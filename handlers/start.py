import os
import re
from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery, FSInputFile,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import CommandStart, Command
from keyboards import get_main_menu_keyboard
import database

router = Router()

def is_gazyava_trigger(message: Message) -> bool:
    """Проверка триггера на фразу 'я щас заберу у тебя газяву' и её вариации."""
    if not message.text:
        return False
    t = message.text.lower().strip()
    clean = re.sub(r"[^\w\s]", "", t)
    # Прямое совпадение
    if "я щас заберу у тебя газяву" in clean or "я сейчас заберу у тебя газяву" in clean:
        return True
    # Комбинации слов "заберу/отберу/отдай" + "газяв"
    has_action = any(w in clean for w in ["заберу", "отберу", "забрать", "отдай", "отниму", "украду", "сворую"])
    has_gazyava = "газяв" in clean or "газировк" in clean or "газ воду" in clean
    return has_action and has_gazyava

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

@router.message(is_gazyava_trigger)
async def handle_gazyava_message(message: Message):
    """Пасхалка: ответ стикером на 'я щас заберу у тебя газяву'."""
    # 1. Проверяем, сохранён ли кастомный стикер в базе данных или переменных окружения
    custom_sticker_id = database.get_system_setting("gazyava_sticker", "") or os.getenv("GAZYAVA_STICKER_ID", "")

    if custom_sticker_id:
        try:
            await message.answer_sticker(sticker=custom_sticker_id)
            return
        except Exception:
            pass

    # 2. Если кастомный не задан, отправляем фирменный WebP-стикер из assets
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sticker_path = os.path.join(base_dir, "assets", "gazyava.webp")

    if os.path.exists(sticker_path):
        try:
            sticker_file = FSInputFile(sticker_path)
            await message.answer_sticker(sticker=sticker_file)
            return
        except Exception:
            pass

    # 3. Текстовый фоллбэк на случай проблем со стикером
    await message.answer("🥤 Не трожь газяву! Это святое для студента СТАНКИНа! 💥")

@router.message(F.sticker)
async def handle_incoming_sticker(message: Message):
    """
    Если пользователь присылает боту стикер, бот предлагает
    установить его в качестве ответа на 'я щас заберу у тебя газяву'.
    """
    sticker_id = message.sticker.file_id
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🥤 Назначить на «я щас заберу у тебя газяву»", callback_data=f"set_gaz_sticker")]
    ])
    # Временно сохраняем последний присланный стикер
    database.set_system_setting("last_received_sticker", sticker_id)
    await message.answer(
        "✨ <b>Классный стикер!</b>\n\n"
        "Хотите назначить его в качестве ответа бота на фразу:\n"
        "<i>«я щас заберу у тебя газяву»</i>?",
        reply_markup=kb,
        parse_mode="HTML"
    )

@router.callback_query(F.data == "set_gaz_sticker")
async def handle_set_gaz_sticker(callback: CallbackQuery):
    """Подтверждение установки стикера."""
    last_sticker = database.get_system_setting("last_received_sticker", "")
    if last_sticker:
        database.set_system_setting("gazyava_sticker", last_sticker)
        await callback.answer("Стикер успешно сохранён!", show_alert=True)
        await callback.message.edit_text(
            "✅ <b>Стикер успешно установлен!</b>\n\n"
            "Теперь напишите в чат: <code>я щас заберу у тебя газяву</code> — и бот ответит именно этим стикером!",
            parse_mode="HTML"
        )
    else:
        await callback.answer("Стикер не найден. Пришлите стикер ещё раз.", show_alert=True)
