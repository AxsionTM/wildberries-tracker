from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


def main_menu_kb() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="➕ Добавить товар"),
        KeyboardButton(text="📋 Мои товары"),
    )
    builder.row(
        KeyboardButton(text="📊 Скачать Excel"),
        KeyboardButton(text="📈 История цены"),
    )
    builder.row(
        KeyboardButton(text="⚙️ Настройки"),
        KeyboardButton(text="🔔 Уведомления"),
    )
    builder.row(
        KeyboardButton(text="ℹ️ Помощь"),
    )
    return builder.as_markup(resize_keyboard=True)


def cancel_kb() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="❌ Отмена"))
    return builder.as_markup(resize_keyboard=True)


def product_actions_kb(product_id: int, is_paused: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🔄 Обновить сейчас",
            callback_data=f"update_product:{product_id}"
        )
    )
    if is_paused:
        builder.row(
            InlineKeyboardButton(
                text="▶️ Возобновить мониторинг",
                callback_data=f"resume_product:{product_id}"
            )
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text="⏸ Пауза мониторинга",
                callback_data=f"pause_product:{product_id}"
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="📈 История цены",
            callback_data=f"history:{product_id}"
        ),
        InlineKeyboardButton(
            text="⚙️ Уведомления",
            callback_data=f"notify_settings:{product_id}"
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🗑 Удалить",
            callback_data=f"delete_product:{product_id}"
        )
    )
    return builder.as_markup()


def confirm_delete_kb(product_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete:{product_id}"),
        InlineKeyboardButton(text="❌ Нет", callback_data="cancel_delete"),
    )
    return builder.as_markup()


def back_to_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu"))
    return builder.as_markup()
