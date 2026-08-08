"""
Точка входа для запуска бота.
Использование:
    python run.py
"""
from bot.main import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
