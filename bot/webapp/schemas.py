"""Pydantic-схемы ответов/тела запросов REST API мини-приложения."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class MeOut(BaseModel):
    telegram_id: int
    username: Optional[str] = None
    full_name: Optional[str] = None
    notifications_enabled: bool
    products_count: int
    max_products: int


class MeUpdateIn(BaseModel):
    notifications_enabled: bool


class ProductOut(BaseModel):
    id: int
    nm_id: int
    name: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    seller: Optional[str] = None
    url: Optional[str] = None
    current_price: Optional[float] = None
    price_without_discount: Optional[float] = None
    discount_percent: Optional[float] = None
    stock: Optional[int] = None
    rating: Optional[float] = None
    feedbacks_count: Optional[int] = None
    questions_count: Optional[int] = None
    is_in_promo: bool = False
    is_available: bool = True
    last_updated: Optional[datetime] = None

    # Поля, специфичные для связи пользователь-товар
    is_paused: bool = False
    notifications_enabled: bool = True
    notify_price_drop: bool = True
    notify_price_rise: bool = False
    price_threshold_percent: Optional[float] = None
    price_threshold_rub: Optional[float] = None
    price_below: Optional[float] = None
    price_above: Optional[float] = None
    notify_stock_below: Optional[int] = None
    notify_availability: bool = True
    notify_rating_change: bool = False
    notify_feedbacks_change: bool = False
    notify_promo: bool = True
    group_name: Optional[str] = None

    # Изменение цены с прошлого сохранённого замера — удобно для стрелочки на карточке
    price_change_abs: Optional[float] = None
    price_change_percent: Optional[float] = None


class ProductsPageOut(BaseModel):
    items: List[ProductOut]
    total: int
    page: int
    per_page: int


class HistoryPointOut(BaseModel):
    price: Optional[float] = None
    price_without_discount: Optional[float] = None
    discount_percent: Optional[float] = None
    stock: Optional[int] = None
    rating: Optional[float] = None
    feedbacks_count: Optional[int] = None
    is_available: bool = True
    recorded_at: datetime


class ProductDetailOut(BaseModel):
    product: ProductOut
    history: List[HistoryPointOut]


class AddProductsIn(BaseModel):
    query: str = Field(..., description="Артикулы/ссылки WB, один на строку или через запятую")


class AddProductResultItem(BaseModel):
    nm_id: int
    status: str  # "added" | "already" | "failed"
    product: Optional[ProductOut] = None


class AddProductsOut(BaseModel):
    added: int
    already: int
    failed: int
    items: List[AddProductResultItem]


class ProductSettingsIn(BaseModel):
    is_paused: Optional[bool] = None
    notifications_enabled: Optional[bool] = None
    notify_price_drop: Optional[bool] = None
    notify_price_rise: Optional[bool] = None
    price_threshold_percent: Optional[float] = None
    price_threshold_rub: Optional[float] = None
    price_below: Optional[float] = None
    price_above: Optional[float] = None
    notify_stock_below: Optional[int] = None
    notify_availability: Optional[bool] = None
    notify_rating_change: Optional[bool] = None
    notify_feedbacks_change: Optional[bool] = None
    notify_promo: Optional[bool] = None


class FieldOut(BaseModel):
    key: str
    label: str


class ExportIn(BaseModel):
    product_ids: List[int]
    fields: List[str]
