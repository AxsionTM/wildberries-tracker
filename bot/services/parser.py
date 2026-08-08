import re
import random
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timezone

import httpx
from bot.config import settings


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) Gecko/20100101 Firefox/129.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
]


def extract_nm_id(text: str) -> Optional[int]:
    """Извлекает артикул (nm_id) из ссылки или чистого числа"""
    text = text.strip()

    # Чистый артикул
    if text.isdigit():
        return int(text)

    # Ссылки вида https://www.wildberries.ru/catalog/12345678/detail.aspx
    patterns = [
        r"/catalog/(\d+)",
        r"nm=(\d+)",
        r" артикул[:= ]*(\d+)",
        r"(\d{6,})",  # fallback — длинное число
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


async def fetch_product_data(nm_id: int, client: Optional[httpx.AsyncClient] = None) -> Optional[Dict[str, Any]]:
    """
    Парсит данные товара с публичного эндпоинта WB.
    Возвращает словарь с данными или None при ошибке.
    """
    url = f"https://card.wb.ru/cards/v4/detail?nm={nm_id}&curr=rub&dest=-1257786&spp=30"

    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Origin": "https://www.wildberries.ru",
        "Referer": f"https://www.wildberries.ru/catalog/{nm_id}/detail.aspx",
    }

    close_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=20.0, follow_redirects=True)
        close_client = True

    try:
        # Небольшая случайная задержка
        await asyncio.sleep(random.uniform(settings.PARSER_DELAY_MIN, settings.PARSER_DELAY_MAX))

        response = await client.get(url, headers=headers)

        if response.status_code != 200:
            print(f"[Parser] HTTP {response.status_code} for nm_id={nm_id}")
            return None

        data = response.json()

        products = data.get("data", {}).get("products", [])
        if not products:
            print(f"[Parser] No products found for nm_id={nm_id}")
            return None

        product = products[0]

        # Цена: WB отдаёт в копейках
        sale_price = product.get("salePriceU")  # цена со скидкой
        price = product.get("priceU")           # цена без скидки

        current_price = round(sale_price / 100, 2) if sale_price is not None else None
        price_without_discount = round(price / 100, 2) if price is not None else None

        discount_percent = None
        if current_price and price_without_discount and price_without_discount > 0:
            discount_percent = round((1 - current_price / price_without_discount) * 100, 1)

        # Остаток
        stock = 0
        sizes = product.get("sizes", [])
        for size in sizes:
            for stock_item in size.get("stocks", []):
                stock += stock_item.get("qty", 0)

        # Рейтинг и отзывы
        rating = product.get("reviewRating") or product.get("rating")
        feedbacks = product.get("feedbacks") or product.get("nmFeedbacks")
        questions = product.get("questionsCount") or 0

        # Бренд, название, продавец
        name = product.get("name")
        brand = product.get("brand")
        supplier = product.get("supplier") or product.get("supplierName")
        subject = product.get("subjectName") or product.get("entity")

        # Акции (упрощённо)
        is_in_promo = bool(product.get("promoTextCard") or product.get("panelPromoId"))

        result = {
            "nm_id": nm_id,
            "name": name,
            "brand": brand,
            "category": subject,
            "seller": supplier,
            "url": f"https://www.wildberries.ru/catalog/{nm_id}/detail.aspx",
            "current_price": current_price,
            "price_without_discount": price_without_discount,
            "discount_percent": discount_percent,
            "stock": stock if stock > 0 else None,
            "rating": float(rating) if rating is not None else None,
            "feedbacks_count": int(feedbacks) if feedbacks is not None else None,
            "questions_count": int(questions) if questions is not None else 0,
            "is_in_promo": is_in_promo,
            "is_available": stock > 0 if stock is not None else True,
            "last_updated": datetime.now(timezone.utc),
            "raw": product,  # на всякий случай
        }
        return result

    except httpx.TimeoutException:
        print(f"[Parser] Timeout for nm_id={nm_id}")
        return None
    except Exception as e:
        print(f"[Parser] Error for nm_id={nm_id}: {e}")
        return None
    finally:
        if close_client:
            await client.aclose()


async def parse_and_get_info(nm_id: int) -> Optional[Dict[str, Any]]:
    """Удобная обёртка"""
    return await fetch_product_data(nm_id)
