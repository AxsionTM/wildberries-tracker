from typing import Optional, List
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.database.models import User, Product, ProductHistory, UserProduct, Group
from bot.config import settings


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
        # Обновляем текущие данные
        product.name = data.get("name") or product.name
        product.brand = data.get("brand") or product.brand
        product.category = data.get("category") or product.category
        product.seller = data.get("seller") or product.seller
        product.url = data.get("url") or product.url
        product.current_price = data.get("current_price")
        product.price_without_discount = data.get("price_without_discount")
        product.discount_percent = data.get("discount_percent")
        product.stock = data.get("stock")
        product.rating = data.get("rating")
        product.feedbacks_count = data.get("feedbacks_count")
        product.questions_count = data.get("questions_count")
        product.is_in_promo = data.get("is_in_promo", False)
        product.is_available = data.get("is_available", True)
        product.last_updated = data.get("last_updated") or datetime.now(timezone.utc)

    # Всегда пишем историю
    history = ProductHistory(
        product_id=product.id,
        price=data.get("current_price"),
        price_without_discount=data.get("price_without_discount"),
        discount_percent=data.get("discount_percent"),
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
        .options(selectinload(UserProduct.product))
    )
    return result.scalar_one_or_none()
