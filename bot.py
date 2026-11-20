import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
import database
from config import BOT_TOKEN, DB_PATH
from handlers import start, print_wizard, orders, support, admin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger("CloudPrintBot")

async def main():
    print("=" * 70)
    print("  🤖 Запуск Telegram-бота «CloudPrint СТАНКИН»")
    print("  🎓 МГТУ «СТАНКИН» — Смарт-полиграфия")
    print(f"  📂 База данных: {DB_PATH}")
    print("=" * 70)

    # Инициализация структуры базы данных
    database.init_db()

    # Проверка наличия токена
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("\n⚠️ ВНИМАНИЕ: Не указан токен Telegram-бота!")
        print("1. Откройте Telegram и напишите боту @BotFather")
        print("2. Создайте нового бота командой /newbot и скопируйте API токен")
        print("3. Вставьте токен в файл .env в этой папке:")
        print("   BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ")
        print("4. Перезапустите бота командой: python bot.py (или через start_bot.bat)\n")
        sys.exit(1)

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # Регистрация роутеров всех модулей
    dp.include_router(start.router)
    dp.include_router(print_wizard.router)
    dp.include_router(orders.router)
    dp.include_router(support.router)
    dp.include_router(admin.router)

    logger.info("Бот успешно инициализирован. Запуск long polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен пользователем.")
