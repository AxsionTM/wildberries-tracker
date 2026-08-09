"""
Тест парсера Wildberries.
    python test_parser.py
    python test_parser.py 816758849
"""

import sys
import asyncio
from bot.services.parser import parse_and_get_info, extract_nm_id


async def main():
    if len(sys.argv) > 1:
        nm_id = extract_nm_id(sys.argv[1])
        if not nm_id:
            print(f"Не удалось извлечь артикул из: {sys.argv[1]}")
            return
    else:
        nm_id = 816758849

    print(f"Пробую артикул: {nm_id}")
    print("-" * 50)

    data = await parse_and_get_info(nm_id)

    if not data:
        print("ОШИБКА: данные не получены")
        return

    print("УСПЕХ!\n")
    print(f"  Название:        {data.get('name')}")
    print(f"  Бренд:           {data.get('brand')}")
    print(f"  Продавец:        {data.get('seller')}")
    print(f"  Цена:            {data.get('current_price')} ₽")
    print(f"  Без скидки:      {data.get('price_without_discount')} ₽")
    print(f"  Скидка:          {data.get('discount_percent')} %")
    print(f"  Остаток:         {data.get('stock')}")
    print(f"  Рейтинг:         {data.get('rating')}")
    print(f"  Отзывы:          {data.get('feedbacks_count')}")
    print(f"  В наличии:       {data.get('is_available')}")
    print("-" * 50)

    if data.get("current_price") is not None:
        print("Парсер работает — цена получена!")
    else:
        print("Цена не получена, но базовые данные есть.")


if __name__ == "__main__":
    asyncio.run(main())
