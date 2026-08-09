from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    BOT_TOKEN: str
    ADMIN_IDS: str = ""

    DATABASE_URL: str = "sqlite+aiosqlite:///./wb_monitor.db"

    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""

    PARSER_DELAY_MIN: float = 1.0
    PARSER_DELAY_MAX: float = 3.0

    # Wildberries не отдаёт push-события об изменении цены (нет WebSocket/SSE/webhook
    # у публичного card.wb.ru API), поэтому мониторинг физически обязан быть polling-ом.
    # Чтобы обнаруживать изменения максимально быстро, но не спамить WB:
    #   - опрашиваем товары часто (секунды, а не минуты/часы);
    #   - при этом опрашиваем их ПАРАЛЛЕЛЬНО (см. bot/services/monitor.py), а не по одному,
    #     чтобы длина очереди товаров не увеличивала задержку обнаружения.
    DEFAULT_UPDATE_INTERVAL_SECONDS: int = 60
    # Сколько товаров можно опрашивать одновременно (ограничивает нагрузку на WB API).
    MAX_CONCURRENT_PARSES: int = 5

    MAX_PRODUCTS_PER_USER: int = 50

    # ===== Mini App (Telegram Web App) =====
    # Публичный HTTPS-адрес мини-приложения (например, https://wb-monitor.example.com).
    # Должен совпадать с URL, который указан у @BotFather в Menu Button / Web App.
    # Если оставить пустым — веб-сервер мини-приложения не запускается,
    # бот работает как раньше (только текст + инлайн-кнопки).
    WEBAPP_URL: str = ""
    WEBAPP_HOST: str = "0.0.0.0"
    WEBAPP_PORT: int = 8080
    # Сколько секунд считать initData от Telegram валидной (защита от replay-атак)
    WEBAPP_INIT_DATA_MAX_AGE: int = 86400
    # Разрешить вход по "dev:<telegram_id>" вместо реальной initData —
    # ТОЛЬКО для локальной разработки вне Telegram. В проде держать False.
    WEBAPP_DEV_MODE: bool = False

    @property
    def admin_ids_list(self) -> List[int]:
        if not self.ADMIN_IDS:
            return []
        return [int(x.strip()) for x in self.ADMIN_IDS.split(",") if x.strip()]


settings = Settings()
