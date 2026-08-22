<p align="center">
  <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=700&size=40&pause=1000&color=8A2BE2&center=true&vCenter=true&width=600&height=70&lines=WB+MONITOR;PRICE+PARSING+BOT;Wildberries+Tracker" alt="WB Monitor animated title" />
</p>

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&height=120&section=header" />
</p>

---

<p align="center">
  <img src="https://wsrv.nl/?url=avatars.githubusercontent.com/u/146373364%3Fv%3D4&w=200&h=200&fit=cover&mask=circle" width="120">
</p>

<h2 align="center">Maxsim (Axsion)</h2>

<p align="center">
  Telegram Bot Developer · Python · Automation
</p>

<p align="center">
  <a href="https://github.com/AxsionTM">
    <img src="https://img.shields.io/badge/GitHub-Axsion-black?style=for-the-badge&logo=github">
  </a>
</p>

---

## О проекте

**WB Monitor Bot** — Telegram-бот для мониторинга товаров на Wildberries: отслеживание цены, скидок, наличия и рейтинга с уведомлениями об изменениях и Telegram Mini App, работающим поверх того же бэкенда.

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-blue?style=for-the-badge&logo=python">
  <img src="https://img.shields.io/badge/aiogram-3.13-2CA5E0?style=for-the-badge&logo=telegram">
  <img src="https://img.shields.io/badge/FastAPI-Mini%20App-009688?style=for-the-badge&logo=fastapi">
  <img src="https://img.shields.io/badge/License-Proprietary-red?style=for-the-badge">
</p>

> **Это витрина, а не готовый к запуску дистрибутив.** Проект является коммерческим продуктом, поэтому часть кода в репозитории намеренно упрощена или убрана. Подробности описаны в разделе [Почему код неполный](#почему-код-неполный).

---

## Функционал

* Добавление товаров по артикулу или ссылке на Wildberries, в том числе списком
* Автоматический мониторинг товаров через APScheduler
* Параллельный опрос карточек товаров
* Уведомления об изменениях цены в рублях и процентах с настраиваемым порогом
* Уведомления об изменениях наличия и рейтинга
* Глобальные настройки уведомлений и настройки для отдельных товаров
* История цены и график изменений
* Экспорт данных в Excel с выбором необходимых полей
* Telegram Mini App с карточками товаров, графиками и настройками уведомлений
* Проверка подлинности запросов Mini App по официальной схеме Telegram через `initData` и HMAC-подпись
* Многопользовательский режим с лимитами товаров и административными ролями

---

## Архитектура проекта

```text
wb_monitor_bot/
├── bot/
│   ├── main.py                  # точка входа: бот, планировщик и Mini App
│   ├── config.py                # настройки из .env
│   ├── database/                # модели и сессии SQLAlchemy
│   ├── handlers/                # обработчики Telegram
│   ├── keyboards/               # inline-клавиатуры
│   ├── services/
│   │   ├── parser.py            # запросы к Wildberries API
│   │   ├── monitor.py           # мониторинг и уведомления
│   │   ├── db_service.py        # работа с данными
│   │   └── excel_export.py      # генерация отчётов
│   └── webapp/                  # Telegram Mini App
├── run.py                       # точка запуска
├── requirements.txt
└── .env.example                 # шаблон переменных окружения
```

---

## Быстрый старт

### 1. Клонирование и установка

```bash
git clone https://github.com/AxsionTM/wb-monitor-bot.git
cd wb-monitor-bot
python -m venv venv
```

Windows:

```bash
venv\Scripts\activate
```

Linux / macOS:

```bash
source venv/bin/activate
```

Установите зависимости:

```bash
pip install -r requirements.txt
```

### 2. Создание Telegram-бота

1. Откройте [@BotFather](https://t.me/BotFather).
2. Выполните команду `/newbot`.
3. Задайте имя и username бота.
4. Получите токен.
5. Узнайте свой Telegram ID, например через [@userinfobot](https://t.me/userinfobot).

### 3. Настройка переменных окружения

Создайте `.env` на основе `.env.example`:

```bash
cp .env.example .env
```

Минимальная конфигурация:

```env
BOT_TOKEN=токен_от_botfather
ADMIN_IDS=ваш_telegram_id
```

По умолчанию используется SQLite. База `wb_monitor.db` создаётся автоматически при первом запуске.

---

## Telegram Mini App

Для работы Mini App требуется публичный HTTPS-адрес.

Для локального тестирования можно использовать туннель:

```bash
ngrok http 8080
```

Полученный адрес укажите в `.env`:

```env
WEBAPP_URL=https://xxxx.ngrok-free.app
```

Если `WEBAPP_URL` оставить пустым, бот продолжит работать без веб-интерфейса.

---

## Запуск

```bash
python run.py
```

При успешном запуске в логах появится:

```text
Bot starting...
```

При включённом Mini App также запускается веб-сервер на `0.0.0.0:8080`.

---

## Почему код неполный

Проект является коммерческим продуктом, поэтому публичная версия на GitHub представляет собой портфолио-витрину, а не полноценный дистрибутив.

В публичной версии:

* `bot/services/parser.py` содержит упрощённую реализацию без конкретных деталей обхода антибот-защиты Wildberries;
* цикл мониторинга в `bot/services/monitor.py` и часть бизнес-логики уведомлений представлены в сокращённом виде;
* реальные секреты, база данных и другие приватные данные не публикуются.

Таким образом, репозиторий позволяет ознакомиться с архитектурой и подходом к разработке, но не предназначен для получения полноценной production-версии из коробки.

Для получения рабочей версии или коммерческой лицензии можно связаться через [Telegram](https://t.me/AxsionTM) или открыть Issue.

---

## Лицензия

Код опубликован в ознакомительных целях и как часть портфолио.

Копирование, модификация и коммерческое использование без согласия автора запрещены.

Все права защищены.

<p align="center">
  Made by <a href="https://github.com/AxsionTM">Axsion</a>
</p>

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&height=100&section=footer" />
</p>
