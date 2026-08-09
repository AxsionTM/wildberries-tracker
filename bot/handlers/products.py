from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.services.parser import extract_nm_id, parse_and_get_info
from bot.services.db_service import (
    get_or_create_user,
    get_user_products_count,
    get_or_create_product,
    add_product_to_user,
    get_user_products,
    get_user_product,
    get_user_products_page,
    get_product_history,
    set_user_product_notifications_enabled,
)
from bot.keyboards.inline import (
    main_menu_kb,
    cancel_inline_kb,
    product_actions_kb,
    confirm_delete_kb,
    products_list_kb,
    PRODUCTS_PER_PAGE,
    back_to_menu_kb,
    product_history_kb,
    product_notify_kb,
)
from bot.database.session import async_session
from bot.config import settings

router = Router(name="products")


class AddProductStates(StatesGroup):
    waiting_for_input = State()


def format_product_card(product, user_product=None) -> str:
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


async def _edit(callback: CallbackQuery, text: str, reply_markup=None):
    try:
        await callback.message.edit_text(
            text,
            reply_markup=reply_markup,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception:
        await callback.message.answer(
            text,
            reply_markup=reply_markup,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    await callback.answer()


# ===================== ГЛАВНОЕ МЕНЮ: ДОБАВИТЬ =====================

@router.callback_query(F.data == "menu:add")
async def cb_add_product(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddProductStates.waiting_for_input)
    text = (
        "➕ <b>Добавить товар</b>\n\n"
        "Пришли <b>артикул</b> или <b>ссылку</b> на товар Wildberries.\n\n"
        "Можно несколько — каждый с новой строки.\n\n"
        "Пример:\n"
        "<code>816758849</code>\n"
        "<code>https://www.wildberries.ru/catalog/816758849/detail.aspx</code>"
    )
    await _edit(callback, text, cancel_inline_kb())


@router.message(AddProductStates.waiting_for_input)
async def process_add_product(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("Пришли артикул или ссылку.", reply_markup=cancel_inline_kb())
        return

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    nm_ids = []
    for line in lines:
        nm_id = extract_nm_id(line)
        if nm_id:
            nm_ids.append(nm_id)

    if not nm_ids:
        await message.answer(
            "Не удалось найти артикул.\nПришли число или ссылку WB.",
            reply_markup=cancel_inline_kb(),
            parse_mode="HTML",
        )
        return

    nm_ids = list(dict.fromkeys(nm_ids))

    async with async_session() as session:
        user = await get_or_create_user(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
        )
        current_count = await get_user_products_count(session, user.id)
        available = user.max_products - current_count

        if available <= 0:
            await message.answer(
                f"❌ Лимит товаров ({user.max_products}). Удали ненужные.",
                reply_markup=main_menu_kb(),
            )
            await state.clear()
            return

        if len(nm_ids) > available:
            nm_ids = nm_ids[:available]
            await message.answer(f"⚠️ Добавлю только {available} (лимит).")

        status_msg = await message.answer(f"⏳ Обрабатываю {len(nm_ids)} товар(ов)...")

        added = already = failed = 0
        last_product = last_up = None

        for nm_id in nm_ids:
            data = await parse_and_get_info(nm_id)
            if not data:
                failed += 1
                continue

            product = await get_or_create_product(session, data)
            user_product, created = await add_product_to_user(session, user, product)
            last_product, last_up = product, user_product

            if created:
                added += 1
            else:
                already += 1

        await state.clear()

        summary = f"✅ Готово: добавлено {added}, уже было {already}, ошибок {failed}"

        if last_product and (added + already) == 1:
            card = format_product_card(last_product, last_up)
            await status_msg.edit_text(
                f"{summary}\n\n{card}",
                parse_mode="HTML",
                reply_markup=product_actions_kb(last_product.id, is_paused=last_up.is_paused),
                disable_web_page_preview=True,
            )
        else:
            await status_msg.edit_text(summary, reply_markup=main_menu_kb())


# ===================== МОИ ТОВАРЫ (список + пагинация) =====================

async def _show_products_page(callback: CallbackQuery, page: int = 0):
    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user.id)
        # Берём из базы СРАЗУ только нужную страницу (LIMIT/OFFSET),
        # а не все товары пользователя целиком — так бот не тормозит
        # и не грузит сервер, даже если товаров сотни.
        page_items, total = await get_user_products_page(
            session, user.id, page=page, per_page=PRODUCTS_PER_PAGE
        )

        if total == 0:
            await _edit(
                callback,
                "📋 <b>Мои товары</b>\n\nУ тебя пока нет товаров.\nНажми «➕ Добавить товар».",
                main_menu_kb(),
            )
            return

        text = (
            f"📋 <b>Мои товары</b> — {total} шт.\n\n"
            f"Страница {page + 1} из {max(1, (total + PRODUCTS_PER_PAGE - 1) // PRODUCTS_PER_PAGE)}\n"
            "Нажми на товар, чтобы открыть карточку 👇"
        )
        await _edit(callback, text, products_list_kb(page_items, page=page, total=total))


@router.callback_query(F.data == "menu:my_products")
async def cb_my_products(callback: CallbackQuery):
    await _show_products_page(callback, page=0)


@router.callback_query(F.data.startswith("products_page:"))
async def cb_products_page(callback: CallbackQuery):
    page = int(callback.data.split(":")[1])
    await _show_products_page(callback, page=page)


@router.callback_query(F.data.startswith("product:"))
async def cb_open_product(callback: CallbackQuery):
    product_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user.id)
        up = await get_user_product(session, user.id, product_id)
        if not up:
            await callback.answer("Товар не найден", show_alert=True)
            return
        card = format_product_card(up.product, up)
        await _edit(callback, card, product_actions_kb(product_id, is_paused=up.is_paused))


# ===================== ДЕЙСТВИЯ С ТОВАРОМ =====================

@router.callback_query(F.data.startswith("update_product:"))
async def cb_update_product(callback: CallbackQuery):
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
            await callback.message.answer("❌ Не удалось обновить. Попробуй позже.")
            return

        product = await get_or_create_product(session, data)
        card = format_product_card(product, up)
        try:
            await callback.message.edit_text(
                f"✅ Обновлено!\n\n{card}",
                parse_mode="HTML",
                reply_markup=product_actions_kb(product.id, is_paused=up.is_paused),
                disable_web_page_preview=True,
            )
        except Exception:
            pass


@router.callback_query(F.data.startswith("pause_product:"))
async def cb_pause(callback: CallbackQuery):
    product_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user.id)
        up = await get_user_product(session, user.id, product_id)
        if not up:
            await callback.answer("Не найден", show_alert=True)
            return
        up.is_paused = True
        await session.commit()
        card = format_product_card(up.product, up)
        await _edit(callback, card, product_actions_kb(product_id, is_paused=True))


@router.callback_query(F.data.startswith("resume_product:"))
async def cb_resume(callback: CallbackQuery):
    product_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user.id)
        up = await get_user_product(session, user.id, product_id)
        if not up:
            await callback.answer("Не найден", show_alert=True)
            return
        up.is_paused = False
        up.is_active = True
        await session.commit()
        card = format_product_card(up.product, up)
        await _edit(callback, card, product_actions_kb(product_id, is_paused=False))


@router.callback_query(F.data.startswith("delete_product:"))
async def cb_delete_ask(callback: CallbackQuery):
    product_id = int(callback.data.split(":")[1])
    await _edit(
        callback,
        "🗑 Удалить товар из мониторинга?",
        confirm_delete_kb(product_id),
    )


@router.callback_query(F.data.startswith("confirm_delete:"))
async def cb_delete_confirm(callback: CallbackQuery):
    product_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user.id)
        up = await get_user_product(session, user.id, product_id)
        if up:
            await session.delete(up)
            await session.commit()
    await _edit(callback, "🗑 Товар удалён.", main_menu_kb())


# ===================== ИСТОРИЯ ЦЕН (в карточке товара) =====================

def format_history_text(product, history_rows) -> str:
    name = product.name or f"Артикул {product.nm_id}"
    header = f"📈 <b>История цен</b>\n<b>{name}</b>\n━━━━━━━━━━━━━━━━━━\n\n"

    if not history_rows:
        return header + "Пока нет данных — история появится после первого обновления цены."

    lines = []
    # history_rows приходит от новых к старым — печатаем так же, сверху последнее изменение
    for row in history_rows:
        date_str = row.recorded_at.strftime("%d.%m.%Y %H:%M")
        if row.price is not None:
            price_str = f"{row.price:,.0f}".replace(",", " ") + " рублей"
        else:
            price_str = "нет данных"

        line = f"🗓 {date_str} — цена {price_str}"
        if row.price_without_discount is not None:
            old_str = f"{row.price_without_discount:,.0f}".replace(",", " ")
            line += f" / без скидки {old_str} рублей"
        lines.append(line)

    text = header + "\n".join(lines)

    # Телеграм режет сообщения длиннее 4096 символов — на всякий случай подрежем
    if len(text) > 3900:
        text = text[:3880] + "\n\n… (показаны не все записи)"

    return text


@router.callback_query(F.data.startswith("history:"))
async def cb_history(callback: CallbackQuery):
    product_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user.id)
        up = await get_user_product(session, user.id, product_id)
        if not up:
            await callback.answer("Товар не найден", show_alert=True)
            return

        history_rows = await get_product_history(session, up.product.id, limit=30)
        text = format_history_text(up.product, history_rows)
        await _edit(callback, text, product_history_kb(product_id))


# ===================== УВЕДОМЛЕНИЯ ПО ТОВАРУ (в карточке товара) =====================

@router.callback_query(F.data.startswith("notify_settings:"))
async def cb_notify_settings(callback: CallbackQuery):
    product_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user.id)
        up = await get_user_product(session, user.id, product_id)
        if not up:
            await callback.answer("Товар не найден", show_alert=True)
            return

        name = up.product.name or f"Артикул {up.product.nm_id}"
        status = "включены 🔔" if up.notifications_enabled else "выключены 🔕"
        text = (
            f"🔔 <b>Уведомления по товару</b>\n\n"
            f"<b>{name}</b>\n\n"
            f"Сейчас уведомления по этому товару <b>{status}</b>.\n\n"
            "Если выключить — бот продолжит следить за товаром, "
            "но сообщения об изменениях по нему присылать не будет."
        )
        await _edit(callback, text, product_notify_kb(product_id, enabled=up.notifications_enabled))


@router.callback_query(F.data.startswith("product_notify:"))
async def cb_product_notify_toggle(callback: CallbackQuery):
    _, product_id_str, mode = callback.data.split(":")
    product_id = int(product_id_str)
    enabled = mode == "on"

    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user.id)
        up = await set_user_product_notifications_enabled(
            session, user.id, product_id, enabled
        )
        if not up:
            await callback.answer("Товар не найден", show_alert=True)
            return

        name = up.product.name or f"Артикул {up.product.nm_id}"
        status = "включены 🔔" if enabled else "выключены 🔕"
        text = (
            f"🔔 <b>Уведомления по товару</b>\n\n"
            f"<b>{name}</b>\n\n"
            f"Уведомления по этому товару теперь <b>{status}</b>."
        )
        await _edit(callback, text, product_notify_kb(product_id, enabled=enabled))


@router.callback_query(F.data.startswith("notify_global:"))
async def cb_notify_global(callback: CallbackQuery):
    from bot.keyboards.inline import notifications_global_kb
    from bot.services.db_service import set_user_notifications_enabled

    mode = callback.data.split(":")[1]
    enabled = mode == "on"

    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user.id)
        await set_user_notifications_enabled(session, user, enabled)

    if enabled:
        text = "🔔 Уведомления по всем товарам <b>включены</b>."
    else:
        text = (
            "🔕 Уведомления по всем товарам <b>выключены</b>.\n\n"
            "Мониторинг цен продолжит работать, но сообщения об изменениях "
            "присылаться не будут."
        )
    await _edit(callback, text, notifications_global_kb(enabled=enabled))
