from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext

from bot.services.db_service import get_or_create_user
from bot.keyboards.inline import main_menu_kb, back_to_menu_kb, notifications_global_kb
from bot.database.session import async_session
from bot.config import settings
from bot.services.monitor import run_monitoring_cycle

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
    # Пока упрощённо: глобальный вкл/выкл (детали в следующем этапе)
    text = (
        "🔔 <b>Уведомления</b>\n\n"
        "Здесь можно включить или выключить уведомления "
        "сразу по <b>всем</b> твоим товарам.\n\n"
        "Подробные настройки (падение цены, остаток и т.д.) "
        "доступны внутри карточки каждого товара."
    )
    await _edit_or_answer(callback, text, notifications_global_kb(enabled=True))


@router.callback_query(F.data == "menu:excel")
async def cb_excel_stub(callback: CallbackQuery):
    text = (
        "📊 <b>Excel-отчёт</b>\n\n"
        "Этот раздел будет доработан в следующем этапе:\n"
        "• выбор товаров\n"
        "• выбор полей (цена, бренд, рейтинг...)\n"
        "• скачивание файла\n\n"
        "Пока можно пользоваться карточкой товара."
    )
    await _edit_or_answer(callback, text, back_to_menu_kb())


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
