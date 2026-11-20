from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import CommandStart, Command
from keyboards import get_main_menu_keyboard
import database

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    """Приветственное сообщение и инициализация меню студента с синхронизацией."""
    database.init_db()
    # Привязываем Telegram chat_id к профилю студента в единой базе данных
    database.bind_user_telegram_chat(user_id=1, chat_id=message.chat.id)

    user = database.get_student_user(1)
    full_name = user["full_name"] if user else "Иванов М. В."
    group = user["group_code"] if user else "ИДБ-25-15"
    balance = user["balance_rub"] if user else 150.0

    text = (
        f"👋 **Добро пожаловать в CloudPrint СТАНКИН!**\n"
        f"Университетский сервис облачной смарт-полиграфии МГТУ «СТАНКИН».\n\n"
        f"👤 **Студент:** {full_name} ({group})\n"
        f"💰 **Бонусный баланс:** `{balance:.2f} ₽` (1 бонус = 1 ₽)\n"
        f"🔗 **Синхронизация с сайтом:** `Подключено` ✅\n"
        f"_(Ответы диспетчера с веб-панели и уведомления о статусе печати приходят сюда)_\n\n"
        f"📌 **Действующие тарифы:**\n"
        f"• ⚫ Черно-белая печать (Ч/Б): **5.00 ₽** / стр.\n"
        f"• 🎨 Цветная лазерная печать: **10.00 ₽** / стр.\n"
        f"• 📎 Автоматическое скрепление степлером: **+15.00 ₽** / комплект\n"
        f"• 📐 Проверка и оформление по **ГОСТ 7.32 (СТАНКИН)**: бесплатно!\n\n"
        f"Выберите нужное действие в меню ниже 👇"
    )
    await message.answer(text, reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")

@router.message(F.text == "💳 Баланс и профиль")
@router.message(Command("balance"))
async def show_profile(message: Message):
    """Отображение профиля студента и истории операций."""
    user = database.get_student_user(1)
    if not user:
        await message.answer("Ошибка: профиль студента не найден.")
        return

    text = (
        f"👤 **Профиль студента МГТУ «СТАНКИН»**\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"• ФИО: **{user['full_name']}**\n"
        f"• Студенческий билет: `{user['student_card']}`\n"
        f"• Академическая группа: **{user['group_code']}**\n"
        f"• Доступный баланс: **{user['balance_rub']:.2f} ₽**\n"
        f"• Статус: `Активный субсидированный аккаунт`\n\n"
        f"ℹ️ Бонусы начисляются за академические успехи, а также в виде 100% компенсации при замятии бумаги."
    )
    await message.answer(text, parse_mode="Markdown")
