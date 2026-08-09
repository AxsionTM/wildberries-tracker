import os
import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext

from bot.services.db_service import (
    get_or_create_user,
    get_user_products_page,
    get_all_user_product_ids,
    get_user_products_by_ids,
)
from bot.services.excel_export import build_excel_report
from bot.keyboards.inline import (
    excel_start_kb,
    excel_products_kb,
    excel_fields_kb,
    back_to_menu_kb,
    EXCEL_PRODUCTS_PER_PAGE,
)
from bot.database.session import async_session

logger = logging.getLogger(__name__)

router = Router(name="excel")

# Ключи в FSM-хранилище (используем обычные данные состояния, отдельный State не нужен —
# вся навигация идёт по инлайн-кнопкам)
KEY_SELECTED_PRODUCTS = "excel_selected_products"
KEY_SELECTED_FIELDS = "excel_selected_fields"


async def _edit(callback: CallbackQuery, text: str, reply_markup=None):
    try:
        await callback.message.edit_text(
            text, reply_markup=reply_markup, parse_mode="HTML", disable_web_page_preview=True
        )
    except Exception:
        await callback.message.answer(
            text, reply_markup=reply_markup, parse_mode="HTML", disable_web_page_preview=True
        )
    await callback.answer()


EXCEL_INTRO_TEXT = (
    "📊 <b>Excel-отчёт</b>\n\n"
    "Сначала выбери, по каким товарам собрать отчёт."
)


# ===================== СТАРТ =====================

@router.callback_query(F.data == "menu:excel")
async def cb_excel_start(callback: CallbackQuery, state: FSMContext):
    await state.update_data(**{KEY_SELECTED_PRODUCTS: [], KEY_SELECTED_FIELDS: []})
    await _edit(callback, EXCEL_INTRO_TEXT, excel_start_kb())


@router.callback_query(F.data == "excel:mode:all")
async def cb_excel_mode_all(callback: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user.id)
        all_ids = await get_all_user_product_ids(session, user.id)

    if not all_ids:
        await _edit(
            callback,
            "📊 <b>Excel-отчёт</b>\n\nУ тебя пока нет товаров для отчёта.",
            back_to_menu_kb(),
        )
        return

    await state.update_data(**{KEY_SELECTED_PRODUCTS: all_ids})
    await _show_fields_step(callback, state)


@router.callback_query(F.data == "excel:mode:select")
async def cb_excel_mode_select(callback: CallbackQuery, state: FSMContext):
    await _show_products_page(callback, state, page=0)


# ===================== ШАГ 1: ВЫБОР ТОВАРОВ =====================

async def _show_products_page(callback: CallbackQuery, state: FSMContext, page: int):
    data = await state.get_data()
    selected_ids = set(data.get(KEY_SELECTED_PRODUCTS, []))

    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user.id)
        page_items, total = await get_user_products_page(
            session, user.id, page=page, per_page=EXCEL_PRODUCTS_PER_PAGE
        )

    if total == 0:
        await _edit(
            callback,
            "📊 <b>Excel-отчёт</b>\n\nУ тебя пока нет товаров для отчёта.",
            back_to_menu_kb(),
        )
        return

    text = (
        "📊 <b>Excel-отчёт — выбор товаров</b>\n\n"
        "Нажимай на товары, чтобы включить/исключить их из отчёта "
        "(🔴 — не включён, 🟢 — включён).\n\n"
        f"Страница {page + 1} из {max(1, (total + EXCEL_PRODUCTS_PER_PAGE - 1) // EXCEL_PRODUCTS_PER_PAGE)}"
    )
    await _edit(callback, text, excel_products_kb(page_items, page, total, selected_ids))


@router.callback_query(F.data.startswith("excel_products_page:"))
async def cb_excel_products_page(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.split(":")[1])
    await _show_products_page(callback, state, page=page)


@router.callback_query(F.data.startswith("excel_toggle_product:"))
async def cb_excel_toggle_product(callback: CallbackQuery, state: FSMContext):
    _, product_id_str, page_str = callback.data.split(":")
    product_id, page = int(product_id_str), int(page_str)

    data = await state.get_data()
    selected_ids = set(data.get(KEY_SELECTED_PRODUCTS, []))
    if product_id in selected_ids:
        selected_ids.discard(product_id)
    else:
        selected_ids.add(product_id)
    await state.update_data(**{KEY_SELECTED_PRODUCTS: list(selected_ids)})

    await _show_products_page(callback, state, page=page)


@router.callback_query(F.data == "excel_select_all")
async def cb_excel_select_all(callback: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user.id)
        all_ids = await get_all_user_product_ids(session, user.id)
    await state.update_data(**{KEY_SELECTED_PRODUCTS: all_ids})
    await _show_products_page(callback, state, page=0)


@router.callback_query(F.data == "excel_select_none")
async def cb_excel_select_none(callback: CallbackQuery, state: FSMContext):
    await state.update_data(**{KEY_SELECTED_PRODUCTS: []})
    await _show_products_page(callback, state, page=0)


@router.callback_query(F.data == "excel_products_done")
async def cb_excel_products_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected_ids = data.get(KEY_SELECTED_PRODUCTS, [])
    if not selected_ids:
        await callback.answer("Выбери хотя бы один товар 🙂", show_alert=True)
        return
    await _show_fields_step(callback, state)


# ===================== ШАГ 2: ВЫБОР ПОЛЕЙ =====================

async def _show_fields_step(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected_fields = set(data.get(KEY_SELECTED_FIELDS, []))
    products_count = len(data.get(KEY_SELECTED_PRODUCTS, []))

    text = (
        "📊 <b>Excel-отчёт — выбор колонок</b>\n\n"
        f"Товаров в отчёте: <b>{products_count}</b>\n\n"
        "Выбери, какие данные включить в файл "
        "(🔴 — не включено, 🟢 — включено):"
    )
    await _edit(callback, text, excel_fields_kb(selected_fields))


@router.callback_query(F.data.startswith("excel_toggle_field:"))
async def cb_excel_toggle_field(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":", 1)[1]
    data = await state.get_data()
    selected_fields = set(data.get(KEY_SELECTED_FIELDS, []))
    if key in selected_fields:
        selected_fields.discard(key)
    else:
        selected_fields.add(key)
    await state.update_data(**{KEY_SELECTED_FIELDS: list(selected_fields)})
    await _show_fields_step(callback, state)


@router.callback_query(F.data == "excel_fields_all")
async def cb_excel_fields_all(callback: CallbackQuery, state: FSMContext):
    from bot.keyboards.inline import EXCEL_FIELDS

    all_keys = [key for key, _label in EXCEL_FIELDS]
    await state.update_data(**{KEY_SELECTED_FIELDS: all_keys})
    await _show_fields_step(callback, state)


@router.callback_query(F.data == "excel_fields_none")
async def cb_excel_fields_none(callback: CallbackQuery, state: FSMContext):
    await state.update_data(**{KEY_SELECTED_FIELDS: []})
    await _show_fields_step(callback, state)


# ===================== ШАГ 3: ГЕНЕРАЦИЯ ФАЙЛА =====================

@router.callback_query(F.data == "excel_generate")
async def cb_excel_generate(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected_ids = data.get(KEY_SELECTED_PRODUCTS, [])
    selected_fields = data.get(KEY_SELECTED_FIELDS, [])

    if not selected_ids:
        await callback.answer("Сначала выбери товары", show_alert=True)
        return
    if not selected_fields:
        await callback.answer("Выбери хотя бы одну колонку 🙂", show_alert=True)
        return

    await callback.answer("⏳ Формирую файл...")

    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user.id)
        products = await get_user_products_by_ids(session, user.id, selected_ids)

    file_path = None
    try:
        file_path = build_excel_report(products, selected_fields)
        document = FSInputFile(file_path, filename="wb_monitor_report.xlsx")
        await callback.message.answer_document(
            document,
            caption=f"📊 Готово! Товаров в отчёте: {len(products)}.",
        )
    except Exception as e:
        logger.error(f"Ошибка при формировании Excel-отчёта: {e}")
        await callback.message.answer("❌ Не удалось сформировать файл. Попробуй ещё раз.")
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

    await state.update_data(**{KEY_SELECTED_PRODUCTS: [], KEY_SELECTED_FIELDS: []})
