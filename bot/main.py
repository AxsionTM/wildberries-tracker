import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from bot.config import settings
from bot.database.session import init_db
from bot.handlers import start, products
from bot.services.monitor import run_monitoring_cycle

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_bot(token: str) -> Bot:
    """Совместимость со старыми и новыми версиями aiogram 3.x"""
    try:
        # aiogram >= 3.7
        from aiogram.client.default import DefaultBotProperties
        return Bot(
            token=token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
    except ImportError:
        # aiogram < 3.7
        return Bot(token=token, parse_mode=ParseMode.HTML)


async def main() -> None:
    await init_db()
    logger.info("Database initialized")

    bot = create_bot(settings.BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    dp.include_router(start.router)
    dp.include_router(products.router)

    scheduler = AsyncIOScheduler()
    interval_minutes = settings.DEFAULT_UPDATE_INTERVAL_MINUTES

    scheduler.add_job(
        run_monitoring_cycle,
        trigger=IntervalTrigger(minutes=interval_minutes),
        args=[bot],
        id="wb_monitoring",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info(f"Scheduler started. Monitoring every {interval_minutes} minutes")

    logger.info("Bot starting...")
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")
