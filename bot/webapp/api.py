"""REST API мини-приложения. Переиспользует те же сервисы (db_service, parser,
excel_export), что и обычный чат-бот, — так оба интерфейса всегда видят
одинаковые данные и одинаковую бизнес-логику.
"""

import logging
import os
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from bot.database.session import async_session
from bot.services.parser import extract_nm_id, parse_and_get_info
from bot.services.excel_export import build_excel_report
from bot.keyboards.inline import EXCEL_FIELDS
from bot.services.db_service import (
    get_or_create_user,
    get_user_products_count,
    get_or_create_product,
    add_product_to_user,
    get_user_products_page,
    get_user_product,
    get_product_history,
    set_user_notifications_enabled,
    set_user_product_paused,
    update_user_product_settings,
    remove_user_product,
    get_user_products_by_ids,
)
from bot.webapp.auth import TelegramUser, get_current_telegram_user
from bot.webapp.schemas import (
    MeOut,
    MeUpdateIn,
    ProductOut,
    ProductsPageOut,
    ProductDetailOut,
    HistoryPointOut,
    AddProductsIn,
    AddProductsOut,
    AddProductResultItem,
    ProductSettingsIn,
    FieldOut,
    ExportIn,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["webapp"])


def _to_product_out(up) -> ProductOut:
    p = up.product
    return ProductOut(
        id=p.id,
        nm_id=p.nm_id,
        name=p.name,
        brand=p.brand,
        category=p.category,
        seller=p.seller,
        url=p.url or f"https://www.wildberries.ru/catalog/{p.nm_id}/detail.aspx",
        current_price=p.current_price,
        price_without_discount=p.price_without_discount,
        discount_percent=p.discount_percent,
        stock=p.stock,
        rating=p.rating,
        feedbacks_count=p.feedbacks_count,
        questions_count=p.questions_count,
        is_in_promo=p.is_in_promo,
        is_available=p.is_available,
        last_updated=p.last_updated,
        is_paused=up.is_paused,
        notifications_enabled=up.notifications_enabled,
        notify_price_drop=up.notify_price_drop,
        notify_price_rise=up.notify_price_rise,
        price_threshold_percent=up.price_threshold_percent,
        price_threshold_rub=up.price_threshold_rub,
        price_below=up.price_below,
        price_above=up.price_above,
        notify_stock_below=up.notify_stock_below,
        notify_availability=up.notify_availability,
        notify_rating_change=up.notify_rating_change,
        notify_feedbacks_change=up.notify_feedbacks_change,
        notify_promo=up.notify_promo,
        group_name=up.group.name if up.group else None,
    )


@router.get("/me", response_model=MeOut)
async def api_get_me(tg_user: TelegramUser = Depends(get_current_telegram_user)):
    async with async_session() as session:
        user = await get_or_create_user(
            session,
            telegram_id=tg_user.id,
            username=tg_user.username,
            full_name=tg_user.full_name,
        )
        count = await get_user_products_count(session, user.id)
        return MeOut(
            telegram_id=user.telegram_id,
            username=user.username,
            full_name=user.full_name,
            notifications_enabled=user.notifications_enabled,
            products_count=count,
            max_products=user.max_products,
        )


@router.patch("/me", response_model=MeOut)
async def api_update_me(
    body: MeUpdateIn, tg_user: TelegramUser = Depends(get_current_telegram_user)
):
    async with async_session() as session:
        user = await get_or_create_user(
            session,
            telegram_id=tg_user.id,
            username=tg_user.username,
            full_name=tg_user.full_name,
        )
        await set_user_notifications_enabled(session, user, body.notifications_enabled)
        count = await get_user_products_count(session, user.id)
        return MeOut(
            telegram_id=user.telegram_id,
            username=user.username,
            full_name=user.full_name,
            notifications_enabled=user.notifications_enabled,
            products_count=count,
            max_products=user.max_products,
        )


@router.get("/products", response_model=ProductsPageOut)
async def api_list_products(
    page: int = 0,
    per_page: int = 20,
    tg_user: TelegramUser = Depends(get_current_telegram_user),
):
    per_page = max(1, min(per_page, 100))
    async with async_session() as session:
        user = await get_or_create_user(
            session,
            telegram_id=tg_user.id,
            username=tg_user.username,
            full_name=tg_user.full_name,
        )
        items, total = await get_user_products_page(session, user.id, page=page, per_page=per_page)
        return ProductsPageOut(
            items=[_to_product_out(up) for up in items],
            total=total,
            page=page,
            per_page=per_page,
        )


@router.post("/products", response_model=AddProductsOut)
async def api_add_products(
    body: AddProductsIn, tg_user: TelegramUser = Depends(get_current_telegram_user)
):
    raw = body.query or ""
    # Пользователь может вставить артикулы через строки, запятые или пробелы
    lines = [chunk.strip() for piece in raw.splitlines() for chunk in piece.split(",")]
    nm_ids: List[int] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        nm_id = extract_nm_id(line)
        if nm_id:
            nm_ids.append(nm_id)
    nm_ids = list(dict.fromkeys(nm_ids))  # убираем дубли, сохраняя порядок

    if not nm_ids:
        raise HTTPException(status_code=400, detail="Не удалось найти артикул в введённом тексте")

    async with async_session() as session:
        user = await get_or_create_user(
            session,
            telegram_id=tg_user.id,
            username=tg_user.username,
            full_name=tg_user.full_name,
        )
        current_count = await get_user_products_count(session, user.id)
        available = user.max_products - current_count

        if available <= 0:
            raise HTTPException(
                status_code=400,
                detail=f"Достигнут лимит товаров ({user.max_products}). Удали ненужные, чтобы добавить новые.",
            )

        truncated = False
        if len(nm_ids) > available:
            nm_ids = nm_ids[:available]
            truncated = True

        added = already = failed = 0
        result_items: List[AddProductResultItem] = []

        for nm_id in nm_ids:
            data = await parse_and_get_info(nm_id)
            if not data:
                failed += 1
                result_items.append(AddProductResultItem(nm_id=nm_id, status="failed"))
                continue

            product = await get_or_create_product(session, data)
            user_product, created = await add_product_to_user(session, user, product)
            # чтобы отдать группу/поля из свежей связи
            up = await get_user_product(session, user.id, product.id)

            if created:
                added += 1
                status_str = "added"
            else:
                already += 1
                status_str = "already"

            result_items.append(
                AddProductResultItem(nm_id=nm_id, status=status_str, product=_to_product_out(up))
            )

        out = AddProductsOut(added=added, already=already, failed=failed, items=result_items)
        if truncated:
            # Не критично, но фронт может показать предупреждение через отдельное поле —
            # проще всего прокинуть через заголовок в будущем; пока просто логируем.
            logger.info(f"[WebApp] user={tg_user.id}: список товаров обрезан лимитом")
        return out


@router.get("/products/{product_id}", response_model=ProductDetailOut)
async def api_get_product(
    product_id: int, tg_user: TelegramUser = Depends(get_current_telegram_user)
):
    async with async_session() as session:
        user = await get_or_create_user(
            session,
            telegram_id=tg_user.id,
            username=tg_user.username,
            full_name=tg_user.full_name,
        )
        up = await get_user_product(session, user.id, product_id)
        if not up:
            raise HTTPException(status_code=404, detail="Товар не найден в твоём списке")

        history = await get_product_history(session, product_id, limit=60)
        history_out = [
            HistoryPointOut(
                price=h.price,
                price_without_discount=h.price_without_discount,
                discount_percent=h.discount_percent,
                stock=h.stock,
                rating=h.rating,
                feedbacks_count=h.feedbacks_count,
                is_available=h.is_available,
                recorded_at=h.recorded_at,
            )
            for h in reversed(history)  # отдаём от старых к новым — удобно для графика
        ]

        product_out = _to_product_out(up)
        if len(history) >= 2:
            newest, prev = history[0], history[1]
            if newest.price is not None and prev.price is not None:
                product_out.price_change_abs = round(newest.price - prev.price, 2)
                if prev.price:
                    product_out.price_change_percent = round(
                        (newest.price - prev.price) / prev.price * 100, 2
                    )

        return ProductDetailOut(product=product_out, history=history_out)


@router.patch("/products/{product_id}", response_model=ProductOut)
async def api_update_product_settings(
    product_id: int,
    body: ProductSettingsIn,
    tg_user: TelegramUser = Depends(get_current_telegram_user),
):
    async with async_session() as session:
        user = await get_or_create_user(
            session,
            telegram_id=tg_user.id,
            username=tg_user.username,
            full_name=tg_user.full_name,
        )
        # exclude_unset — а не "убрать None": позволяет явно ОБНУЛИТЬ порог
        # (пользователь стёр значение в поле и сохранил), но не трогает поля,
        # которых вообще не было в теле запроса.
        fields = body.model_dump(exclude_unset=True)
        if not fields:
            raise HTTPException(status_code=400, detail="Нечего обновлять")

        up = await update_user_product_settings(session, user.id, product_id, fields)
        if not up:
            raise HTTPException(status_code=404, detail="Товар не найден в твоём списке")
        up = await get_user_product(session, user.id, product_id)
        return _to_product_out(up)


@router.post("/products/{product_id}/pause", response_model=ProductOut)
async def api_pause_product(
    product_id: int, tg_user: TelegramUser = Depends(get_current_telegram_user)
):
    async with async_session() as session:
        user = await get_or_create_user(
            session,
            telegram_id=tg_user.id,
            username=tg_user.username,
            full_name=tg_user.full_name,
        )
        current = await get_user_product(session, user.id, product_id)
        if not current:
            raise HTTPException(status_code=404, detail="Товар не найден в твоём списке")
        up = await set_user_product_paused(session, user.id, product_id, not current.is_paused)
        up = await get_user_product(session, user.id, product_id)
        return _to_product_out(up)


@router.delete("/products/{product_id}")
async def api_delete_product(
    product_id: int, tg_user: TelegramUser = Depends(get_current_telegram_user)
):
    async with async_session() as session:
        user = await get_or_create_user(
            session,
            telegram_id=tg_user.id,
            username=tg_user.username,
            full_name=tg_user.full_name,
        )
        ok = await remove_user_product(session, user.id, product_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Товар не найден в твоём списке")
        return {"ok": True}


@router.get("/fields", response_model=List[FieldOut])
async def api_get_fields(tg_user: TelegramUser = Depends(get_current_telegram_user)):
    return [FieldOut(key=key, label=label) for key, label in EXCEL_FIELDS]


@router.post("/export")
async def api_export(body: ExportIn, tg_user: TelegramUser = Depends(get_current_telegram_user)):
    if not body.product_ids:
        raise HTTPException(status_code=400, detail="Не выбрано ни одного товара")
    if not body.fields:
        raise HTTPException(status_code=400, detail="Не выбрано ни одного поля")

    async with async_session() as session:
        user = await get_or_create_user(
            session,
            telegram_id=tg_user.id,
            username=tg_user.username,
            full_name=tg_user.full_name,
        )
        products = await get_user_products_by_ids(session, user.id, body.product_ids)
        if not products:
            raise HTTPException(status_code=404, detail="Товары не найдены")

        path = build_excel_report(products, body.fields)

    filename = f"wb_monitor_{tg_user.id}.xlsx"
    return FileResponse(
        path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        background=_cleanup_file_task(path),
    )


def _cleanup_file_task(path: str):
    from starlette.background import BackgroundTask

    def _remove():
        try:
            os.remove(path)
        except OSError:
            pass

    return BackgroundTask(_remove)
