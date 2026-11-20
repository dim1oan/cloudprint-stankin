from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from keyboards import get_dispatcher_menu_keyboard
import database
from config import DISPATCHER_NAME

router = Router()

@router.message(F.text == "👨‍💼 Панель диспетчера")
async def show_dispatcher_panel(message: Message):
    """Главная панель диспетчера и администратора (Цырулев А. А.)."""
    text = (
        f"👨‍💼 **Панель диспетчера техподдержки CloudPrint**\n"
        f"Дежурный инженер-диспетчер: **{DISPATCHER_NAME}**\n\n"
        f"Выберите раздел управления комплексом смарт-полиграфии 👇"
    )
    await message.answer(text, reply_markup=get_dispatcher_menu_keyboard(), parse_mode="Markdown")

@router.callback_query(F.data == "disp_telemetry")
async def handle_disp_telemetry(callback: CallbackQuery):
    """Просмотр телеметрии МФУ (бумага, тонер, скобы) и пульт инженера."""
    terms = database.get_terminals_list()

    text = "📊 **Телеметрия лазерных МФУ CloudPrint СТАНКИН:**\n━━━━━━━━━━━━━━━━━━━━━\n"
    buttons = []

    for t in terms:
        is_error = t["status"] in ("Замятие E-04", "Ожидает ТО")
        status_ico = "🔴" if is_error else "🟢"

        text += (
            f"\n{status_ico} **{t['name']}** (`{t['code']}`)\n"
            f"• Статус: **{t['status']}**\n"
            f"• Локация: {t['location']}\n"
            f"• 🧻 Бумага: `{t['paper_sheets']} / {t['paper_max']} л.` ({t['paper_percent']}%)\n"
            f"• 🧪 Тонер (TK-1150): `R_toner = {t['toner_percent']}%` (~{t['toner_pages_left']} стр.)\n"
            f"• 📎 Степлерный модуль: `{t['staples_count']} / {t['staples_max']} скоб` ({t['staples_percent']}%)\n"
            f"• IP: `{t['ip_address']}` • Отпечатано: `{t['total_printed_pages']} стр.`\n"
        )

        buttons.append([
            InlineKeyboardButton(text=f"🧻 Бумага +500 ({t['code']})", callback_data=f"eng_paper_{t['id']}"),
            InlineKeyboardButton(text=f"🧪 Тонер ({t['code']})", callback_data=f"eng_toner_{t['id']}"),
            InlineKeyboardButton(text=f"🛠 Сброс E-04 ({t['code']})", callback_data=f"eng_jam_{t['id']}")
        ])

    buttons.append([InlineKeyboardButton(text="🔄 Обновить телеметрию", callback_data="disp_telemetry")])
    buttons.append([InlineKeyboardButton(text="⬅️ В меню диспетчера", callback_data="disp_back_to_menu")])

    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="Markdown")

@router.callback_query(F.data.startswith("eng_paper_"))
async def handle_eng_paper(callback: CallbackQuery):
    term_id = int(callback.data.replace("eng_paper_", ""))
    database.refill_paper(term_id)
    await callback.answer("Бумага заправлена (500 листов)!", show_alert=True)
    await handle_disp_telemetry(callback)

@router.callback_query(F.data.startswith("eng_toner_"))
async def handle_eng_toner(callback: CallbackQuery):
    term_id = int(callback.data.replace("eng_toner_", ""))
    database.replace_cartridge(term_id)
    await callback.answer("Тонер-картридж TK-1150 заменен, ресурс сброшен!", show_alert=True)
    await handle_disp_telemetry(callback)

@router.callback_query(F.data.startswith("eng_jam_"))
async def handle_eng_jam(callback: CallbackQuery):
    term_id = int(callback.data.replace("eng_jam_", ""))
    database.clear_jam(term_id)
    await callback.answer("Замятие устранено, статус МФУ восстановлен в Онлайн!", show_alert=True)
    await handle_disp_telemetry(callback)

@router.callback_query(F.data == "disp_tickets")
async def handle_disp_tickets(callback: CallbackQuery):
    """Очередь тикетов техподдержки."""
    tickets = database.get_tickets_list(limit=5)
    if not tickets:
        await callback.answer("Нет активных обращений в очереди", show_alert=True)
        return

    text = f"📥 **Очередь обращений техподдержки ({len(tickets)} шт.):**\n\n"
    buttons = []

    for t in tickets:
        status_ico = "🟢" if t["status"] == "Решен" else "🟡"
        btn_text = f"{status_ico} {t['ticket_number']} • {t['user_name']} ({t.get('order_code', '—')})"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"disp_ticket_card_{t['id']}")])

    buttons.append([InlineKeyboardButton(text="⬅️ В меню диспетчера", callback_data="disp_back_to_menu")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="Markdown")

@router.callback_query(F.data.startswith("disp_ticket_card_"))
async def handle_disp_ticket_card(callback: CallbackQuery):
    """Карточка тикета с кнопками управления диспетчера."""
    ticket_id = int(callback.data.replace("disp_ticket_card_", ""))
    t = database.get_ticket_details(ticket_id)
    if not t:
        await callback.answer("Тикет не найден", show_alert=True)
        return

    text = (
        f"👨‍💼 **Карточка обращения `{t['ticket_number']}`**\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"• Студент: **{t['user_name']}** ({t['user_group']})\n"
        f"• Студенческий билет: `{t['student_card']}`\n"
        f"• Баланс студента: `{t['balance_rub']:.2f} ₽`\n"
        f"• Заказ: `{t.get('order_code', '—')}` (стоимость: {t.get('price_rub', 0):.2f} ₽)\n"
        f"• Текущее МФУ: **{t.get('terminal_name', '—')}**\n"
        f"• Статус тикета: `{t['status']}`\n"
        f"• Выплачено компенсации: `{t['compensation_rub']:.2f} ₽`\n"
    )

    buttons = [
        [
            InlineKeyboardButton(text="🔄 Перевести на 2-й корпус (без компенсации)", callback_data=f"disp_reroute_{ticket_id}")
        ],
        [
            InlineKeyboardButton(text=f"💰 Вернуть средства 100% ({t.get('price_rub', 0):.2f} ₽)", callback_data=f"disp_comp_{ticket_id}")
        ],
        [
            InlineKeyboardButton(text="🛠 Вызов дежурного инженера (Ожидает ТО)", callback_data=f"disp_tech_{ticket_id}")
        ],
        [
            InlineKeyboardButton(text="✅ Закрыть тикет (Решено)", callback_data=f"disp_resolve_{ticket_id}")
        ],
        [
            InlineKeyboardButton(text="⬅️ К списку тикетов", callback_data="disp_tickets")
        ]
    ]

    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="Markdown")

@router.callback_query(F.data.startswith("disp_reroute_"))
async def handle_disp_reroute(callback: CallbackQuery):
    ticket_id = int(callback.data.replace("disp_reroute_", ""))
    res = database.reroute_order_to_campus(ticket_id, dispatcher_name=DISPATCHER_NAME)
    await callback.answer("🔄 Заказ успешно перенаправлен на 2-й корпус без компенсации! Сгенерирован новый пин-код.", show_alert=True)
    await handle_disp_ticket_card(callback)

@router.callback_query(F.data.startswith("disp_comp_"))
async def handle_disp_comp(callback: CallbackQuery):
    ticket_id = int(callback.data.replace("disp_comp_", ""))
    res = database.compensate_ticket_100(ticket_id, dispatcher_name=DISPATCHER_NAME)
    amt = res["compensation_added"] if res else 200.0
    await callback.answer(f"💰 Начислена 100% компенсация (+{amt:.2f} ₽) на баланс студента! Заказ отменен.", show_alert=True)
    await handle_disp_ticket_card(callback)

@router.callback_query(F.data.startswith("disp_tech_"))
async def handle_disp_tech(callback: CallbackQuery):
    ticket_id = int(callback.data.replace("disp_tech_", ""))
    database.call_on_duty_technician(ticket_id, dispatcher_name=DISPATCHER_NAME)
    await callback.answer("🛠 Дежурный инженер вызван к МФУ! Статус переведен в «Ожидает ТО».", show_alert=True)
    await handle_disp_ticket_card(callback)

@router.callback_query(F.data.startswith("disp_resolve_"))
async def handle_disp_resolve(callback: CallbackQuery):
    ticket_id = int(callback.data.replace("disp_resolve_", ""))
    database.resolve_ticket(ticket_id, dispatcher_name=DISPATCHER_NAME)
    await callback.answer("✅ Обращение успешно закрыто и помечено решенным!", show_alert=True)
    await handle_disp_ticket_card(callback)

@router.callback_query(F.data == "disp_simulation")
async def handle_disp_simulation(callback: CallbackQuery):
    """Стенд симуляции работы оборудования (Demo Mode)."""
    text = (
        "🧪 **Интерактивный стенд симуляции CloudPrint СТАНКИН:**\n\n"
        "Выберите сценарий для проверки поведения комплекса 👇"
    )
    buttons = [
        [
            InlineKeyboardButton(text="🖨 Печать 20 стр. на МФУ №2", callback_data="sim_print_no_staple"),
            InlineKeyboardButton(text="📎 Печать 20 стр. со сшивкой", callback_data="sim_print_staple")
        ],
        [
            InlineKeyboardButton(text="🚨 Смоделировать аварию E-04", callback_data="sim_jam")
        ],
        [
            InlineKeyboardButton(text="⬅️ В меню диспетчера", callback_data="disp_back_to_menu")
        ]
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="Markdown")

@router.callback_query(F.data == "sim_print_no_staple")
async def handle_sim_print_no_staple(callback: CallbackQuery):
    res = database.simulate_print_job(terminal_id=2, pages=20, stapling=False)
    if isinstance(res, dict) and "error" in res:
        await callback.answer(res["error"], show_alert=True)
    else:
        await callback.answer("Печать 20 стр. смоделирована: бумага -20л, тонер пересчитан!", show_alert=True)

@router.callback_query(F.data == "sim_print_staple")
async def handle_sim_print_staple(callback: CallbackQuery):
    res = database.simulate_print_job(terminal_id=2, pages=20, stapling=True)
    if isinstance(res, dict) and "error" in res:
        await callback.answer(res["error"], show_alert=True)
    else:
        await callback.answer("Печать 20 стр. смоделирована: бумага -20л, скоба степлера -1 шт.!", show_alert=True)

@router.callback_query(F.data == "sim_jam")
async def handle_sim_jam(callback: CallbackQuery):
    res = database.simulate_jam_event(terminal_id=2)
    await callback.answer(f"⚠️ Авария E-04 смоделирована! Создан тикет {res['ticket_number']}.", show_alert=True)

@router.callback_query(F.data == "disp_reset_demo")
async def handle_disp_reset_demo(callback: CallbackQuery):
    database.init_db(force_reseed=True)
    await callback.answer("База данных успешно возвращена к эталонным демо-данным!", show_alert=True)
    await handle_disp_telemetry(callback)

@router.callback_query(F.data == "disp_back_to_menu")
async def handle_disp_back_to_menu(callback: CallbackQuery):
    text = (
        f"👨‍💼 **Панель диспетчера техподдержки CloudPrint**\n"
        f"Дежурный инженер-диспетчер: **{DISPATCHER_NAME}**\n\n"
        f"Выберите раздел управления комплексом смарт-полиграфии 👇"
    )
    await callback.message.edit_text(text, reply_markup=get_dispatcher_menu_keyboard(), parse_mode="Markdown")
