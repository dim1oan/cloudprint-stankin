import io
import os
import qrcode
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from pypdf import PdfReader
from keyboards import (
    get_file_choice_keyboard,
    get_gost_mode_keyboard,
    get_options_keyboard,
    get_terminals_keyboard,
    get_payment_keyboard,
    get_main_menu_keyboard
)
import database
from config import PRICE_PER_PAGE_BW, PRICE_PER_PAGE_COLOR, PRICE_STAPLING

router = Router()

class PrintWizard(StatesGroup):
    choosing_file = State()
    choosing_gost = State()
    choosing_options = State()
    choosing_terminal = State()
    choosing_payment = State()

def calculate_order_price(pages: int, is_color: bool, stapling: bool) -> float:
    """Расчет стоимости: 5 ₽ за ч/б, 10 ₽ за цветную, +15 ₽ за сшитие степлером."""
    rate = PRICE_PER_PAGE_COLOR if is_color else PRICE_PER_PAGE_BW
    return round((pages * rate) + (PRICE_STAPLING if stapling else 0.0), 2)

@router.message(F.text == "🖨 Оформить печать")
async def start_print_wizard(message: Message, state: FSMContext):
    """Старт мастера оформления печати (Шаг 1: Документ)."""
    await state.clear()
    await state.set_state(PrintWizard.choosing_file)
    await state.update_data(
        file_name="Курсовой_проект_Детали_машин.pdf",
        page_count=20,
        is_gost=True,
        is_color=True,
        stapling=False,
        terminal_id=2
    )

    text = (
        "📄 **Шаг 1 из 4: Загрузка документа для печати**\n\n"
        "Вы можете:\n"
        "1. **Отправить свой файл (PDF или DOCX)** прямо в этот чат Telegram 📎\n"
        "2. Или выбрать один из готовых образцов студенческих работ ниже 👇"
    )
    await message.answer(text, reply_markup=get_file_choice_keyboard(), parse_mode="Markdown")

@router.callback_query(F.data == "sample_file_1")
async def handle_sample_1(callback: CallbackQuery, state: FSMContext):
    """Выбор образца: Курсовой проект (20 стр.)."""
    await state.update_data(
        file_name="Курсовой_проект_Детали_машин.pdf",
        page_count=20
    )
    await step_to_gost_screen(callback, state)

@router.callback_query(F.data == "sample_file_2")
async def handle_sample_2(callback: CallbackQuery, state: FSMContext):
    """Выбор образца: Дипломный проект (45 стр.)."""
    await state.update_data(
        file_name="Дипломный_проект_ВКР_СТАНКИН.pdf",
        page_count=45
    )
    await step_to_gost_screen(callback, state)

@router.callback_query(F.data == "await_upload_hint")
async def handle_upload_hint(callback: CallbackQuery):
    await callback.answer("Прикрепите и отправьте PDF или DOCX файл в чат как документ!", show_alert=True)

@router.message(PrintWizard.choosing_file, F.document)
async def handle_file_upload(message: Message, state: FSMContext):
    """Получение документа от студента и подсчет страниц."""
    doc = message.document
    file_name = doc.file_name or "Документ_студента.pdf"
    pages = 1

    # Попытка автоматически определить число страниц для PDF
    if file_name.lower().endswith(".pdf"):
        try:
            bot = message.bot
            file_obj = await bot.get_file(doc.file_id)
            pdf_bytes = io.BytesIO()
            await bot.download_file(file_obj.file_path, pdf_bytes)
            pdf_bytes.seek(0)
            reader = PdfReader(pdf_bytes)
            pages = max(1, len(reader.pages))
        except Exception:
            pages = 10
    else:
        pages = 15

    await state.update_data(
        file_name=file_name,
        page_count=pages
    )

    await message.answer(
        f"✅ **Файл успешно принят!**\n"
        f"📄 `{file_name}`\n"
        f"📑 Распознано страниц: **{pages} стр. (А4)**",
        parse_mode="Markdown"
    )

    data = await state.get_data()
    is_gost = data.get("is_gost", True)
    await state.set_state(PrintWizard.choosing_gost)

    text = (
        f"📐 **Режим оформления студенческой работы:**\n\n"
        f"• **ГОСТ 7.32 (СТАНКИН)**: автоматический префлайт полей (20-10-10-30 мм), шрифтов Times New Roman 14 pt, нумерации и рамок.\n"
        f"• **Обычная печать**: без изменения оригинальной разметки документа."
    )
    await message.answer(text, reply_markup=get_gost_mode_keyboard(is_gost), parse_mode="Markdown")

async def step_to_gost_screen(callback: CallbackQuery, state: FSMContext):
    """Экран выбора режима ГОСТ."""
    await state.set_state(PrintWizard.choosing_gost)
    data = await state.get_data()
    file_name = data.get("file_name", "Курсовой_проект_Детали_машин.pdf")
    pages = data.get("page_count", 20)
    is_gost = data.get("is_gost", True)

    text = (
        f"📄 Выбран документ: **{file_name}** ({pages} стр.)\n\n"
        f"📐 **Выберите режим оформления работы:**\n"
        f"• **ГОСТ 7.32 (СТАНКИН)**: проверка полей (20-10-10-30 мм), шрифтов Times New Roman 14 pt и рамок.\n"
        f"• **Обычная печать**: печать в оригинальном виде."
    )
    await callback.message.edit_text(text, reply_markup=get_gost_mode_keyboard(is_gost), parse_mode="Markdown")

@router.callback_query(F.data == "set_gost_true")
async def handle_gost_true(callback: CallbackQuery, state: FSMContext):
    await state.update_data(is_gost=True)
    await callback.answer("Выбран режим: ГОСТ 7.32 (СТАНКИН)")
    await callback.message.edit_reply_markup(reply_markup=get_gost_mode_keyboard(True))

@router.callback_query(F.data == "set_gost_false")
async def handle_gost_false(callback: CallbackQuery, state: FSMContext):
    await state.update_data(is_gost=False)
    await callback.answer("Выбран режим: Обычная печать")
    await callback.message.edit_reply_markup(reply_markup=get_gost_mode_keyboard(False))

@router.callback_query(F.data == "step_to_options")
async def handle_step_to_options(callback: CallbackQuery, state: FSMContext):
    """Переход к параметрам цветности и сшития."""
    await state.set_state(PrintWizard.choosing_options)
    data = await state.get_data()
    is_gost = data.get("is_gost", True)
    is_color = data.get("is_color", True)
    stapling = data.get("stapling", False)
    pages = data.get("page_count", 20)

    preflight_note = (
        "🔍 *Префлайт ГОСТ 7.32 успешно подтвержден: поля 20-10-10-30 мм и шрифты TNR 14pt соответствуют регламенту СТАНКИН!*\n\n"
        if is_gost else ""
    )

    current_price = calculate_order_price(pages, is_color, stapling)

    text = (
        f"{preflight_note}"
        f"⚙️ **Шаг 2 из 4: Параметры печати и скрепления**\n\n"
        f"• **Цветность:** {'🎨 Цветная (10 ₽/стр)' if is_color else '⚫ Черно-белая (5 ₽/стр)'}\n"
        f"• **Сшитие степлером:** {'📎 Включено (+15 ₽)' if stapling else '🚫 Без сшития (0 ₽)'}\n"
        f"• **Текущая стоимость:** `{current_price:.2f} ₽` ({pages} стр.)\n\n"
        f"Настройте параметры кнопками ниже 👇"
    )
    await callback.message.edit_text(text, reply_markup=get_options_keyboard(is_color, stapling), parse_mode="Markdown")

@router.callback_query(F.data == "opt_color_true")
async def handle_opt_color_true(callback: CallbackQuery, state: FSMContext):
    await state.update_data(is_color=True)
    data = await state.get_data()
    await update_options_message(callback, state, data)

@router.callback_query(F.data == "opt_color_false")
async def handle_opt_color_false(callback: CallbackQuery, state: FSMContext):
    await state.update_data(is_color=False)
    data = await state.get_data()
    await update_options_message(callback, state, data)

@router.callback_query(F.data == "opt_toggle_stapling")
async def handle_opt_toggle_stapling(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    new_stapling = not data.get("stapling", False)
    await state.update_data(stapling=new_stapling)
    data["stapling"] = new_stapling
    await update_options_message(callback, state, data)

async def update_options_message(callback: CallbackQuery, state: FSMContext, data: dict):
    is_color = data.get("is_color", True)
    stapling = data.get("stapling", False)
    pages = data.get("page_count", 20)
    current_price = calculate_order_price(pages, is_color, stapling)

    text = (
        f"⚙️ **Шаг 2 из 4: Параметры печати и скрепления**\n\n"
        f"• **Цветность:** {'🎨 Цветная (10 ₽/стр)' if is_color else '⚫ Черно-белая (5 ₽/стр)'}\n"
        f"• **Сшитие степлером:** {'📎 Включено (+15 ₽)' if stapling else '🚫 Без сшития (0 ₽)'}\n"
        f"• **Текущая стоимость:** `{current_price:.2f} ₽` ({pages} стр.)\n\n"
        f"Настройте параметры кнопками ниже 👇"
    )
    await callback.message.edit_text(text, reply_markup=get_options_keyboard(is_color, stapling), parse_mode="Markdown")

@router.callback_query(F.data == "step_back_to_gost")
async def handle_step_back_to_gost(callback: CallbackQuery, state: FSMContext):
    await step_to_gost_screen(callback, state)

@router.callback_query(F.data == "step_to_terminals")
@router.callback_query(F.data == "step_back_to_terminals")
async def handle_step_to_terminals(callback: CallbackQuery, state: FSMContext):
    """Выбор терминала выдачи распечатки (Шаг 3)."""
    await state.set_state(PrintWizard.choosing_terminal)
    terms = database.get_terminals_list()

    text = (
        "📍 **Шаг 3 из 4: Выберите терминал выдачи распечатки**\n\n"
        "Задание будет отправлено в очередь печати выбранного МФУ.\n"
        "⚠️ Если на МФУ зафиксирован аппаратный сбой (например, Замятие E-04), печать блокируется во избежание списания средств!"
    )
    await callback.message.edit_text(text, reply_markup=get_terminals_keyboard(terms), parse_mode="Markdown")

@router.callback_query(F.data.startswith("select_term_"))
async def handle_select_terminal(callback: CallbackQuery, state: FSMContext):
    """Проверка доступности МФУ (БАГ 2) и переход к оплате."""
    term_id = int(callback.data.replace("select_term_", ""))
    term = database.get_terminal(term_id)

    if not term:
        await callback.answer("Ошибка: терминал не найден", show_alert=True)
        return

    # БАГ 2: Блокировка выбора сломанного терминала
    if term["status"] != "Онлайн":
        alt_campus = "Терминал №2 (Новый корпус)" if term_id == 1 else "Терминал №1 (Старый корпус)"
        alert_msg = (
            f"⛔ Терминал «{term['name']}» заблокирован диспетчерской службой!\n\n"
            f"Текущий статус: «{term['status']}».\n"
            f"Печать на нем остановлена во избежание списания средств.\n"
            f"Пожалуйста, выберите {alt_campus}!"
        )
        await callback.answer(alert_msg, show_alert=True)
        return

    await state.update_data(terminal_id=term_id)
    await state.set_state(PrintWizard.choosing_payment)

    data = await state.get_data()
    file_name = data.get("file_name", "Курсовой_проект.pdf")
    pages = data.get("page_count", 20)
    is_gost = data.get("is_gost", True)
    is_color = data.get("is_color", True)
    stapling = data.get("stapling", False)
    total_price = calculate_order_price(pages, is_color, stapling)

    user = database.get_student_user(1)
    user_balance = user["balance_rub"] if user else 150.0

    color_title = "Цветная (10.00 ₽/стр)" if is_color else "Черно-белая (5.00 ₽/стр)"
    staple_line = f"• 📎 Сшитие степлером: `+15.00 ₽`\n" if stapling else ""

    text = (
        f"🧾 **Шаг 4 из 4: Детализация заказа и оплата**\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"• 📄 Документ: **{file_name}**\n"
        f"• 📑 Объем: **{pages} стр. (А4)**\n"
        f"• 📐 Стандарт: `{'ГОСТ 7.32 (СТАНКИН)' if is_gost else 'Обычная печать'}`\n"
        f"• 🎨 Цветность: `{color_title}`\n"
        f"{staple_line}"
        f"• 📍 Пункт выдачи: **{term['name']}**\n"
        f"  ({term['location']})\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 **ИТОГО К ОПЛАТЕ:** `{total_price:.2f} ₽`\n"
        f"🪙 Ваш бонусный баланс: `{user_balance:.2f} ₽`\n\n"
        f"Выберите удобный способ оплаты:"
    )
    await callback.message.edit_text(text, reply_markup=get_payment_keyboard(total_price, user_balance), parse_mode="Markdown")

@router.callback_query(F.data == "step_back_to_options")
async def handle_step_back_to_options(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await update_options_message(callback, state, data)

@router.callback_query(F.data == "pay_bonus")
async def handle_pay_bonus(callback: CallbackQuery, state: FSMContext):
    await process_payment(callback, state, payment_method="bonus")

@router.callback_query(F.data == "pay_sbp")
async def handle_pay_sbp(callback: CallbackQuery, state: FSMContext):
    await process_payment(callback, state, payment_method="sbp")

async def process_payment(callback: CallbackQuery, state: FSMContext, payment_method: str):
    """Проведение оплаты и отправка 6-значного пин-кода с QR-кодом."""
    data = await state.get_data()
    file_name = data.get("file_name", "Курсовой_проект.pdf")
    pages = data.get("page_count", 20)
    is_gost = data.get("is_gost", True)
    is_color = data.get("is_color", True)
    stapling = data.get("stapling", False)
    term_id = data.get("terminal_id", 2)
    total_price = calculate_order_price(pages, is_color, stapling)

    res = database.create_client_order(
        user_id=1,
        terminal_id=term_id,
        file_name=file_name,
        page_count=pages,
        price_rub=total_price,
        payment_method=payment_method,
        is_gost=is_gost,
        stapling=stapling,
        is_color=is_color
    )

    if isinstance(res, dict) and "error" in res:
        await callback.answer(res["error"], show_alert=True)
        return

    await state.clear()
    await callback.message.delete()

    order_code = res["order_code"]
    pickup_code = res["pickup_code"]
    term_name = res["terminal_name"]
    location = res["terminal_location"]

    # Генерация изображения реального QR-кода
    qr_data = f"STANKIN-PRINT:{order_code}:{pickup_code}"
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0D2040", back_color="white")

    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")
    img_bytes.seek(0)
    photo = BufferedInputFile(img_bytes.read(), filename="pickup_qr.png")

    caption = (
        f"🎉 **Заказ успешно оплачен и отправлен в печать!**\n\n"
        f"🔑 **ВАШ КОД ПОЛУЧЕНИЯ:** 【 `{pickup_code}` 】\n"
        f"📦 Номер заказа: `{order_code}`\n"
        f"📍 Терминал: **{term_name}**\n"
        f"📌 Адрес: {location}\n"
        f"💰 Оплачено: `{total_price:.2f} ₽` ({'Бонусами' if payment_method == 'bonus' else 'СБП'})\n\n"
        f"ℹ️ Введите код на клавиатуре МФУ или отсканируйте QR-код сканером терминала."
    )
    await callback.message.answer_photo(photo=photo, caption=caption, parse_mode="Markdown", reply_markup=get_main_menu_keyboard())

@router.callback_query(F.data == "cancel_wizard")
async def handle_cancel_wizard(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Оформление печати отменено.")
