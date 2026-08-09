"""
Проверка подлинности данных, которые Telegram передаёт мини-приложению (initData).

Как это работает:
  1. Telegram Web App подписывает данные о пользователе своим HMAC на основе
     токена бота — так сервер может быть уверен, что запрос действительно
     пришёл из Telegram, а не подделан снаружи.
  2. Фронтенд (static/app.js) на каждый запрос к /api/* кладёт сырой
     `Telegram.WebApp.initData` в заголовок `Authorization: tma <initData>`.
  3. Мы пересчитываем HMAC и сверяем — алгоритм описан в официальной документации:
     https://core.telegram.org/bots/webapps#validating-data-received-via-the-web-app
"""

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException, status

from bot.config import settings

logger = logging.getLogger(__name__)


@dataclass
class TelegramUser:
    id: int
    username: Optional[str]
    full_name: str


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def _validate_init_data(init_data: str) -> dict:
    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        raise _unauthorized("Некорректный формат initData")

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise _unauthorized("В initData отсутствует hash")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", settings.BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise _unauthorized("Недействительная подпись initData")

    auth_date = int(parsed.get("auth_date", "0") or "0")
    max_age = settings.WEBAPP_INIT_DATA_MAX_AGE
    if max_age and auth_date and (time.time() - auth_date) > max_age:
        raise _unauthorized("initData устарела — переоткройте приложение из Telegram")

    return parsed


def _extract_init_data(
    authorization: Optional[str],
    x_telegram_init_data: Optional[str],
) -> Optional[str]:
    if authorization:
        # Официальная схема Telegram: "Authorization: tma <initData>"
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "tma":
            return parts[1]
    if x_telegram_init_data:
        return x_telegram_init_data
    return None


async def get_current_telegram_user(
    authorization: Optional[str] = Header(default=None),
    x_telegram_init_data: Optional[str] = Header(default=None, alias="X-Telegram-Init-Data"),
) -> TelegramUser:
    init_data = _extract_init_data(authorization, x_telegram_init_data)
    if not init_data:
        raise _unauthorized("Нет данных авторизации Telegram")

    # Только для локальной разработки вне Telegram (WEBAPP_DEV_MODE=true в .env).
    if settings.WEBAPP_DEV_MODE and init_data.startswith("dev:"):
        try:
            dev_id = int(init_data.split(":", 1)[1])
        except (IndexError, ValueError):
            raise _unauthorized("Некорректный dev-идентификатор")
        logger.warning(f"[WebApp] DEV MODE: вход как telegram_id={dev_id} без проверки подписи")
        return TelegramUser(id=dev_id, username="dev", full_name="Dev User")

    parsed = _validate_init_data(init_data)

    user_raw = parsed.get("user")
    if not user_raw:
        raise _unauthorized("В initData нет данных о пользователе")

    try:
        user_json = json.loads(user_raw)
    except json.JSONDecodeError:
        raise _unauthorized("Не удалось разобрать данные пользователя")

    full_name = " ".join(
        part for part in [user_json.get("first_name"), user_json.get("last_name")] if part
    ) or "Без имени"

    return TelegramUser(
        id=int(user_json["id"]),
        username=user_json.get("username"),
        full_name=full_name,
    )
