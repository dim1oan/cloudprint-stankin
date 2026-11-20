from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)

def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню студенческого сервиса CloudPrint."""
    kb = [
        [
            KeyboardButton(text="🖨 Оформить печать"),
            KeyboardButton(text="📋 Мои заказы")
        ],
        [
            KeyboardButton(text="💳 Баланс и профиль"),
            KeyboardButton(text="🆘 Поддержка (Замятие E-04)")
        ],
        [
            KeyboardButton(text="👨‍💼 Панель диспетчера")
        ]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_file_choice_keyboard() -> InlineKeyboardMarkup:
    """Выбор готового образца или загрузка собственного файла."""
    kb = [
        [
            InlineKeyboardButton(text="📘 Курсовой проект (20 стр.)", callback_data="sample_file_1")
        ],
        [
            InlineKeyboardButton(text="📕 Дипломный проект (45 стр.)", callback_data="sample_file_2")
        ],
        [
            InlineKeyboardButton(text="📤 Отправьте файл PDF/DOCX в чат", callback_data="await_upload_hint")
        ],
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_wizard")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_gost_mode_keyboard(current_gost: bool) -> InlineKeyboardMarkup:
    """Выбор режима оформления по ГОСТ 7.32."""
    gost_icon = "🟢" if current_gost else "⚪"
    norm_icon = "🟢" if not current_gost else "⚪"
    kb = [
        [
            InlineKeyboardButton(text=f"{gost_icon} По ГОСТ 7.32 (СТАНКИН)", callback_data="set_gost_true"),
            InlineKeyboardButton(text=f"{norm_icon} Обычная печать", callback_data="set_gost_false")
        ],
        [
            InlineKeyboardButton(text="➡️ Далее к параметрам печати", callback_data="step_to_options")
        ],
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_wizard")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_options_keyboard(is_color: bool, is_stapling: bool) -> InlineKeyboardMarkup:
    """Настройка цветности (10 ₽/5 ₽) и скрепления степлером (+15 ₽)."""
    color_text = "🎨 Цветная (10 ₽/стр) ✅" if is_color else "🎨 Цветная (10 ₽/стр)"
    bw_text = "⚫ Ч/Б (5 ₽/стр) ✅" if not is_color else "⚫ Ч/Б (5 ₽/стр)"
    staple_text = "📎 Сшитие степлером (+15 ₽) ✅" if is_stapling else "📎 Сшитие степлером (+15 ₽) ❌"

    kb = [
        [
            InlineKeyboardButton(text=color_text, callback_data="opt_color_true"),
            InlineKeyboardButton(text=bw_text, callback_data="opt_color_false")
        ],
        [
            InlineKeyboardButton(text=staple_text, callback_data="opt_toggle_stapling")
        ],
        [
            InlineKeyboardButton(text="➡️ Далее к выбору терминала МФУ", callback_data="step_to_terminals")
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="step_back_to_gost")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_terminals_keyboard(terminals: list) -> InlineKeyboardMarkup:
    """Выбор терминала выдачи распечатки с индикацией статуса."""
    buttons = []
    for t in terminals:
        is_broken = t["status"] != "Онлайн"
        status_ico = "🔴" if is_broken else "🟢"
        label = f"{status_ico} {t['name']} ({t['status']})"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"select_term_{t['id']}")])

    buttons.append([InlineKeyboardButton(text="⬅️ Назад к параметрам", callback_data="step_back_to_options")])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_wizard")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_payment_keyboard(price_rub: float, user_balance: float) -> InlineKeyboardMarkup:
    """Выбор способа оплаты заказа (СБП или списание бонусов)."""
    bonus_can_pay = user_balance >= price_rub
    bonus_badge = "✅" if bonus_can_pay else "⚠️ Мало бонусов"

    kb = [
        [
            InlineKeyboardButton(text=f"📱 Оплатить через СБП ({price_rub:.2f} ₽)", callback_data="pay_sbp")
        ],
        [
            InlineKeyboardButton(text=f"🪙 Бонусами ({price_rub:.2f} ₽) [{bonus_badge}]", callback_data="pay_bonus")
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад к терминалам", callback_data="step_back_to_terminals")
        ],
        [
            InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_wizard")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_dispatcher_menu_keyboard() -> InlineKeyboardMarkup:
    """Главная панель диспетчера техподдержки и инженера."""
    kb = [
        [
            InlineKeyboardButton(text="📊 Телеметрия МФУ", callback_data="disp_telemetry"),
            InlineKeyboardButton(text="📥 Очередь тикетов", callback_data="disp_tickets")
        ],
        [
            InlineKeyboardButton(text="🧪 Стенд симуляции (Demo Mode)", callback_data="disp_simulation")
        ],
        [
            InlineKeyboardButton(text="🔄 Сброс БД к эталонным данным", callback_data="disp_reset_demo")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)
