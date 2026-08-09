import asyncio
import logging

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import MenuButtonWebApp, WebAppInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from bot.config import settings
from bot.database.session import init_db
from bot.handlers import start, products, excel
from bot.services.monitor import run_monitoring_cycle
from bot.webapp.app import app as webapp_app

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


async def run_webapp_server() -> None:
    """Запускает HTTP-сервер мини-приложения (FastAPI) внутри того же event loop,
    что и бот. Если WEBAPP_URL не задан в .env — сервер не поднимаем вообще,
    бот продолжает работать как раньше (только чат-интерфейс)."""
    if not settings.WEBAPP_URL:
        logger.info(
            "WEBAPP_URL не задан в .env — мини-приложение отключено, "
            "работает только обычный интерфейс бота"
        )
        return

    config = uvicorn.Config(
        webapp_app,
        host=settings.WEBAPP_HOST,
        port=settings.WEBAPP_PORT,
        log_level="info",
        loop="asyncio",
    )
    server = uvicorn.Server(config)
    logger.info(
        f"Mini App сервер запускается на {settings.WEBAPP_HOST}:{settings.WEBAPP_PORT} "
        f"(публичный адрес: {settings.WEBAPP_URL})"
    )
    await server.serve()


async def setup_menu_button(bot: Bot) -> None:
    """Показывает кнопку 'Открыть приложение' рядом с полем ввода сообщения в Telegram."""
    if not settings.WEBAPP_URL:
        return
    try:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Открыть приложение",
                web_app=WebAppInfo(url=settings.WEBAPP_URL),
            )
        )
        logger.info("Menu Button мини-приложения установлена")
    except Exception as e:
        logger.warning(f"Не удалось установить Menu Button мини-приложения: {e}")


async def main() -> None:
    await init_db()
    logger.info("Database initialized")

    bot = create_bot(settings.BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    dp.include_router(start.router)
    dp.include_router(products.router)
    dp.include_router(excel.router)

    await setup_menu_button(bot)

    scheduler = AsyncIOScheduler()
    interval_seconds = settings.DEFAULT_UPDATE_INTERVAL_SECONDS

    # WB не предоставляет push-события (WebSocket/SSE/webhook) об изменении цены,
    # поэтому мы вынуждены опрашивать её по расписанию (polling). Чтобы обнаруживать
    # изменения максимально быстро без "while True + sleep(1)":
    #   - интервал измеряется в секундах, а не в минутах/часах;
    #   - max_instances=1 + coalesce=True гарантируют, что для одного и того же товара
    #     никогда не будет запущено два параллельных цикла опроса одновременно —
    #     следующий цикл не стартует, пока не завершился предыдущий;
    #   - внутри одного цикла товары опрашиваются параллельно (см. monitor.py),
    #     поэтому задержка обнаружения не растёт линейно с числом товаров.
    scheduler.add_job(
        run_monitoring_cycle,
        trigger=IntervalTrigger(seconds=interval_seconds),
        args=[bot],
        id="wb_monitoring",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info(f"Scheduler started. Monitoring every {interval_seconds} seconds")

    logger.info("Bot starting...")
    try:
        # Бот (long polling) и веб-сервер мини-приложения работают одновременно
        # в одном event loop. Если WEBAPP_URL не задан, run_webapp_server()
        # сразу же завершается и мешать боту не будет.
        await asyncio.gather(
            dp.start_polling(bot),
            run_webapp_server(),
        )
    finally:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")
