from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from bot.config import settings
from bot.database.models import Base


engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# Колонки, которые могли отсутствовать в уже существующей базе (добавлены позже).
# Формат: {"таблица": [("колонка", "SQL-тип и default"), ...]}
_NEW_COLUMNS = {
    "users": [
        ("notifications_enabled", "BOOLEAN DEFAULT 1"),
    ],
    "user_products": [
        ("notifications_enabled", "BOOLEAN DEFAULT 1"),
    ],
}


async def _run_sqlite_migrations(conn) -> None:
    """Добавляет недостающие колонки в уже существующую SQLite базу (без потери данных)."""
    if not settings.DATABASE_URL.startswith("sqlite"):
        return
    for table, columns in _NEW_COLUMNS.items():
        result = await conn.execute(text(f"PRAGMA table_info({table})"))
        existing = {row[1] for row in result.fetchall()}
        for column_name, column_def in columns:
            if column_name not in existing:
                await conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {column_name} {column_def}")
                )


async def init_db() -> None:
    """Создание всех таблиц + миграция недостающих колонок в уже существующей базе"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _run_sqlite_migrations(conn)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
