from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import CommandStart, Command
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.db_service import get_or_create_user
from bot.keyboards.inline import main_menu_kb
from bot.database.session import async_session

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message):
    async with async_session() as session:
        user = await get_or_create_user(
            session=session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
        )

    text = (
        f"👋 Привет, <b>{message.from_user.first_name}</b>!\n\n"
        "Я бот для мониторинга цен и ключевых показателей товаров на <b>Wildberries</b>.\n\n"
        "🔹 Добавляй товары по артикулу или ссылке\n"
        "🔹 Получай уведомления об изменении цены, остатка, рейтинга\n"
        "🔹 Скачивай Excel-отчёты с историей\n"
        "🔹 Следи за конкурентами и своими товарами\n\n"
        "Бот полностью бесплатный.\n\n"
        "Выбери действие в меню ниже 👇"
    )
    await message.answer(text, reply_markup=main_menu_kb(), parse_mode="HTML")


@router.message(Command("help"))
@router.message(F.text == "ℹ️ Помощь")
async def cmd_help(message: Message):
    text = (
        "<b>📖 Помощь по боту</b>\n\n"
        "<b>Как добавить товар:</b>\n"
        "1. Нажми «➕ Добавить товар»\n"
        "2. Пришли артикул (например <code>123456789</code>) или ссылку на товар WB\n"
        "3. Бот сразу соберёт данные и начнёт мониторинг\n\n"
        "<b>Массовое добавление:</b>\n"
        "Можно отправить несколько артикулов/ссылок списком (каждый с новой строки)\n\n"
        "<b>Мои товары:</b>\n"
        "Список всех добавленных товаров с текущими ценами\n\n"
        "<b>Уведомления:</b>\n"
        "Можно настроить условия: падение/рост цены, остаток, появление в акции и т.д.\n\n"
        "<b>Excel-отчёт:</b>\n"
        "Актуальные данные + история цен по всем товарам\n\n"
        "По вопросам и предложениям — пиши администратору."
    )
    await message.answer(text, parse_mode="HTML", reply_markup=main_menu_kb())
