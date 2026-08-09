"""
Парсер Wildberries — рабочий вариант на основе проверенного кода.
"""

import re
import random
import asyncio
import logging
from typing import Optional, Dict, Any
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


def _parse_product(product: dict, nm_id: int) -> Dict[str, Any]:
    """Разбор товара — цена из sizes[0].price (актуальный формат)"""

    name = product.get("name")
    brand = product.get("brand")
    supplier = product.get("supplier") or product.get("supplierName")
    supplier_rating = product.get("supplierRating")
    rating = product.get("reviewRating") or product.get("rating")
    feedbacks = product.get("feedbacks") or product.get("nmFeedbacks")
    questions = product.get("questionsCount") or 0
    subject = product.get("subjectName") or product.get("entity")

    current_price = None
    basic_price = None
    discount = None
    stock = 0

    sizes = product.get("sizes") or []
    if sizes:
        price_data = sizes[0].get("price") or {}

        if price_data.get("product") is not None:
            current_price = price_data["product"] / 100
        if price_data.get("basic") is not None:
            basic_price = price_data["basic"] / 100

        # запасной старый формат
        if current_price is None and product.get("salePriceU") is not None:
            current_price = product["salePriceU"] / 100
        if basic_price is None and product.get("priceU") is not None:
            basic_price = product["priceU"] / 100

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
        "current_price": round(current_price, 2) if current_price is not None else None,
        "price_without_discount": round(basic_price, 2) if basic_price is not None else None,
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
