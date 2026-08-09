from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import List, Optional

from bot.config import settings


# Сколько товаров на одной странице
PRODUCTS_PER_PAGE = 6


def main_menu_kb() -> InlineKeyboardMarkup:
    """Главное меню — только нужные кнопки"""
    builder = InlineKeyboardBuilder()
    if settings.WEBAPP_URL:
        builder.row(
            InlineKeyboardButton(
                text="🖥 Открыть приложение",
                web_app=WebAppInfo(url=settings.WEBAPP_URL),
            )
        )
    builder.row(
        InlineKeyboardButton(text="➕ Добавить товар", callback_data="menu:add"),
        InlineKeyboardButton(text="📋 Мои товары", callback_data="menu:my_products"),
    )
    builder.row(
        InlineKeyboardButton(text="📊 Excel-отчёт", callback_data="menu:excel"),
        InlineKeyboardButton(text="🔔 Уведомления", callback_data="menu:notifications"),
    )
    builder.row(
        InlineKeyboardButton(text="ℹ️ Помощь", callback_data="menu:help"),
    )
    return builder.as_markup()


def cancel_inline_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="menu:main"))
    return builder.as_markup()


def products_list_kb(
    products: list,
    page: int = 0,
    total: int = 0,
) -> InlineKeyboardMarkup:
    """
    Список товаров кнопками + пагинация.
    products — список UserProduct с уже загруженным .product
    """
    builder = InlineKeyboardBuilder()

    for up in products:
        p = up.product
        name = (p.name or f"Артикул {p.nm_id}")[:40]
        price = f"{p.current_price:.0f}₽" if p.current_price else "—"
        prefix = "⏸" if up.is_paused else "🟢"
        builder.row(
            InlineKeyboardButton(
                text=f"{prefix} {name} | {price}",
                callback_data=f"product:{p.id}",
            )
        )

    # Пагинация
    total_pages = max(1, (total + PRODUCTS_PER_PAGE - 1) // PRODUCTS_PER_PAGE)
    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(text="⬅️", callback_data=f"products_page:{page - 1}")
        )
    nav_buttons.append(
        InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop")
    )
    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton(text="➡️", callback_data=f"products_page:{page + 1}")
        )
    if nav_buttons:
        builder.row(*nav_buttons)

    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return builder.as_markup()


def product_actions_kb(product_id: int, is_paused: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 Обновить", callback_data=f"update_product:{product_id}")
    )
    if is_paused:
        builder.row(
            InlineKeyboardButton(text="▶️ Возобновить", callback_data=f"resume_product:{product_id}")
        )
    else:
        builder.row(
            InlineKeyboardButton(text="⏸ Пауза", callback_data=f"pause_product:{product_id}")
        )
    builder.row(
        InlineKeyboardButton(text="📈 История цен", callback_data=f"history:{product_id}"),
        InlineKeyboardButton(text="🔔 Уведомления", callback_data=f"notify_settings:{product_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_product:{product_id}")
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ К списку", callback_data="menu:my_products"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main"),
    )
    return builder.as_markup()


def confirm_delete_kb(product_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete:{product_id}"),
        InlineKeyboardButton(text="❌ Нет", callback_data=f"product:{product_id}"),
    )
    return builder.as_markup()


def back_to_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return builder.as_markup()


def product_history_kb(product_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⬅️ К товару", callback_data=f"product:{product_id}")
    )
    return builder.as_markup()


def product_notify_kb(product_id: int, enabled: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if enabled:
        builder.row(
            InlineKeyboardButton(
                text="🔕 Выключить уведомления по товару",
                callback_data=f"product_notify:{product_id}:off",
            )
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text="🔔 Включить уведомления по товару",
                callback_data=f"product_notify:{product_id}:on",
            )
        )
    builder.row(
        InlineKeyboardButton(text="⬅️ К товару", callback_data=f"product:{product_id}")
    )
    return builder.as_markup()


def notifications_global_kb(enabled: bool = True) -> InlineKeyboardMarkup:
    """Глобальные уведомления вкл/выкл"""
    builder = InlineKeyboardBuilder()
    if enabled:
        builder.row(
            InlineKeyboardButton(text="🔕 Выключить все уведомления", callback_data="notify_global:off")
        )
    else:
        builder.row(
            InlineKeyboardButton(text="🔔 Включить все уведомления", callback_data="notify_global:on")
        )
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return builder.as_markup()


# ===================== EXCEL-ОТЧЁТ =====================

# Доступные поля для выгрузки: (ключ, подпись)
EXCEL_FIELDS: list[tuple[str, str]] = [
    ("name", "📝 Название"),
    ("article", "📦 Артикул"),
    ("price", "💰 Цена"),
    ("old_price", "⚪ Цена без скидки"),
    ("brand", "🏷 Бренд"),
    ("rating", "⭐ Рейтинг"),
    ("feedbacks", "💬 Кол-во отзывов"),
    ("seller", "🏪 Продавец"),
    ("url", "🔗 Ссылка на товар"),
]

EXCEL_PRODUCTS_PER_PAGE = 6


def excel_start_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📦 Все товары", callback_data="excel:mode:all")
    )
    builder.row(
        InlineKeyboardButton(text="🎯 Выбрать товары", callback_data="excel:mode:select")
    )
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return builder.as_markup()


def excel_products_kb(
    products: list,
    page: int,
    total: int,
    selected_ids: set,
) -> InlineKeyboardMarkup:
    """
    Список товаров для отчёта с переключателями 🔴/🟢.
    products — список UserProduct с загруженным .product (одна страница).
    """
    builder = InlineKeyboardBuilder()

    for up in products:
        p = up.product
        name = (p.name or f"Артикул {p.nm_id}")[:38]
        mark = "🟢" if p.id in selected_ids else "🔴"
        builder.row(
            InlineKeyboardButton(
                text=f"{mark} {name}",
                callback_data=f"excel_toggle_product:{p.id}:{page}",
            )
        )

    total_pages = max(1, (total + EXCEL_PRODUCTS_PER_PAGE - 1) // EXCEL_PRODUCTS_PER_PAGE)
    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(text="⬅️", callback_data=f"excel_products_page:{page - 1}")
        )
    nav_buttons.append(
        InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop")
    )
    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton(text="➡️", callback_data=f"excel_products_page:{page + 1}")
        )
    if nav_buttons:
        builder.row(*nav_buttons)

    builder.row(
        InlineKeyboardButton(text="✅ Выбрать все", callback_data="excel_select_all"),
        InlineKeyboardButton(text="❌ Снять все", callback_data="excel_select_none"),
    )
    builder.row(
        InlineKeyboardButton(
            text=f"➡️ Далее ({len(selected_ids)} выбрано)",
            callback_data="excel_products_done",
        )
    )
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return builder.as_markup()


def excel_fields_kb(selected_fields: set) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, label in EXCEL_FIELDS:
        mark = "🟢" if key in selected_fields else "🔴"
        builder.row(
            InlineKeyboardButton(
                text=f"{mark} {label}",
                callback_data=f"excel_toggle_field:{key}",
            )
        )
    builder.row(
        InlineKeyboardButton(text="✅ Выбрать все", callback_data="excel_fields_all"),
        InlineKeyboardButton(text="❌ Снять все", callback_data="excel_fields_none"),
    )
    builder.row(
        InlineKeyboardButton(text="📥 Сформировать Excel", callback_data="excel_generate")
    )
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return builder.as_markup()
