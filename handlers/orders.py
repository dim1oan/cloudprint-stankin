import io
import qrcode
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
import database

router = Router()

@router.message(F.text == "📋 Мои заказы")
async def show_student_orders(message: Message):
    """Отображение реестра всех заказов студента."""
    orders = database.get_student_orders_list(user_id=1)

    if not orders:
        await message.answer(
            "📭 **У вас пока нет оформленных заказов.**\n"
            "Нажмите «🖨 Оформить печать», чтобы отправить первый документ!",
            parse_mode="Markdown"
        )
        return

    await message.answer(f"📋 **Ваши заказы в CloudPrint ({len(orders)} шт.):**", parse_mode="Markdown")

    for o in orders[:8]:
        order_status = o["order_status"]
        is_completed = order_status == "Завершен"
        is_cancelled = order_status == "Отменен (Возврат)"
        is_error = order_status == "Ошибка печати"
        is_rerouted = order_status == "Перенаправлен"

        if is_cancelled:
            status_badge = "💰 Возврат (100%)"
        elif is_completed:
            status_badge = "✓ Завершен"
        elif is_error:
            status_badge = "⚠️ Сбой (E-04)"
        elif is_rerouted:
            status_badge = "🔄 Переведен во 2-й корпус"
        else:
            status_badge = "🟢 Готов к выдаче"

        gost_badge = "ГОСТ 7.32" if o["is_gost"] != 0 else "Без ГОСТ"
        staple_badge = "Сшитие (+15 ₽)" if o["stapling"] else "Без сшития"
        color_badge = "Цвет" if o["is_color"] != 0 else "Ч/Б"

        text = (
            f"📦 **Заказ `{o['order_code']}`** • {status_badge}\n"
            f"📄 {o['file_name']}\n"
            f"📑 {o['page_count']} стр. • `{gost_badge}` • `{color_badge}` • `{staple_badge}`\n"
            f"📍 {o['terminal_campus']} ({o['terminal_name']})\n"
            f"💵 Сумма: **{o['price_rub']:.2f} ₽**\n"
            f"🕒 Время: {o['created_at']}"
        )

        buttons = []
        if not is_completed and not is_cancelled:
            buttons.append([
                InlineKeyboardButton(
                    text=f"🔑 Пин: {o['pickup_code']} (Показать QR)", 
                    callback_data=f"show_qr_{o['id']}"
                )
            ])
            buttons.append([
                InlineKeyboardButton(
                    text="⚠️ Проблема с печатью (E-04)", 
                    callback_data=f"report_order_{o['id']}"
                )
            ])

        reply_markup = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
        await message.answer(text, reply_markup=reply_markup, parse_mode="Markdown")

@router.callback_query(F.data.startswith("show_qr_"))
async def handle_show_order_qr(callback: CallbackQuery):
    """Отправка изображения QR-кода и пин-кода по заказу."""
    order_id = int(callback.data.replace("show_qr_", ""))
    orders = database.get_student_orders_list(user_id=1)
    target = next((x for x in orders if x["id"] == order_id), None)

    if not target:
        await callback.answer("Заказ не найден", show_alert=True)
        return

    pickup_code = target["pickup_code"] or "654-321"
    order_code = target["order_code"]

    qr_data = f"STANKIN-PRINT:{order_code}:{pickup_code}"
    qr = qrcode.QRCode(version=1, box_size=8, border=3)
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0D2040", back_color="white")

    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")
    img_bytes.seek(0)
    photo = BufferedInputFile(img_bytes.read(), filename="pickup.png")

    caption = (
        f"🔑 **Код выдачи:** 【 `{pickup_code}` 】\n"
        f"📦 Заказ: `{order_code}`\n"
        f"📍 МФУ: **{target['terminal_campus']}** ({target['terminal_name']})\n"
        f"📌 Адрес: {target['terminal_location']}"
    )
    await callback.message.answer_photo(photo=photo, caption=caption, parse_mode="Markdown")
    await callback.answer()
