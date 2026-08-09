<p align="center">
  <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=700&size=40&pause=1000&color=8A2BE2&center=true&vCenter=true&width=600&height=70&lines=WB+MONITOR;PRICE+PARSING+BOT;Wildberries+Tracker" alt="WB Monitor animated title" />
</p>

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&height=120&section=header" />
</p>

---

<p align="center">
<img src="https://avatars.githubusercontent.com/u/146373364?v=4" width="120" style="border-radius:50%">
</p>
<h2 align="center">👨‍💻 Maxsim (Axsion)</h2>
<p align="center">
<img src="https://img.shields.io/badge/Age-17-blue?style=for-the-badge">
<a href="https://github.com/AxsionTM">
<img src="https://img.shields.io/badge/GitHub-Axsion-black?style=for-the-badge&logo=github">
</a>
</p>

---

## 📦 О проекте

**WB Monitor Bot** — Telegram-бот для мониторинга товаров на Wildberries: отслеживание цены,
скидок, наличия и рейтинга в реальном времени, с уведомлениями об изменениях и Telegram
Mini App (веб-интерфейсом) поверх того же бэкенда.

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-blue?style=for-the-badge&logo=python">
  <img src="https://img.shields.io/badge/aiogram-3.13-2CA5E0?style=for-the-badge&logo=telegram">
  <img src="https://img.shields.io/badge/FastAPI-Mini%20App-009688?style=for-the-badge&logo=fastapi">
  <img src="https://img.shields.io/badge/License-Proprietary-red?style=for-the-badge">
</p>

> ⚠️ **Это витрина, а не готовый к запуску дистрибутив.** Проект коммерческий (продаётся),
> поэтому часть кода в этом репозитории намеренно упрощена/убрана — подробности в разделе
> [«Почему код неполный»](#-почему-код-неполный).

---

## ✨ Функционал

- 🔍 **Добавление товаров** по артикулу или ссылке на Wildberries (можно списком, по одному на строку)
- 📊 **Автоматический мониторинг** — фоновый опрос карточек товара по расписанию (APScheduler),
  параллельно, без линейного роста задержки от количества товаров
- 🔔 **Уведомления об изменениях** цены (в рублях и/или в процентах, с настраиваемым порогом),
  наличия и рейтинга — глобально или по каждому товару отдельно
- 📈 **История цены** и график изменений по товару
- 📁 **Экспорт в Excel** — гибкий выбор полей (цена, старая цена, бренд, рейтинг, артикул и т.д.)
- 📱 **Telegram Mini App** — полноценный веб-интерфейс внутри Telegram: карточки товаров,
  графики, настройки уведомлений, тот же функционал, что и в чате, но в виде приложения
- 🔐 **Проверка подлинности запросов Mini App** по официальной схеме Telegram
  (`initData` + HMAC-подпись на основе токена бота) — фронтенд не может быть вызван в обход бота
- 👤 **Многопользовательский режим** с лимитом товаров на пользователя и админ-ролями

---

## 🏗 Архитектура проекта

```
wb_monitor_bot/
├── bot/
│   ├── main.py              # точка входа: бот + планировщик + веб-сервер мини-аппы
│   ├── config.py             # настройки из .env (pydantic-settings)
│   ├── database/              # модели и сессии SQLAlchemy (async)
│   ├── handlers/               # обработчики команд/кнопок Telegram (aiogram)
│   ├── keyboards/               # инлайн-клавиатуры
│   ├── services/
│   │   ├── parser.py             # запросы к Wildberries API
│   │   ├── monitor.py            # цикл мониторинга и логика уведомлений
│   │   ├── db_service.py         # доступ к данным
│   │   └── excel_export.py       # генерация отчётов
│   └── webapp/                    # Telegram Mini App (FastAPI + статика)
├── run.py                    # запуск: python run.py
├── requirements.txt
└── .env.example                # шаблон переменных окружения (без секретов)
```

---

## 🚀 Как запустить (демо-режим)

### 1. Клонировать репозиторий и установить зависимости

```bash
git clone https://github.com/AxsionTM/wb-monitor-bot.git
cd wb-monitor-bot
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Создать своего бота

1. В Telegram написать [@BotFather](https://t.me/BotFather)
2. `/newbot` → задать имя и username → получить токен
3. Узнать свой Telegram ID (например, у [@userinfobot](https://t.me/userinfobot))

### 3. Настроить переменные окружения

```bash
cp .env.example .env
```

Открыть `.env` и заполнить как минимум:

```env
BOT_TOKEN=токен_от_botfather
ADMIN_IDS=ваш_telegram_id
```

По умолчанию используется SQLite — база `wb_monitor.db` создастся автоматически
при первом запуске, ничего дополнительно поднимать не нужно.

### 4. (Опционально) Mini App

Mini App требует публичный `https://` адрес. Для локального теста — туннель:

```bash
ngrok http 8080
```

Полученный адрес вписать в `.env`:

```env
WEBAPP_URL=https://xxxx.ngrok-free.app
```

Если оставить `WEBAPP_URL` пустым — бот работает как обычный текстовый бот,
без веб-интерфейса, и это нормально.

### 5. Запустить

```bash
python run.py
```

В логах должно появиться `Bot starting...` и (если настроен Mini App)
`Mini App сервер запускается на 0.0.0.0:8080`.

---

## 🔒 Почему код неполный

Проект — коммерческий продукт (лицензия/доступ продаётся), поэтому публичная версия
на GitHub — это **портфолио-витрина**, показывающая архитектуру и качество кода, а не
готовый к бесплатному использованию продукт. Сознательно:

- из `bot/services/parser.py` убраны/упрощены конкретные детали обхода
  анти-бот защиты Wildberries (задержки, ротация заголовков, повторные попытки —
  «боевая» логика не публикуется);
- цикл мониторинга (`bot/services/monitor.py`) и часть бизнес-логики уведомлений
  оставлены в сокращённом виде — достаточно, чтобы понять подход, недостаточно,
  чтобы получить продакшн-версию «из коробки»;
- никакие реальные секреты (`.env`, база `wb_monitor.db`) в репозиторий не попадают —
  см. `.gitignore` выше.

Если вам нужен рабочий бот под ключ или лицензия на полную версию — пишите в
[Telegram](https://t.me/AxsionTM) или через issues.

## 📄 Лицензия

Код опубликован в ознакомительных целях (портфолио). Копирование, модификация и
коммерческое использование без согласия автора запрещены. Все права защищены.

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&height=100&section=footer" />
</p>
