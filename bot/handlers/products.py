from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.parser import extract_nm_id, parse_and_get_info
from bot.services.db_service import (
    get_or_create_user,
    get_user_products_count,
    get_or_create_product,
    add_product_to_user,
    get_user_products,
    get_user_product,
)
from bot.keyboards.inline import main_menu_kb, cancel_kb, product_actions_kb, confirm_delete_kb
from bot.database.session import async_session
from bot.config import settings

router = Router(name="products")


class AddProductStates(StatesGroup):
    waiting_for_input = State()


def format_product_card(product, user_product=None) -> str:
    """Красивая карточка товара (как в рабочем мини-боте)"""
    status = ""
    if user_product:
        if user_product.is_paused:
            status = "⏸ <i>мониторинг на паузе</i>\n\n"
        elif not user_product.is_active:
            status = "❌ <i>удалён из мониторинга</i>\n\n"

    name = product.name or "Без названия"
    brand = product.brand or "—"
    seller = product.seller or "—"

    text = (
        f"{status}"
        "🛍 <b>ТОВАР WILDBERRIES</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 <b>Артикул:</b> <code>{product.nm_id}</code>\n"
        f"📝 <b>Название:</b> {name}\n"
        f"🏷 <b>Бренд:</b> {brand}\n\n"
        "💰 <b>ЦЕНА</b>\n"
    )

    if product.current_price is not None:
        price_str = f"{product.current_price:,.0f}".replace(",", " ")
        text += f"🟢 Сейчас: <b>{price_str} ₽</b>\n"
    else:
        text += "🟢 Сейчас: —\n"

    if product.price_without_discount is not None:
        old_str = f"{product.price_without_discount:,.0f}".replace(",", " ")
        text += f"⚪ Без скидки: {old_str} ₽\n"

    if product.discount_percent is not None:
        text += f"🔥 Скидка: <b>{product.discount_percent:.0f}%</b>\n"

    text += "\n⭐ <b>ОЦЕНКИ</b>\n"
    if product.rating is not None:
        text += f"⭐ Рейтинг: <b>{product.rating}</b>\n"
    if product.feedbacks_count is not None:
        text += f"💬 Отзывов: <b>{product.feedbacks_count}</b>\n"

    text += f"\n🏪 <b>ПРОДАВЕЦ</b>\n👤 {seller}\n"

    if product.stock is not None:
        text += f"\n📦 Остаток: <b>{product.stock} шт.</b>\n"

    if product.is_in_promo:
        text += "\n🔥 <b>В акции!</b>\n"

    text += (
        "\n━━━━━━━━━━━━━━━━━━\n"
        f"🔗 <a href=\"https://www.wildberries.ru/catalog/{product.nm_id}/detail.aspx\">"
        "Открыть товар на Wildberries</a>"
    )
    return text


@router.message(F.text == "➕ Добавить товар")
async def add_product_start(message: Message, state: FSMContext):
    await state.set_state(AddProductStates.waiting_for_input)
    await message.answer(
        "Отправь <b>артикул</b> товара Wildberries или <b>ссылку</b> на него.\n\n"
        "Можно отправить несколько артикулов/ссылок списком — каждый с новой строки.\n\n"
        "Пример:\n"
        "<code>123456789</code>\n"
        "<code>https://www.wildberries.ru/catalog/987654321/detail.aspx</code>",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )


@router.message(F.text == "❌ Отмена")
async def cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=main_menu_kb())


@router.message(AddProductStates.waiting_for_input)
async def process_add_product(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text:
        await message.answer("Пустое сообщение. Пришли артикул или ссылку.")
        return

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    nm_ids = []
    for line in lines:
        nm_id = extract_nm_id(line)
        if nm_id:
            nm_ids.append(nm_id)

    if not nm_ids:
        await message.answer(
            "Не удалось найти артикул.\n"
            "Пришли число (артикул) или ссылку вида:\n"
            "<code>https://www.wildberries.ru/catalog/12345678/detail.aspx</code>",
            parse_mode="HTML",
        )
        return

    # Убираем дубли
    nm_ids = list(dict.fromkeys(nm_ids))

    async with async_session() as session:
        user = await get_or_create_user(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
        )

        current_count = await get_user_products_count(session, user.id)
        available_slots = user.max_products - current_count

        if available_slots <= 0:
            await message.answer(
                f"❌ Достигнут лимит товаров ({user.max_products}).\n"
                "Удали ненужные товары или обратись к администратору.",
                reply_markup=main_menu_kb(),
            )
            await state.clear()
            return

        if len(nm_ids) > available_slots:
            nm_ids = nm_ids[:available_slots]
            await message.answer(
                f"⚠️ Можно добавить только {available_slots} товар(ов) (лимит {user.max_products}). "
                f"Добавляю первые {available_slots}."
            )

        await message.answer(f"⏳ Обрабатываю {len(nm_ids)} товар(ов)...")

        added = 0
        already = 0
        failed = 0

        for nm_id in nm_ids:
            data = await parse_and_get_info(nm_id)
            if not data:
                failed += 1
                await message.answer(f"❌ Не удалось получить данные по артикулу <code>{nm_id}</code>", parse_mode="HTML")
                continue

            product = await get_or_create_product(session, data)
            user_product, created = await add_product_to_user(session, user, product)

            if created:
                added += 1
                card = format_product_card(product, user_product)
                await message.answer(
                    f"✅ Товар добавлен!\n\n{card}",
                    parse_mode="HTML",
                    reply_markup=product_actions_kb(product.id),
                    disable_web_page_preview=True,
                )
            else:
                already += 1
                card = format_product_card(product, user_product)
                await message.answer(
                    f"ℹ️ Товар уже был в вашем списке (мониторинг возобновлён).\n\n{card}",
                    parse_mode="HTML",
                    reply_markup=product_actions_kb(product.id, is_paused=user_product.is_paused),
                    disable_web_page_preview=True,
                )

        summary = f"\n📊 Итого: добавлено {added}, уже было {already}, ошибок {failed}"
        await message.answer(summary, reply_markup=main_menu_kb())
        await state.clear()


@router.message(F.text == "📋 Мои товары")
async def my_products(message: Message):
    async with async_session() as session:
        user = await get_or_create_user(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
        )
        products = await get_user_products(session, user.id)

    if not products:
        await message.answer(
            "У тебя пока нет товаров.\nНажми «➕ Добавить товар», чтобы начать.",
            reply_markup=main_menu_kb(),
        )
        return

    await message.answer(f"📋 Твои товары ({len(products)}):")

    for up in products:
        product = up.product
        card = format_product_card(product, up)
        await message.answer(
            card,
            parse_mode="HTML",
            reply_markup=product_actions_kb(product.id, is_paused=up.is_paused),
            disable_web_page_preview=True,
        )


@router.callback_query(F.data.startswith("update_product:"))
async def update_product_callback(callback: CallbackQuery):
    product_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user.id)
        up = await get_user_product(session, user.id, product_id)
        if not up:
            await callback.answer("Товар не найден", show_alert=True)
            return

        await callback.answer("Обновляю...")
        data = await parse_and_get_info(up.product.nm_id)
        if not data:
            await callback.message.answer("❌ Не удалось обновить данные. Попробуй позже.")
            return

        product = await get_or_create_product(session, data)
        card = format_product_card(product, up)
        await callback.message.edit_text(
            f"✅ Данные обновлены!\n\n{card}",
            parse_mode="HTML",
            reply_markup=product_actions_kb(product.id, is_paused=up.is_paused),
            disable_web_page_preview=True,
        )


@router.callback_query(F.data.startswith("pause_product:"))
async def pause_product_callback(callback: CallbackQuery):
    product_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user.id)
        up = await get_user_product(session, user.id, product_id)
        if not up:
            await callback.answer("Товар не найден", show_alert=True)
            return

        up.is_paused = True
        await session.commit()
        await callback.answer("Мониторинг поставлен на паузу")
        card = format_product_card(up.product, up)
        await callback.message.edit_text(
            card,
            parse_mode="HTML",
            reply_markup=product_actions_kb(product_id, is_paused=True),
            disable_web_page_preview=True,
        )


@router.callback_query(F.data.startswith("resume_product:"))
async def resume_product_callback(callback: CallbackQuery):
    product_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user.id)
        up = await get_user_product(session, user.id, product_id)
        if not up:
            await callback.answer("Товар не найден", show_alert=True)
            return

        up.is_paused = False
        up.is_active = True
        await session.commit()
        await callback.answer("Мониторинг возобновлён")
        card = format_product_card(up.product, up)
        await callback.message.edit_text(
            card,
            parse_mode="HTML",
            reply_markup=product_actions_kb(product_id, is_paused=False),
            disable_web_page_preview=True,
        )


@router.callback_query(F.data.startswith("delete_product:"))
async def delete_product_callback(callback: CallbackQuery):
    product_id = int(callback.data.split(":")[1])
    await callback.message.edit_reply_markup(reply_markup=confirm_delete_kb(product_id))
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_delete:"))
async def confirm_delete_callback(callback: CallbackQuery):
    product_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user.id)
        up = await get_user_product(session, user.id, product_id)
        if not up:
            await callback.answer("Товар не найден", show_alert=True)
            return

        await session.delete(up)
        await session.commit()

    await callback.message.edit_text("🗑 Товар удалён из мониторинга.")
    await callback.answer()


@router.callback_query(F.data == "cancel_delete")
async def cancel_delete_callback(callback: CallbackQuery):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Отменено")
