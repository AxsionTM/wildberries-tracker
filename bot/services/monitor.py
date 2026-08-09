"""
Сервис автоматического мониторинга товаров.
Запускается по расписанию через APScheduler.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.session import async_session
from bot.database.models import Product, UserProduct, User, NotificationLog
from bot.services.parser import parse_and_get_info
from bot.services.db_service import get_or_create_product
from bot.config import settings

logger = logging.getLogger(__name__)


def _price_changed_significantly(
    old_price: Optional[float],
    new_price: Optional[float],
    threshold_rub: Optional[float],
    threshold_percent: Optional[float],
) -> tuple[bool, Optional[float], Optional[float]]:
    """
    Проверяет, изменилась ли цена достаточно сильно.
    Возвращает (changed, diff_rub, diff_percent)
    """
    if old_price is None or new_price is None:
        return False, None, None

    diff_rub = new_price - old_price
    if old_price == 0:
        diff_percent = 0.0
    else:
        diff_percent = (diff_rub / old_price) * 100

    # Если пользователь задал пороги — используем их
    if threshold_rub is not None and abs(diff_rub) >= threshold_rub:
        return True, diff_rub, diff_percent
    if threshold_percent is not None and abs(diff_percent) >= threshold_percent:
        return True, diff_rub, diff_percent

    # Если пороги не заданы — считаем любое изменение цены значимым
    if threshold_rub is None and threshold_percent is None:
        if abs(diff_rub) >= 1:  # хотя бы 1 рубль
            return True, diff_rub, diff_percent

    return False, diff_rub, diff_percent


def build_notification_messages(
    user_product: UserProduct,
    old_data: Dict[str, Any],
    new_data: Dict[str, Any],
) -> List[tuple[str, str]]:
    """
    Сравнивает старые и новые данные и возвращает список уведомлений.
    Каждый элемент: (notification_type, message_text)
    """
    messages = []
    product = user_product.product
    name = product.name or f"Артикул {product.nm_id}"
    url = product.url or f"https://www.wildberries.ru/catalog/{product.nm_id}/detail.aspx"

    old_price = old_data.get("current_price")
    new_price = new_data.get("current_price")
    old_stock = old_data.get("stock")
    new_stock = new_data.get("stock")
    old_available = old_data.get("is_available", True)
    new_available = new_data.get("is_available", True)
    old_promo = old_data.get("is_in_promo", False)
    new_promo = new_data.get("is_in_promo", False)
    old_rating = old_data.get("rating")
    new_rating = new_data.get("rating")
    old_feedbacks = old_data.get("feedbacks_count")
    new_feedbacks = new_data.get("feedbacks_count")

    # --- Цена ---
    changed, diff_rub, diff_percent = _price_changed_significantly(
        old_price,
        new_price,
        user_product.price_threshold_rub,
        user_product.price_threshold_percent,
    )

    if changed and diff_rub is not None:
        if diff_rub < 0 and user_product.notify_price_drop:
            msg = (
                f"📉 <b>Цена упала!</b>\n\n"
                f"<b>{name}</b>\n"
                f"🆔 <code>{product.nm_id}</code>\n\n"
                f"Было: <b>{old_price} ₽</b>\n"
                f"Стало: <b>{new_price} ₽</b>\n"
                f"Изменение: <b>{diff_rub:+.2f} ₽</b> ({diff_percent:+.1f}%)\n\n"
                f"<a href=\"{url}\">Открыть на WB</a>"
            )
            messages.append(("price_drop", msg))

        elif diff_rub > 0 and user_product.notify_price_rise:
            msg = (
                f"📈 <b>Цена выросла!</b>\n\n"
                f"<b>{name}</b>\n"
                f"🆔 <code>{product.nm_id}</code>\n\n"
                f"Было: <b>{old_price} ₽</b>\n"
                f"Стало: <b>{new_price} ₽</b>\n"
                f"Изменение: <b>{diff_rub:+.2f} ₽</b> ({diff_percent:+.1f}%)\n\n"
                f"<a href=\"{url}\">Открыть на WB</a>"
            )
            messages.append(("price_rise", msg))

    # Цена стала ниже заданного значения
    if (
        user_product.price_below is not None
        and new_price is not None
        and old_price is not None
        and new_price <= user_product.price_below < old_price
    ):
        msg = (
            f"⬇️ <b>Цена стала ниже {user_product.price_below} ₽</b>\n\n"
            f"<b>{name}</b>\n"
            f"🆔 <code>{product.nm_id}</code>\n\n"
            f"Текущая цена: <b>{new_price} ₽</b>\n\n"
            f"<a href=\"{url}\">Открыть на WB</a>"
        )
        messages.append(("price_below", msg))

    # Цена стала выше заданного значения
    if (
        user_product.price_above is not None
        and new_price is not None
        and old_price is not None
        and new_price >= user_product.price_above > old_price
    ):
        msg = (
            f"⬆️ <b>Цена стала выше {user_product.price_above} ₽</b>\n\n"
            f"<b>{name}</b>\n"
            f"🆔 <code>{product.nm_id}</code>\n\n"
            f"Текущая цена: <b>{new_price} ₽</b>\n\n"
            f"<a href=\"{url}\">Открыть на WB</a>"
        )
        messages.append(("price_above", msg))

    # --- Остаток ---
    if (
        user_product.notify_stock_below is not None
        and new_stock is not None
        and new_stock <= user_product.notify_stock_below
        and (old_stock is None or old_stock > user_product.notify_stock_below)
    ):
        msg = (
            f"📦 <b>Остаток стал меньше {user_product.notify_stock_below} шт.</b>\n\n"
            f"<b>{name}</b>\n"
            f"🆔 <code>{product.nm_id}</code>\n\n"
            f"Текущий остаток: <b>{new_stock} шт.</b>\n\n"
            f"<a href=\"{url}\">Открыть на WB</a>"
        )
        messages.append(("stock_below", msg))

    # --- Появление / исчезновение ---
    if user_product.notify_availability:
        if not old_available and new_available:
            msg = (
                f"✅ <b>Товар снова в наличии!</b>\n\n"
                f"<b>{name}</b>\n"
                f"🆔 <code>{product.nm_id}</code>\n\n"
                f"Цена: <b>{new_price} ₽</b>\n"
                f"Остаток: {new_stock or 'н/д'} шт.\n\n"
                f"<a href=\"{url}\">Открыть на WB</a>"
            )
            messages.append(("appeared", msg))
        elif old_available and not new_available:
            msg = (
                f"❌ <b>Товар пропал из наличия</b>\n\n"
                f"<b>{name}</b>\n"
                f"🆔 <code>{product.nm_id}</code>\n\n"
                f"<a href=\"{url}\">Открыть на WB</a>"
            )
            messages.append(("disappeared", msg))

    # --- Акция ---
    if user_product.notify_promo and not old_promo and new_promo:
        msg = (
            f"🔥 <b>Товар попал в акцию!</b>\n\n"
            f"<b>{name}</b>\n"
            f"🆔 <code>{product.nm_id}</code>\n\n"
            f"Цена: <b>{new_price} ₽</b>\n\n"
            f"<a href=\"{url}\">Открыть на WB</a>"
        )
        messages.append(("promo", msg))

    # --- Рейтинг ---
    if (
        user_product.notify_rating_change
        and old_rating is not None
        and new_rating is not None
        and abs(new_rating - old_rating) >= 0.1
    ):
        direction = "вырос" if new_rating > old_rating else "упал"
        msg = (
            f"⭐ <b>Рейтинг {direction}</b>\n\n"
            f"<b>{name}</b>\n"
            f"🆔 <code>{product.nm_id}</code>\n\n"
            f"Было: {old_rating} → Стало: <b>{new_rating}</b>\n\n"
            f"<a href=\"{url}\">Открыть на WB</a>"
        )
        messages.append(("rating_change", msg))

    # --- Количество отзывов ---
    if (
        user_product.notify_feedbacks_change
        and old_feedbacks is not None
        and new_feedbacks is not None
        and new_feedbacks != old_feedbacks
    ):
        msg = (
            f"💬 <b>Изменилось количество отзывов</b>\n\n"
            f"<b>{name}</b>\n"
            f"🆔 <code>{product.nm_id}</code>\n\n"
            f"Было: {old_feedbacks} → Стало: <b>{new_feedbacks}</b>\n\n"
            f"<a href=\"{url}\">Открыть на WB</a>"
        )
        messages.append(("feedbacks_change", msg))

    return messages


async def process_product(
    session: AsyncSession,
    product: Product,
    bot: Bot,
) -> int:
    """
    Обновляет один товар и рассылает уведомления подписанным пользователям.
    Возвращает количество отправленных уведомлений.
    """
    # Сохраняем старые данные до обновления
    old_data = {
        "current_price": product.current_price,
        "price_without_discount": product.price_without_discount,
        "discount_percent": product.discount_percent,
        "stock": product.stock,
        "rating": product.rating,
        "feedbacks_count": product.feedbacks_count,
        "questions_count": product.questions_count,
        "is_in_promo": product.is_in_promo,
        "is_available": product.is_available,
    }

    # Парсим свежие данные
    new_data = await parse_and_get_info(product.nm_id)
    if not new_data:
        logger.warning(f"Не удалось обновить товар nm_id={product.nm_id}")
        return 0

    # Обновляем товар + пишем историю
    updated_product = await get_or_create_product(session, new_data)

    # Получаем всех пользователей, которые следят за этим товаром
    result = await session.execute(
        select(UserProduct)
        .where(
            UserProduct.product_id == updated_product.id,
            UserProduct.is_active == True,
            UserProduct.is_paused == False,
        )
        .options(
            selectinload(UserProduct.user),
            selectinload(UserProduct.product),
        )
    )
    user_products = list(result.scalars().all())

    sent_count = 0

    for up in user_products:
        notifications = build_notification_messages(up, old_data, new_data)

        for notif_type, text in notifications:
            try:
                await bot.send_message(
                    chat_id=up.user.telegram_id,
                    text=text,
                    parse_mode="HTML",
                    disable_web_page_preview=False,
                )
                sent_count += 1

                # Логируем уведомление
                log = NotificationLog(
                    user_id=up.user.id,
                    product_id=updated_product.id,
                    notification_type=notif_type,
                    message=text,
                    sent_to_telegram=True,
                    sent_to_email=False,
                )
                session.add(log)

            except Exception as e:
                logger.error(
                    f"Не удалось отправить уведомление user={up.user.telegram_id} "
                    f"product={updated_product.nm_id}: {e}"
                )

    await session.commit()
    return sent_count


async def run_monitoring_cycle(bot: Bot) -> None:
    """
    Один полный цикл мониторинга всех активных товаров.
    """
    logger.info("🔄 Запуск цикла мониторинга...")

    async with async_session() as session:
        # Получаем все товары, у которых есть хотя бы один активный подписчик
        result = await session.execute(
            select(Product)
            .join(UserProduct)
            .where(
                UserProduct.is_active == True,
                UserProduct.is_paused == False,
            )
            .distinct()
        )
        products = list(result.scalars().all())

        if not products:
            logger.info("Нет активных товаров для мониторинга")
            return

        logger.info(f"Найдено {len(products)} товаров для обновления")

        total_notifications = 0
        success = 0
        failed = 0

        for product in products:
            try:
                sent = await process_product(session, product, bot)
                total_notifications += sent
                success += 1
            except Exception as e:
                failed += 1
                logger.error(f"Ошибка при обработке nm_id={product.nm_id}: {e}")

        logger.info(
            f"✅ Цикл завершён. Успешно: {success}, ошибок: {failed}, "
            f"уведомлений отправлено: {total_notifications}"
        )
