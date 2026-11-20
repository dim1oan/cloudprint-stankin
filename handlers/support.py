from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import database
from config import DISPATCHER_NAME

router = Router()

class SupportChat(StatesGroup):
    waiting_message = State()

@router.message(F.text == "🆘 Поддержка (Замятие E-04)")
async def show_support_menu(message: Message):
    """Служба поддержки: выбор проблемного заказа или просмотр активного тикета."""
    ticket = database.get_student_active_ticket(user_id=1)
    orders = database.get_student_orders_list(user_id=1)

    buttons = []
    if orders:
        for o in orders[:4]:
            buttons.append([
                InlineKeyboardButton(
                    text=f"🚨 Замятие по {o['order_code']} ({o['price_rub']:.0f} ₽)", 
                    callback_data=f"report_order_{o['id']}"
                )
            ])

    if ticket:
        buttons.append([
            InlineKeyboardButton(text="💬 Открыть чат с диспетчером", callback_data=f"view_ticket_{ticket['id']}")
        ])

    reply_markup = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None

    text = (
        f"🆘 **Диспетчерская служба техподдержки CloudPrint**\n"
        f"Дежурный диспетчер: **{DISPATCHER_NAME}** 👨‍💼\n\n"
        f"Если терминал зажевал бумагу (ошибка E-04), выберите заказ ниже для немедленной регистрации инцидента.\n"
        f"Диспетчер может:\n"
        f"1. 🔄 **Перевести заказ на 2-й корпус** без очередей и доплат (печать состоится в полном объеме).\n"
        f"2. 💰 **Начислить 100% компенсацию** на ваш баланс (если печать отменяется)."
    )
    await message.answer(text, reply_markup=reply_markup, parse_mode="Markdown")

@router.callback_query(F.data.startswith("report_order_"))
async def handle_report_order(callback: CallbackQuery):
    """Регистрация инцидента замятия бумаги с привязкой order_id (БАГ 1)."""
    order_id = int(callback.data.replace("report_order_", ""))
    orders = database.get_student_orders_list(user_id=1)
    target = next((x for x in orders if x["id"] == order_id), None)

    issue_text = "Зажевало бумагу! МФУ издало треск и выдало ошибку E-04. Прошу перевести на другой корпус или вернуть средства!"
    res = database.report_student_issue(
        user_id=1,
        order_id=order_id,
        terminal_id=target["terminal_id"] if target else 1,
        order_code=target["order_code"] if target else "",
        issue_text=issue_text
    )

    if isinstance(res, dict) and "error" in res:
        await callback.answer(res["error"], show_alert=True)
        return

    ticket_num = res["ticket_number"]
    text = (
        f"🚨 **Зафиксирован инцидент замятия бумаги (E-04)!**\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"• Номер обращения: `{ticket_num}`\n"
        f"• Заказ: `{res.get('order_code', '—')}` (стоимость: {res.get('price_rub', 0):.2f} ₽)\n"
        f"• Терминал: **{res.get('terminal_name', 'МФУ')}** переведен в статус `Замятие E-04`.\n\n"
        f"👨‍💼 Дежурный диспетчер **{DISPATCHER_NAME}** уже получил ваш сигнал и принимает решение (перевод на 2-й корпус или 100% возврат средств)."
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Чат с диспетчером", callback_data=f"view_ticket_{res['id']}")]
    ])
    await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer("Сигнал E-04 передан диспетчеру!", show_alert=True)

@router.callback_query(F.data.startswith("view_ticket_"))
async def handle_view_ticket(callback: CallbackQuery):
    """Просмотр переписки по обращению."""
    ticket_id = int(callback.data.replace("view_ticket_", ""))
    ticket = database.get_ticket_details(ticket_id)

    if not ticket:
        await callback.answer("Тикет не найден", show_alert=True)
        return

    text = (
        f"💬 **Обращение `{ticket['ticket_number']}`**\n"
        f"Статус: `{ticket['status']}`\n"
        f"Заказ: `{ticket.get('order_code', '—')}` ({ticket.get('price_rub', 0):.2f} ₽)\n"
        f"Площадка: {ticket.get('terminal_name', '—')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
    )

    for m in ticket.get("messages", [])[-5:]:
        sender_ico = "👨‍💼" if m["sender_type"] == "dispatcher" else ("🤖" if m["sender_type"] == "system" else "👤")
        text += f"\n{sender_ico} **{m['sender_name']}** ({m['created_at']}):\n{m['message']}\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Написать сообщение диспетчеру", callback_data=f"send_msg_{ticket_id}")],
        [InlineKeyboardButton(text="🔄 Обновить статус", callback_data=f"view_ticket_{ticket_id}")]
    ])
    await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("send_msg_"))
async def handle_send_msg_prompt(callback: CallbackQuery, state: FSMContext):
    ticket_id = int(callback.data.replace("send_msg_", ""))
    await state.set_state(SupportChat.waiting_message)
    await state.update_data(ticket_id=ticket_id)
    await callback.message.answer("✏️ Введите текст сообщения для дежурного диспетчера Цырулева А. А.:")
    await callback.answer()

@router.message(SupportChat.waiting_message)
async def handle_user_support_message(message: Message, state: FSMContext):
    data = await state.get_data()
    ticket_id = data.get("ticket_id")
    text = message.text.strip()
    await state.clear()

    if ticket_id and text:
        database.add_ticket_message(ticket_id, sender_type="student", sender_name="Иванов М. В. (ИДБ-25-15)", message=text)
        await message.answer(f"✅ Сообщение отправлено диспетчеру {DISPATCHER_NAME}!\nОно мгновенно отобразилось на веб-панели диспетчера и в веб-чате.")
