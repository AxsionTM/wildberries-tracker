from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext

from bot.services.db_service import get_or_create_user, get_product_by_nm_id
from bot.keyboards.inline import main_menu_kb, back_to_menu_kb, notifications_global_kb
from bot.database.session import async_session
from bot.config import settings
from bot.services.monitor import run_monitoring_cycle, process_product

router = Router(name="start")

MAIN_TEXT = (
    "👋 <b>WB Monitor Bot</b>\n\n"
    "Мониторинг цен и показателей товаров на Wildberries.\n\n"
    "🔹 Добавляй товары по артикулу или ссылке\n"
    "🔹 Получай уведомления об изменениях\n"
    "🔹 Скачивай Excel-отчёты\n\n"
    "Выбери действие 👇"
)

HELP_TEXT = (
    "<b>📖 Помощь</b>\n\n"
    "<b>Добавить товар:</b>\n"
    "Нажми «➕ Добавить товар» и пришли артикул или ссылку WB.\n"
    "Можно несколько штук — каждый с новой строки.\n\n"
    "<b>Мои товары:</b>\n"
    "Список добавленных товаров. Нажми на название, чтобы открыть карточку.\n\n"
    "<b>Уведомления:</b>\n"
    "Можно включить/выключить уведомления по всем товарам.\n\n"
    "<b>Excel:</b>\n"
    "Выгрузка данных по выбранным товарам и полям."
)


async def _edit_or_answer(callback: CallbackQuery, text: str, reply_markup=None):
    """Редактирует текущее сообщение, чтобы не засорять чат"""
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=reply_markup, parse_mode="HTML")
    await callback.answer()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        await get_or_create_user(
            session=session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
        )
    await message.answer(MAIN_TEXT, reply_markup=main_menu_kb(), parse_mode="HTML")


@router.callback_query(F.data == "menu:main")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await _edit_or_answer(callback, MAIN_TEXT, main_menu_kb())


@router.callback_query(F.data == "menu:help")
async def cb_help(callback: CallbackQuery):
    await _edit_or_answer(callback, HELP_TEXT, back_to_menu_kb())


@router.callback_query(F.data == "menu:notifications")
async def cb_notifications(callback: CallbackQuery):
    async with async_session() as session:
        user = await get_or_create_user(
            session=session,
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            full_name=callback.from_user.full_name,
        )
        enabled = user.notifications_enabled

    text = (
        "🔔 <b>Уведомления</b>\n\n"
        "Здесь можно включить или выключить уведомления "
        "сразу по <b>всем</b> твоим товарам.\n\n"
        f"Сейчас уведомления {'включены 🔔' if enabled else 'выключены 🔕'}.\n\n"
        "Уведомления по отдельному товару можно дополнительно "
        "включить/выключить внутри карточки этого товара."
    )
    await _edit_or_answer(callback, text, notifications_global_kb(enabled=enabled))


# Реальный обработчик Excel-отчёта находится в bot/handlers/excel.py (router excel_router)


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery):
    await callback.answer()


@router.message(Command("force_update"))
async def cmd_force_update(message: Message, bot: Bot):
    if message.from_user.id not in settings.admin_ids_list:
        await message.answer("⛔ Только для администратора.")
        return
    await message.answer("🔄 Запускаю обновление всех товаров...")
    try:
        await run_monitoring_cycle(bot)
        await message.answer("✅ Готово.")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@router.message(Command("simulate_price"))
async def cmd_simulate_price(message: Message, bot: Bot):
    """
    Тестовая команда для проверки уведомлений без ожидания реального
    изменения цены на Wildberries.

    Использование:
    /simulate_price <артикул> <новая_цена> [старая_цена_без_скидки]

    Пример:
    /simulate_price 816758849 1500
    """
    if message.from_user.id not in settings.admin_ids_list:
        await message.answer("⛔ Только для администратора.")
        return

    parts = (message.text or "").split()[1:]
    if len(parts) < 2:
        await message.answer(
            "Использование:\n"
            "<code>/simulate_price артикул новая_цена [цена_без_скидки]</code>\n\n"
            "Пример:\n<code>/simulate_price 816758849 1500</code>",
            parse_mode="HTML",
        )
        return

    try:
        nm_id = int(parts[0])
        new_price = float(parts[1])
        new_price_without_discount = float(parts[2]) if len(parts) > 2 else None
    except ValueError:
        await message.answer("Артикул и цена должны быть числами.")
        return

    async with async_session() as session:
        product = await get_product_by_nm_id(session, nm_id)
        if not product:
            await message.answer(
                f"❌ Товар с артикулом <code>{nm_id}</code> не найден в базе.\n"
                "Он должен быть сначала добавлен через «➕ Добавить товар» "
                "(хотя бы одним пользователем).",
                parse_mode="HTML",
            )
            return

        override = {"current_price": new_price}
        if new_price_without_discount is not None:
            override["price_without_discount"] = new_price_without_discount

        old_price = product.current_price
        sent = await process_product(session, product, bot, override_data=override)

    await message.answer(
        f"✅ Готово.\n\n"
        f"Товар: <code>{nm_id}</code>\n"
        f"Цена: {old_price} ₽ → <b>{new_price} ₽</b>\n"
        f"Уведомлений отправлено: <b>{sent}</b>\n\n"
        f"Если 0 — проверь: включены ли уведомления у подписчиков товара "
        f"(глобально и по товару), не на паузе ли мониторинг, и достаточно ли "
        f"сильно изменилась цена (порог по умолчанию — любое изменение от 1 ₽).",
        parse_mode="HTML",
    )
