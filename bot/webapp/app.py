"""FastAPI-приложение мини-аппы. Отдаёт статический фронтенд (static/) и
REST API (/api/*), которым пользуется этот фронтенд.
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from bot.webapp.api import router as api_router

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI(title="WB Monitor Mini App", docs_url=None, redoc_url=None)

# Мини-приложение открывается внутри Telegram (WebView), поэтому источник запроса
# не всегда предсказуем — разрешаем CORS на уровне API, сама аутентификация
# всё равно защищена подписью initData (см. bot/webapp/auth.py).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

# Статика (index.html, style.css, app.js) — монтируется последней и на "/",
# чтобы не перекрывать /api/*.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
