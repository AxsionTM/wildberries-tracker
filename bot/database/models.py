from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    BigInteger, String, Integer, Float, Boolean, Text,
    DateTime, ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    max_products: Mapped[int] = mapped_column(Integer, default=50)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user_products: Mapped[List["UserProduct"]] = relationship(
        "UserProduct", back_populates="user", cascade="all, delete-orphan"
    )
    groups: Mapped[List["Group"]] = relationship(
        "Group", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User telegram_id={self.telegram_id} username={self.username}>"


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="groups")
    user_products: Mapped[List["UserProduct"]] = relationship("UserProduct", back_populates="group")

    def __repr__(self) -> str:
        return f"<Group id={self.id} name={self.name}>"


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nm_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)  # артикул WB
    name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    brand: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    seller: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Current data (обновляется парсером)
    current_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # цена со скидкой
    price_without_discount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    discount_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stock: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    feedbacks_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    questions_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_in_promo: Mapped[bool] = mapped_column(Boolean, default=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)

    last_updated: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    history: Mapped[List["ProductHistory"]] = relationship(
        "ProductHistory", back_populates="product", cascade="all, delete-orphan"
    )
    user_products: Mapped[List["UserProduct"]] = relationship(
        "UserProduct", back_populates="product", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Product nm_id={self.nm_id} name={self.name}>"


class ProductHistory(Base):
    __tablename__ = "product_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)

    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_without_discount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    discount_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stock: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    feedbacks_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    questions_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_in_promo: Mapped[bool] = mapped_column(Boolean, default=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)

    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    product: Mapped["Product"] = relationship("Product", back_populates="history")

    def __repr__(self) -> str:
        return f"<ProductHistory product_id={self.product_id} price={self.price} at={self.recorded_at}>"


class UserProduct(Base):
    """Связь пользователя с товаром + настройки уведомлений"""
    __tablename__ = "user_products"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_user_product"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    group_id: Mapped[Optional[int]] = mapped_column(ForeignKey("groups.id", ondelete="SET NULL"), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # мониторинг включён
    is_paused: Mapped[bool] = mapped_column(Boolean, default=False)

    # Настройки уведомлений
    notify_price_drop: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_price_rise: Mapped[bool] = mapped_column(Boolean, default=False)
    price_threshold_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # % изменения
    price_threshold_rub: Mapped[Optional[float]] = mapped_column(Float, nullable=True)      # ₽ изменения
    price_below: Mapped[Optional[float]] = mapped_column(Float, nullable=True)              # цена ниже
    price_above: Mapped[Optional[float]] = mapped_column(Float, nullable=True)              # цена выше
    notify_stock_below: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    notify_availability: Mapped[bool] = mapped_column(Boolean, default=True)                # появился/исчез
    notify_rating_change: Mapped[bool] = mapped_column(Boolean, default=False)
    notify_feedbacks_change: Mapped[bool] = mapped_column(Boolean, default=False)
    notify_promo: Mapped[bool] = mapped_column(Boolean, default=True)

    # Email уведомления
    email_notifications: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship("User", back_populates="user_products")
    product: Mapped["Product"] = relationship("Product", back_populates="user_products")
    group: Mapped[Optional["Group"]] = relationship("Group", back_populates="user_products")

    def __repr__(self) -> str:
        return f"<UserProduct user_id={self.user_id} product_id={self.product_id}>"


class NotificationLog(Base):
    __tablename__ = "notifications_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    notification_type: Mapped[str] = mapped_column(String(50), nullable=False)  # price_drop, stock, etc.
    message: Mapped[str] = mapped_column(Text, nullable=False)
    sent_to_telegram: Mapped[bool] = mapped_column(Boolean, default=False)
    sent_to_email: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<NotificationLog id={self.id} type={self.notification_type}>"
