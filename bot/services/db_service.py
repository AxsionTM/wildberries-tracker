import logging
from typing import Optional, List
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.database.models import User, Product, ProductHistory, UserProduct, Group
from bot.config import settings

logger = logging.getLogger(__name__)


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: Optional[str] = None,
    full_name: Optional[str] = None,
) -> User:
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        is_admin = telegram_id in settings.admin_ids_list
        user = User(
            telegram_id=telegram_id,
            username=username,
            full_name=full_name,
            is_admin=is_admin,
            max_products=settings.MAX_PRODUCTS_PER_USER,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    else:
        # Обновляем имя/username если изменились
        updated = False
        if username and user.username != username:
            user.username = username
            updated = True
        if full_name and user.full_name != full_name:
            user.full_name = full_name
            updated = True
        if updated:
            await session.commit()
            await session.refresh(user)

    return user


async def get_user_products_count(session: AsyncSession, user_id: int) -> int:
    result = await session.execute(
        select(func.count(UserProduct.id)).where(UserProduct.user_id == user_id)
    )
    return result.scalar() or 0


async def get_or_create_product(session: AsyncSession, data: dict) -> Product:
    """Создаёт или обновляет товар по данным парсера"""
    result = await session.execute(
        select(Product).where(Product.nm_id == data["nm_id"])
    )
    product = result.scalar_one_or_none()

    if product is None:
        if data.get("current_price") is None:
            logger.warning(
                f"[DB] nm_id={data.get('nm_id')}: создаю новый товар без цены "
                f"(парсер не смог получить цену при первом добавлении)"
            )
        product = Product(
            nm_id=data["nm_id"],
            name=data.get("name"),
            brand=data.get("brand"),
            category=data.get("category"),
            seller=data.get("seller"),
            url=data.get("url"),
            current_price=data.get("current_price"),
            price_without_discount=data.get("price_without_discount"),
            discount_percent=data.get("discount_percent"),
            stock=data.get("stock"),
            rating=data.get("rating"),
            feedbacks_count=data.get("feedbacks_count"),
            questions_count=data.get("questions_count"),
            is_in_promo=data.get("is_in_promo", False),
            is_available=data.get("is_available", True),
            last_updated=data.get("last_updated") or datetime.now(timezone.utc),
        )
        session.add(product)
        await session.flush()  # чтобы получить id
    else:
        # Обновляем текущие данные.
        #
        # ВАЖНО про цену: раньше поле current_price перезаписывалось значением
        # data.get("current_price") безусловно. Если парсер получал ошибку/пустую
        # цену (например, страница WB временно отдала товар без цены), data["current_price"]
        # оказывался None — и он молча затирал последнюю КОРРЕКТНУЮ сохранённую цену
        # (1499 → None). После этого следующее реальное изменение цены сравнивалось
        # бы уже не со старой ценой, а с "дырой", и уведомление могло не отправиться
        # или отправиться с некорректным "было".
        #
        # Теперь: если новых данных о цене нет — старое значение в БД не трогаем.
        if data.get("current_price") is not None:
            product.current_price = data["current_price"]
        else:
            logger.warning(
                f"[DB] nm_id={product.nm_id}: новая цена не получена "
                f"(парсер вернул None), сохраняю предыдущее значение "
                f"current_price={product.current_price}"
            )

        if data.get("price_without_discount") is not None:
            product.price_without_discount = data["price_without_discount"]
        if data.get("discount_percent") is not None:
            product.discount_percent = data["discount_percent"]

        product.name = data.get("name") or product.name
        product.brand = data.get("brand") or product.brand
        product.category = data.get("category") or product.category
        product.seller = data.get("seller") or product.seller
        product.url = data.get("url") or product.url
        product.stock = data.get("stock")
        product.rating = data.get("rating")
        product.feedbacks_count = data.get("feedbacks_count")
        product.questions_count = data.get("questions_count")
        product.is_in_promo = data.get("is_in_promo", False)
        product.is_available = data.get("is_available", True)
        product.last_updated = data.get("last_updated") or datetime.now(timezone.utc)

    # Всегда пишем историю — но ЦЕНОВЫЕ поля берём из уже смёрженного product,
    # а не из сырого data. Иначе при неудачном парсинге цены (data["current_price"] is None)
    # в историю попадала бы запись price=None, хотя реальная (сохранённая) цена товара
    # не менялась — это искажало бы график/историю цен.
    history = ProductHistory(
        product_id=product.id,
        price=product.current_price,
        price_without_discount=product.price_without_discount,
        discount_percent=product.discount_percent,
        stock=data.get("stock"),
        rating=data.get("rating"),
        feedbacks_count=data.get("feedbacks_count"),
        questions_count=data.get("questions_count"),
        is_in_promo=data.get("is_in_promo", False),
        is_available=data.get("is_available", True),
        recorded_at=data.get("last_updated") or datetime.now(timezone.utc),
    )
    session.add(history)

    await session.commit()
    await session.refresh(product)
    return product


async def add_product_to_user(
    session: AsyncSession,
    user: User,
    product: Product,
    group_id: Optional[int] = None,
) -> tuple[UserProduct, bool]:
    """
    Добавляет товар пользователю.
    Возвращает (UserProduct, created: bool)
    """
    result = await session.execute(
        select(UserProduct).where(
            UserProduct.user_id == user.id,
            UserProduct.product_id == product.id,
        )
    )
    user_product = result.scalar_one_or_none()

    if user_product:
        # Уже есть — просто активируем
        user_product.is_active = True
        user_product.is_paused = False
        await session.commit()
        await session.refresh(user_product)
        return user_product, False

    user_product = UserProduct(
        user_id=user.id,
        product_id=product.id,
        group_id=group_id,
        is_active=True,
        is_paused=False,
    )
    session.add(user_product)
    await session.commit()
    await session.refresh(user_product)
    return user_product, True


async def get_user_products(
    session: AsyncSession,
    user_id: int,
    only_active: bool = False,
) -> List[UserProduct]:
    query = (
        select(UserProduct)
        .where(UserProduct.user_id == user_id)
        .options(
            selectinload(UserProduct.product),
            selectinload(UserProduct.group),
        )
        .order_by(UserProduct.created_at.desc())
    )
    if only_active:
        query = query.where(UserProduct.is_active == True, UserProduct.is_paused == False)

    result = await session.execute(query)
    return list(result.scalars().all())


async def get_user_product(
    session: AsyncSession,
    user_id: int,
    product_id: int,
) -> Optional[UserProduct]:
    result = await session.execute(
        select(UserProduct)
        .where(UserProduct.user_id == user_id, UserProduct.product_id == product_id)
        # group тоже подгружаем заранее (eager load) — иначе обращение к
        # user_product.group вне активной сессии/в async-контексте без await
        # упадёт с MissingGreenlet (ленивая подгрузка синхронно не работает
        # в asyncio-сессии SQLAlchemy).
        .options(selectinload(UserProduct.product), selectinload(UserProduct.group))
    )
    return result.scalar_one_or_none()


async def get_user_products_page(
    session: AsyncSession,
    user_id: int,
    page: int = 0,
    per_page: int = 6,
) -> tuple[List[UserProduct], int]:
    """
    Постраничная выборка товаров пользователя ПРЯМО НА УРОВНЕ БАЗЫ (LIMIT/OFFSET),
    чтобы не тянуть из базы разом все товары пользователя — так бот не тормозит
    и не грузит сервер, даже если у пользователя сотни товаров.
    Возвращает (товары_на_странице, всего_товаров).
    """
    count_result = await session.execute(
        select(func.count(UserProduct.id)).where(UserProduct.user_id == user_id)
    )
    total = count_result.scalar() or 0

    result = await session.execute(
        select(UserProduct)
        .where(UserProduct.user_id == user_id)
        .options(
            selectinload(UserProduct.product),
            selectinload(UserProduct.group),
        )
        .order_by(UserProduct.created_at.desc())
        .limit(per_page)
        .offset(page * per_page)
    )
    items = list(result.scalars().all())
    return items, total


async def get_all_user_product_ids(session: AsyncSession, user_id: int) -> List[int]:
    """Только id товаров пользователя (для экрана выбора товаров в Excel-отчёте)."""
    result = await session.execute(
        select(UserProduct.product_id).where(UserProduct.user_id == user_id)
    )
    return [row[0] for row in result.all()]


async def get_product_history(
    session: AsyncSession,
    product_id: int,
    limit: int = 30,
) -> List[ProductHistory]:
    """Последние записи истории цен/показателей товара, от новых к старым."""
    result = await session.execute(
        select(ProductHistory)
        .where(ProductHistory.product_id == product_id)
        .order_by(ProductHistory.recorded_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_product_by_nm_id(session: AsyncSession, nm_id: int) -> Optional[Product]:
    """Найти товар по артикулу WB (для тестовой команды /simulate_price)."""
    result = await session.execute(select(Product).where(Product.nm_id == nm_id))
    return result.scalar_one_or_none()


async def get_user_products_by_ids(
    session: AsyncSession, user_id: int, product_ids: List[int]
) -> List[Product]:
    """Товары пользователя (Product), отфильтрованные по списку id — для Excel-отчёта."""
    if not product_ids:
        return []
    result = await session.execute(
        select(Product)
        .join(UserProduct, UserProduct.product_id == Product.id)
        .where(UserProduct.user_id == user_id, Product.id.in_(product_ids))
        .order_by(UserProduct.created_at.desc())
    )
    return list(result.scalars().unique().all())


async def set_user_notifications_enabled(
    session: AsyncSession, user: User, enabled: bool
) -> None:
    """Глобальный вкл/выкл уведомлений по ВСЕМ товарам пользователя (кнопка в главном меню)."""
    user.notifications_enabled = enabled
    await session.commit()


async def set_user_product_notifications_enabled(
    session: AsyncSession, user_id: int, product_id: int, enabled: bool
) -> Optional[UserProduct]:
    """Вкл/выкл уведомлений по ОДНОМУ товару (кнопка «🔔 Уведомления» в карточке товара)."""
    result = await session.execute(
        select(UserProduct)
        .where(UserProduct.user_id == user_id, UserProduct.product_id == product_id)
        .options(selectinload(UserProduct.product))
    )
    up = result.scalar_one_or_none()
    if up:
        up.notifications_enabled = enabled
        await session.commit()
        await session.refresh(up, attribute_names=["notifications_enabled"])
    return up


async def set_user_product_paused(
    session: AsyncSession, user_id: int, product_id: int, paused: bool
) -> Optional[UserProduct]:
    """Ставит/снимает товар с паузы мониторинга (используется мини-приложением)."""
    result = await session.execute(
        select(UserProduct)
        .where(UserProduct.user_id == user_id, UserProduct.product_id == product_id)
        .options(selectinload(UserProduct.product))
    )
    up = result.scalar_one_or_none()
    if up:
        up.is_paused = paused
        await session.commit()
        await session.refresh(up, attribute_names=["is_paused"])
    return up


# Поля UserProduct, которые разрешено менять через API мини-приложения.
# Белый список — чтобы через API нельзя было случайно/умышленно перезаписать
# служебные поля (id, user_id, product_id, created_at и т.п.).
_ALLOWED_USER_PRODUCT_SETTINGS = {
    "notifications_enabled",
    "is_paused",
    "notify_price_drop",
    "notify_price_rise",
    "price_threshold_percent",
    "price_threshold_rub",
    "price_below",
    "price_above",
    "notify_stock_below",
    "notify_availability",
    "notify_rating_change",
    "notify_feedbacks_change",
    "notify_promo",
    "email_notifications",
}


async def update_user_product_settings(
    session: AsyncSession, user_id: int, product_id: int, fields: dict
) -> Optional[UserProduct]:
    """Точечно обновляет настройки уведомлений товара (мини-приложение)."""
    result = await session.execute(
        select(UserProduct)
        .where(UserProduct.user_id == user_id, UserProduct.product_id == product_id)
        .options(selectinload(UserProduct.product))
    )
    up = result.scalar_one_or_none()
    if not up:
        return None

    changed = []
    for key, value in fields.items():
        if key in _ALLOWED_USER_PRODUCT_SETTINGS and hasattr(up, key):
            setattr(up, key, value)
            changed.append(key)

    if changed:
        await session.commit()
        await session.refresh(up)
    return up


async def remove_user_product(session: AsyncSession, user_id: int, product_id: int) -> bool:
    """Полностью убирает товар из списка пользователя (мониторинг товара для остальных не трогает)."""
    result = await session.execute(
        select(UserProduct).where(
            UserProduct.user_id == user_id, UserProduct.product_id == product_id
        )
    )
    up = result.scalar_one_or_none()
    if not up:
        return False
    await session.delete(up)
    await session.commit()
    return True
