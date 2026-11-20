import os
from pathlib import Path
from dotenv import load_dotenv

# Загрузка переменных окружения из .env файла
ENV_PATH = Path(__file__).parent / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

# Токен Telegram-бота (полученный у @BotFather)
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Путь к базе данных SQLite
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "cloudprint.db")

# Тарифы системы печати CloudPrint СТАНКИН
PRICE_PER_PAGE_BW = 5.0      # Черно-белая печать (5.00 ₽ / стр.)
PRICE_PER_PAGE_COLOR = 10.0   # Цветная печать (10.00 ₽ / стр.)
PRICE_STAPLING = 15.0         # Автоматическое скрепление степлером (+15.00 ₽ / комплект)

# Имя дежурного диспетчера службы эксплуатации
DISPATCHER_NAME = "Цырулев А. А."
