"""
Парсер Wildberries — рабочий вариант на основе проверенного кода.
"""

import re
import random
import asyncio
import logging
from decimal import Decimal, InvalidOperation
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

import requests
from bot.config import settings

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
]


def extract_nm_id(text: str) -> Optional[int]:
    """Извлекает артикул из текста или ссылки"""
    text = text.strip()
    if text.isdigit():
        return int(text)

    match = re.search(r"/catalog/(\d+)", text)
    if match:
        return int(match.group(1))

    match = re.search(r"(\d{6,})", text)
    if match:
        return int(match.group(1))

    return None


def _get_product_sync(nm_id: int) -> Optional[Dict[str, Any]]:
    """
    Синхронный запрос к WB (как в рабочем мини-боте).
    Вызывается через asyncio.to_thread.
    """
    url = (
        "https://card.wb.ru/cards/v4/detail"
        f"?nm={nm_id}"
        "&dest=-1257786"
        "&curr=rub"
        "&locale=ru"
    )

    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code != 200:
            logger.warning(f"[Parser] HTTP {response.status_code} nm={nm_id}")
            return None

        data = response.json()

        # В рабочем боте products лежат на верхнем уровне
        products = data.get("products") or []
        if not products:
            # запасной вариант старой структуры
            products = data.get("data", {}).get("products") or []

        if not products:
            logger.warning(f"[Parser] products empty nm={nm_id}")
            return None

        product = products[0]
        return _parse_product(product, nm_id)

    except requests.Timeout:
        logger.warning(f"[Parser] timeout nm={nm_id}")
        return None
    except Exception as e:
        logger.error(f"[Parser] error nm={nm_id}: {e}")
        return None


def _kopecks_to_rub(value: Any) -> Optional[float]:
    """
    Нормализует цену, полученную от WB (число в копейках), в рубли.

    Почему через Decimal, а не просто value / 100:
    обычное деление float может давать погрешности представления
    (например 0.1 + 0.2 != 0.3 в float), а для денег это недопустимо —
    из-за этого сравнение старой и новой цены могло изредка "видеть"
    несуществующее изменение на доли копейки. Decimal + quantize даёт
    точное и предсказуемое значение с 2 знаками после запятой.

    Возвращает None (а не 0 и не какое-то произвольное число), если:
      - значения нет вовсе;
      - значение не является числом;
      - значение <= 0 (цена не может быть нулевой или отрицательной —
        это признак некорректного/неполного ответа WB, а не реальная цена).
    """
    if value is None:
        return None
    try:
        kopecks = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        logger.warning(f"[Parser] Цена не является числом: {value!r}")
        return None
    if kopecks <= 0:
        logger.warning(f"[Parser] Некорректная цена (<= 0): {value!r}")
        return None
    rub = (kopecks / Decimal(100)).quantize(Decimal("0.01"))
    return float(rub)


def _select_price_data(sizes: List[dict]) -> dict:
    """
    Выбирает объект price из первого варианта (size), где он реально
    присутствует.

    Раньше цена бралась только из sizes[0], а WB иногда отдаёт для
    первого варианта (например, для размера/цвета, которого сейчас нет
    в наличии) пустой объект price: {} — при этом у ДРУГИХ вариантов
    того же товара цена в ответе есть. Из-за этого current_price
    становился None, хотя реальная цена товара была известна.
    """
    for size in sizes:
        price_data = size.get("price") or {}
        if price_data.get("product") is not None or price_data.get("basic") is not None:
            return price_data
    return {}


def _parse_product(product: dict, nm_id: int) -> Dict[str, Any]:
    """Разбор товара — цена из sizes[].price (актуальный формат)"""

    name = product.get("name")
    brand = product.get("brand")
    supplier = product.get("supplier") or product.get("supplierName")
    supplier_rating = product.get("supplierRating")
    rating = product.get("reviewRating") or product.get("rating")
    feedbacks = product.get("feedbacks") or product.get("nmFeedbacks")
    questions = product.get("questionsCount") or 0
    subject = product.get("subjectName") or product.get("entity")

    discount = None
    stock = 0

    sizes = product.get("sizes") or []
    price_data = _select_price_data(sizes)

    current_price = _kopecks_to_rub(price_data.get("product"))
    basic_price = _kopecks_to_rub(price_data.get("basic"))

    # Запасной старый формат ("salePriceU"/"priceU" на верхнем уровне товара).
    # ВАЖНО: этот фолбэк раньше был случайно вложен внутрь `if sizes:`, из-за
    # чего не срабатывал вообще, если WB возвращал товар без массива sizes —
    # цена в этом случае терялась (current_price оставался None), хотя старый
    # формат цены в ответе присутствовал. Теперь фолбэк применяется всегда,
    # когда основной (новый) формат не дал результата — независимо от sizes.
    if current_price is None:
        current_price = _kopecks_to_rub(product.get("salePriceU"))
    if basic_price is None:
        basic_price = _kopecks_to_rub(product.get("priceU"))

    if current_price is not None and basic_price and basic_price > 0:
        discount = round((1 - current_price / basic_price) * 100, 1)

    for size in sizes:
        for st in size.get("stocks") or []:
            stock += st.get("qty", 0)

    if stock == 0 and product.get("totalQuantity") is not None:
        stock = int(product["totalQuantity"])

    is_in_promo = bool(
        product.get("promoTextCard")
        or product.get("panelPromoId")
        or product.get("promoTextCat")
    )

    return {
        "nm_id": nm_id,
        "name": name,
        "brand": brand,
        "category": subject,
        "seller": supplier,
        "seller_rating": float(supplier_rating) if supplier_rating is not None else None,
        "url": f"https://www.wildberries.ru/catalog/{nm_id}/detail.aspx",
        # current_price/basic_price уже нормализованы в _kopecks_to_rub — дополнительное
        # округление не нужно (и могло бы снова внести погрешность float).
        "current_price": current_price,
        "price_without_discount": basic_price,
        "discount_percent": discount,
        "stock": stock if stock > 0 else None,
        "rating": float(rating) if rating is not None else None,
        "feedbacks_count": int(feedbacks) if feedbacks is not None else None,
        "questions_count": int(questions) if questions is not None else 0,
        "is_in_promo": is_in_promo,
        "is_available": bool(stock and stock > 0),
        "last_updated": datetime.now(timezone.utc),
    }


async def fetch_product_data(nm_id: int) -> Optional[Dict[str, Any]]:
    """Асинхронная обёртка"""
    await asyncio.sleep(random.uniform(settings.PARSER_DELAY_MIN, settings.PARSER_DELAY_MAX))
    result = await asyncio.to_thread(_get_product_sync, nm_id)
    if result and result.get("current_price") is not None:
        logger.info(f"[Parser] SUCCESS nm={nm_id} price={result['current_price']}")
    elif result:
        logger.warning(f"[Parser] PARTIAL nm={nm_id} name={result.get('name')}")
    else:
        logger.error(f"[Parser] FAIL nm={nm_id}")
    return result


async def parse_and_get_info(nm_id: int) -> Optional[Dict[str, Any]]:
    return await fetch_product_data(nm_id)
