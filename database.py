"""
Модуль базы данных SQLite3 для системы CloudPrint СТАНКИН.
Локальная система облачной студенческой смарт-полиграфии МГТУ «СТАНКИН».
Разработчики: Цырулев А. А. (диспетчер техподдержки), Ткачук Д. В. (тех. администратор).
"""

import sqlite3
import os
import random
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cloudprint.db")

def get_db_connection():
    """Возвращает соединение с базой данных с поддержкой доступа по именам колонок."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def calculate_toner_percent(toner_printed_pages: int, nominal_pages: int = 3000) -> float:
    """
    Расчет примерного остатка тонера (R_toner):
    R_toner = max(0, 100 * (1 - N_printed / 3000)) (при k=1).
    """
    if nominal_pages <= 0:
        return 0.0
    r_toner = 100.0 * (1.0 - (float(toner_printed_pages) / float(nominal_pages)))
    return round(max(0.0, min(100.0, r_toner)), 1)

def determine_terminal_status(current_status: str, paper_sheets: int, toner_percent: float) -> str:
    """Определяет актуальный статус терминала с учетом приоритета аппаратных ошибок."""
    if current_status in ("Замятие E-04", "Ожидает ТО"):
        return current_status
    if paper_sheets <= 30:
        return "Мало бумаги"
    if toner_percent <= 10.0:
        return "Мало тонера"
    return "Онлайн"

def init_db(force_reseed: bool = False):
    """Инициализация таблиц базы данных и заполнение начальными демо-данными."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Таблица терминалов (МФУ на площадках МГТУ «СТАНКИН»)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS terminals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        campus TEXT NOT NULL,
        location TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Онлайн',
        paper_sheets INTEGER NOT NULL DEFAULT 500,
        paper_max INTEGER NOT NULL DEFAULT 500,
        toner_printed_pages INTEGER NOT NULL DEFAULT 0,
        total_printed_pages INTEGER NOT NULL DEFAULT 0,
        cartridge_model TEXT NOT NULL DEFAULT 'TK-1150',
        cartridge_nominal INTEGER NOT NULL DEFAULT 3000,
        staples_count INTEGER NOT NULL DEFAULT 5000,
        staples_max INTEGER NOT NULL DEFAULT 5000,
        ip_address TEXT NOT NULL,
        last_service TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)

    # Миграция: проверка наличия столбцов staples_count и staples_max в таблице terminals
    cursor.execute("PRAGMA table_info(terminals)")
    term_cols = [c["name"] for c in cursor.fetchall()]
    if "staples_count" not in term_cols:
        cursor.execute("ALTER TABLE terminals ADD COLUMN staples_count INTEGER DEFAULT 5000")
    if "staples_max" not in term_cols:
        cursor.execute("ALTER TABLE terminals ADD COLUMN staples_max INTEGER DEFAULT 5000")

    # Таблица пользователей (студентов и сотрудников)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        group_code TEXT NOT NULL,
        student_card TEXT UNIQUE NOT NULL,
        balance_rub REAL NOT NULL DEFAULT 0.0,
        email TEXT NOT NULL,
        telegram_chat_id INTEGER,
        created_at TEXT NOT NULL
    )
    """)

    # Миграция: проверка наличия столбца telegram_chat_id в таблице users
    cursor.execute("PRAGMA table_info(users)")
    user_cols = [c["name"] for c in cursor.fetchall()]
    if "telegram_chat_id" not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN telegram_chat_id INTEGER")

    # Таблица заказов на печать
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_code TEXT UNIQUE NOT NULL,
        user_id INTEGER NOT NULL,
        terminal_id INTEGER NOT NULL,
        file_name TEXT NOT NULL,
        page_count INTEGER NOT NULL,
        price_rub REAL NOT NULL,
        status TEXT NOT NULL DEFAULT 'Завершен',
        pickup_code TEXT,
        is_gost INTEGER DEFAULT 1,
        stapling INTEGER DEFAULT 0,
        is_color INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id),
        FOREIGN KEY (terminal_id) REFERENCES terminals (id)
    )
    """)

    # Миграция: проверка наличия столбцов is_gost, stapling, is_color в существующей таблице orders
    cursor.execute("PRAGMA table_info(orders)")
    order_cols = [c["name"] for c in cursor.fetchall()]
    if "is_gost" not in order_cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN is_gost INTEGER DEFAULT 1")
    if "stapling" not in order_cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN stapling INTEGER DEFAULT 0")
    if "is_color" not in order_cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN is_color INTEGER DEFAULT 1")

    # Таблица обращений в техподдержку (тикетов)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_number TEXT UNIQUE NOT NULL,
        user_id INTEGER NOT NULL,
        order_id INTEGER,
        terminal_id INTEGER NOT NULL,
        issue_type TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'В работе',
        compensation_rub REAL NOT NULL DEFAULT 0.0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id),
        FOREIGN KEY (order_id) REFERENCES orders (id),
        FOREIGN KEY (terminal_id) REFERENCES terminals (id)
    )
    """)

    # Таблица сообщений в чате тикета
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ticket_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_id INTEGER NOT NULL,
        sender_type TEXT NOT NULL, -- 'student', 'dispatcher', 'system'
        sender_name TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (ticket_id) REFERENCES tickets (id) ON DELETE CASCADE
    )
    """)

    # Таблица финансовых транзакций (компенсации, пополнения)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        ticket_id INTEGER,
        amount_rub REAL NOT NULL,
        transaction_type TEXT NOT NULL, -- 'Компенсация', 'Пополнение', 'Списание'
        description TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id),
        FOREIGN KEY (ticket_id) REFERENCES tickets (id)
    )
    """)

    # Таблица системных настроек и кастомных параметров (например, стикеров)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """)

    conn.commit()

    # Проверка на необходимость предзаполнения
    cursor.execute("SELECT COUNT(*) as count FROM terminals")
    terminals_count = cursor.fetchone()["count"]

    if terminals_count == 0 or force_reseed:
        if force_reseed:
            cursor.execute("DELETE FROM ticket_messages")
            cursor.execute("DELETE FROM transactions")
            cursor.execute("DELETE FROM tickets")
            cursor.execute("DELETE FROM orders")
            cursor.execute("DELETE FROM users")
            cursor.execute("DELETE FROM terminals")
            conn.commit()

        seed_demo_data(conn)

    conn.close()

def seed_demo_data(conn):
    """Наполнение базы реалистичными демонстрационными данными по МГТУ СТАНКИН."""
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. Терминалы МФУ
    # Терминал №1 в Старом корпусе создается с ошибкой замятия (E-04) для эффектного старта защиты
    terminals_data = [
        (
            1, "STANKIN-OLD-01", "Терминал №1 (Старый корпус)", "Старый корпус",
            "Старый корпус, холл 1 этажа (рядом с гардеробом)", "Замятие E-04",
            140, 500, 1240, 14240, "TK-1150", 3000, 4850, 5000,
            "192.168.10.15", "2026-11-19 18:00:00", now_str
        ),
        (
            2, "STANKIN-NEW-01", "Терминал №2 (Новый корпус)", "Новый корпус",
            "Новый корпус, холл 1 этажа (у поста с охраной)", "Онлайн",
            460, 500, 410, 8410, "TK-1150", 3000, 4910, 5000,
            "192.168.10.22", "2026-11-20 08:30:00", now_str
        )
    ]
    cursor.executemany("""
    INSERT OR REPLACE INTO terminals (
        id, code, name, campus, location, status,
        paper_sheets, paper_max, toner_printed_pages, total_printed_pages,
        cartridge_model, cartridge_nominal, staples_count, staples_max, ip_address, last_service, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, terminals_data)

    # 2. Пользователи (студенты)
    users_data = [
        (1, "Иванов М. В.", "ИДБ-25-15", "СТ-2025-0149", 150.00, "ivanov.m@stankin.ru", now_str),
        (2, "Смирнова А. Д.", "ИДБ-25-12", "СТ-2025-0210", 320.00, "smirnova.a@stankin.ru", now_str),
        (3, "Кузнецов А. С.", "ИДБ-24-08", "СТ-2024-0881", 45.00, "kuznetsov.a@stankin.ru", now_str),
        (4, "Васильева Е. П.", "ИДБ-25-15", "СТ-2025-0155", 210.00, "vasilieva.e@stankin.ru", now_str)
    ]
    cursor.executemany("""
    INSERT OR REPLACE INTO users (
        id, full_name, group_code, student_card, balance_rub, email, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, users_data)

    # 3. Заказы
    orders_data = [
        (1, "ORD-78129", 1, 1, "Курсовой_проект_Детали_машин_Иванов.pdf", 45, 225.00, "Ошибка печати", None, "2026-11-20 12:35:00"),
        (2, "ORD-78092", 2, 2, "Лабораторная_3_САПР_Смирнова.docx", 16, 80.00, "Завершен", None, "2026-11-20 11:40:00"),
        (3, "ORD-77984", 3, 1, "Чертеж_А4_Редуктор_Кузнецов.pdf", 8, 40.00, "Завершен", None, "2026-11-19 16:15:00"),
        (4, "ORD-78140", 4, 2, "Расчетно_графическая_работа_ТММ.pdf", 28, 140.00, "Завершен", None, "2026-11-20 12:45:00")
    ]
    cursor.executemany("""
    INSERT OR REPLACE INTO orders (
        id, order_code, user_id, terminal_id, file_name, page_count, price_rub, status, pickup_code, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, orders_data)

    # 4. Начальные тикеты в техподдержку
    tickets_data = [
        (
            1, "TCK-2026-001", 1, 1, 1,
            "Замятие бумаги (E-04)", "В работе", 0.0,
            "2026-11-20 12:36:12", now_str
        )
    ]
    cursor.executemany("""
    INSERT OR REPLACE INTO tickets (
        id, ticket_number, user_id, order_id, terminal_id, issue_type, status, compensation_rub, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, tickets_data)

    # 5. Сообщения в чате
    messages_data = [
        (
            1, 1, "student", "Иванов М. В. (ИДБ-25-15)",
            "Здравствуйте! Отправил на печать курсовой проект (заказ ORD-78129, 45 стр.). На 12 странице терминал затрещал и выдал на экране ошибку «E-04: Замятие бумаги»! С баланса списалось 225 руб., а листы застряли внутри лотка. Срочно нужно сдать преподавателю, помогите!",
            "2026-11-20 12:36:12"
        ),
        (
            2, 1, "dispatcher", "Цырулев А. А. (Диспетчер)",
            "Здравствуйте, Михаил! Зафиксировал проблему со Старым корпусом (STANKIN-OLD-01). Телеметрия подтверждает аппаратный сбой E-04. Сейчас решим вопрос с компенсацией и перенаправим печать на Новый корпус.",
            "2026-11-20 12:38:00"
        )
    ]
    cursor.executemany("""
    INSERT OR REPLACE INTO ticket_messages (
        id, ticket_id, sender_type, sender_name, message, created_at
    ) VALUES (?, ?, ?, ?, ?, ?)
    """, messages_data)

    # 6. Начальные финансовые транзакции
    transactions_data = [
        (1, 1, None, 300.00, "Пополнение", "Пополнение через СБП СТАНКИН", "2026-11-18 10:00:00"),
        (2, 1, None, -225.00, "Списание", "Оплата заказа ORD-78129 (45 стр.)", "2026-11-20 12:35:00"),
        (3, 2, None, 400.00, "Пополнение", "Пополнение картой МИР", "2026-11-19 14:00:00"),
        (4, 2, None, -80.00, "Списание", "Оплата заказа ORD-78092 (16 стр.)", "2026-11-20 11:40:00")
    ]
    cursor.executemany("""
    INSERT OR REPLACE INTO transactions (
        id, user_id, ticket_id, amount_rub, transaction_type, description, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, transactions_data)

    conn.commit()

# --- ФУНКЦИИ ДЛЯ РАБОТЫ С ТЕРМИНАЛАМИ ---

def get_terminals_list():
    """Возвращает список всех терминалов с рассчитанным процентом тонера и состоянием."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM terminals ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()

    terminals = []
    for r in rows:
        toner_pct = calculate_toner_percent(r["toner_printed_pages"], r["cartridge_nominal"])
        computed_status = determine_terminal_status(r["status"], r["paper_sheets"], toner_pct)
        terminals.append({
            "id": r["id"],
            "code": r["code"],
            "name": r["name"],
            "campus": r["campus"],
            "location": r["location"],
            "status": computed_status,
            "raw_status": r["status"],
            "paper_sheets": r["paper_sheets"],
            "paper_max": r["paper_max"],
            "paper_percent": round(100.0 * r["paper_sheets"] / r["paper_max"], 1),
            "toner_printed_pages": r["toner_printed_pages"],
            "total_printed_pages": r["total_printed_pages"],
            "cartridge_model": r["cartridge_model"],
            "cartridge_nominal": r["cartridge_nominal"],
            "toner_percent": toner_pct,
            "toner_pages_left": max(0, r["cartridge_nominal"] - r["toner_printed_pages"]),
            "staples_count": r["staples_count"] if "staples_count" in r.keys() else 4900,
            "staples_max": r["staples_max"] if "staples_max" in r.keys() else 5000,
            "staples_percent": round(100.0 * (r["staples_count"] if "staples_count" in r.keys() else 4900) / (r["staples_max"] if "staples_max" in r.keys() else 5000), 1),
            "ip_address": r["ip_address"],
            "last_service": r["last_service"],
            "updated_at": r["updated_at"]
        })
    return terminals

def get_terminal(terminal_id: int):
    """Получение одного терминала по ID."""
    terminals = get_terminals_list()
    for t in terminals:
        if t["id"] == terminal_id:
            return t
    return None

def refill_paper(terminal_id: int, amount: int = 500):
    """Заправка бумаги в терминал дежурным специалистом."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT paper_max, status FROM terminals WHERE id = ?", (terminal_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    paper_max = row["paper_max"]
    new_paper = paper_max
    current_status = row["status"]
    new_status = "Онлайн" if current_status == "Мало бумаги" else current_status
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
    UPDATE terminals 
    SET paper_sheets = ?, status = ?, last_service = ?, updated_at = ?
    WHERE id = ?
    """, (new_paper, new_status, now_str, now_str, terminal_id))
    conn.commit()
    conn.close()
    return get_terminal(terminal_id)

def replace_cartridge(terminal_id: int):
    """Замена тонер-картриджа TK-1150 и сброс счетчика отпечатанных страниц тонера."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM terminals WHERE id = ?", (terminal_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    current_status = row["status"]
    new_status = "Онлайн" if current_status == "Мало тонера" else current_status
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
    UPDATE terminals 
    SET toner_printed_pages = 0, status = ?, last_service = ?, updated_at = ?
    WHERE id = ?
    """, (new_status, now_str, now_str, terminal_id))
    conn.commit()
    conn.close()
    return get_terminal(terminal_id)

def clear_jam(terminal_id: int):
    """Сброс ошибки замятия бумаги (E-04) дежурным специалистом площадки."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT paper_sheets, toner_printed_pages, cartridge_nominal FROM terminals WHERE id = ?", (terminal_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    toner_pct = calculate_toner_percent(row["toner_printed_pages"], row["cartridge_nominal"])
    new_status = determine_terminal_status("Онлайн", row["paper_sheets"], toner_pct)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
    UPDATE terminals 
    SET status = ?, last_service = ?, updated_at = ?
    WHERE id = ?
    """, (new_status, now_str, now_str, terminal_id))
    conn.commit()
    conn.close()
    return get_terminal(terminal_id)

def simulate_print_job(terminal_id: int, pages: int = 20, create_order: bool = True, stapling: bool = False):
    """
    Симуляция процесса печати:
    - Проверяет статус терминала (БАГ №2: запрет печати на сломанном МФУ);
    - Прибавляет `pages` к счетчикам отпечатанных страниц;
    - Вычитает `pages` листов бумаги;
    - Если stapling=True, расходует 1 скобу из степлерного модуля;
    - Если create_order=True, создает запись завершенного заказа в БД.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM terminals WHERE id = ?", (terminal_id,))
    term = cursor.fetchone()
    if not term:
        conn.close()
        return {"error": "Терминал не найден"}

    # БАГ №2: Запрет печати на терминале с ошибкой (E-04, Ожидает ТО)
    if term["status"] in ("Замятие E-04", "Ожидает ТО"):
        conn.close()
        return {
            "error": f"Печать невозможна! Терминал «{term['name']}» заблокирован со статусом «{term['status']}». Сначала устраните сбой!"
        }

    # Проверка наличия бумаги
    if term["paper_sheets"] < pages:
        conn.close()
        return {
            "error": f"Печать отклонена: в лотке терминала «{term['name']}» недостаточно бумаги ({term['paper_sheets']} л. из требуемых {pages} л.)."
        }

    # Проверка наличия тонера
    toner_pct = calculate_toner_percent(term["toner_printed_pages"], term["cartridge_nominal"])
    if toner_pct <= 0:
        conn.close()
        return {
            "error": f"Печать отклонена: в картридже терминала «{term['name']}» закончился тонер (0%)."
        }

    new_paper = max(0, term["paper_sheets"] - pages)
    new_toner_pages = term["toner_printed_pages"] + pages
    new_total_pages = term["total_printed_pages"] + pages
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur_staples = term["staples_count"] if "staples_count" in term.keys() else 5000
    new_staples = max(0, cur_staples - (1 if stapling else 0))

    new_toner_pct = calculate_toner_percent(new_toner_pages, term["cartridge_nominal"])
    status = term["status"]
    if status not in ("Замятие E-04", "Ожидает ТО"):
        if new_paper <= 0:
            status = "Мало бумаги"
        elif new_toner_pct <= 0:
            status = "Мало тонера"

    cursor.execute("""
    UPDATE terminals 
    SET paper_sheets = ?, toner_printed_pages = ?, total_printed_pages = ?, staples_count = ?, status = ?, updated_at = ?
    WHERE id = ?
    """, (new_paper, new_toner_pages, new_total_pages, new_staples, status, now_str, terminal_id))

    if create_order:
        # Создаем запись симулированного заказа
        rand_code = f"ORD-{random.randint(10000, 99999)}"
        cursor.execute("SELECT id FROM users ORDER BY RANDOM() LIMIT 1")
        user_row = cursor.fetchone()
        user_id = user_row["id"] if user_row else 1
        file_names = [
            "Отчет_по_практике_СТАНКИН.pdf",
            "Методические_указания_ТММ.pdf",
            "Пояснительная_записка_ВКР.docx",
            "Чертеж_Сборочный_Узел_А4.pdf",
            "Лабораторный_практикум_Физика.docx"
        ]
        file_name = random.choice(file_names)
        price = round(pages * 5.0, 2)

        cursor.execute("""
        INSERT INTO orders (order_code, user_id, terminal_id, file_name, page_count, price_rub, status, stapling, is_color, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'Завершен', ?, 1, ?)
        """, (rand_code, user_id, terminal_id, file_name, pages, price, 1 if stapling else 0, now_str))

    conn.commit()
    conn.close()
    return get_terminal(terminal_id)

def simulate_jam_event(terminal_id: int):
    """
    Симуляция замятия бумаги (E-04):
    - Переводит терминал в статус 'Замятие E-04';
    - Создает аварийный заказ со статусом 'Ошибка печати';
    - Создает новый тикет в техподдержку и первое сообщение от пострадавшего студента.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("SELECT * FROM terminals WHERE id = ?", (terminal_id,))
    term = cursor.fetchone()
    if not term:
        conn.close()
        return None

    # Переводим статус в Замятие E-04
    cursor.execute("""
    UPDATE terminals SET status = 'Замятие E-04', updated_at = ? WHERE id = ?
    """, (now_str, terminal_id))

    # Выбираем случайного студента
    cursor.execute("SELECT * FROM users ORDER BY RANDOM() LIMIT 1")
    user = cursor.fetchone()
    if not user:
        user = {"id": 1, "full_name": "Иванов М. В.", "group_code": "ИДБ-25-15"}

    # Создаем заказ с ошибкой печати
    rand_order_code = f"ORD-{random.randint(10000, 99999)}"
    pages = random.choice([25, 30, 40, 52])
    cost = round(pages * 5.0, 2)
    doc_name = random.choice([
        "Дипломный_проект_СТАНКИН_Раздел_4.pdf",
        "Расчет_на_прочность_Вал_Редуктора.docx",
        "Курсовая_работа_Метрология.pdf"
    ])

    cursor.execute("""
    INSERT INTO orders (order_code, user_id, terminal_id, file_name, page_count, price_rub, status, created_at)
    VALUES (?, ?, ?, ?, ?, ?, 'Ошибка печати', ?)
    """, (rand_order_code, user["id"], terminal_id, doc_name, pages, cost, now_str))
    order_id = cursor.lastrowid

    # Списываем средства за этот заказ
    cursor.execute("""
    UPDATE users SET balance_rub = balance_rub - ? WHERE id = ?
    """, (cost, user["id"]))
    cursor.execute("""
    INSERT INTO transactions (user_id, ticket_id, amount_rub, transaction_type, description, created_at)
    VALUES (?, NULL, ?, 'Списание', ?, ?)
    """, (user["id"], -cost, f"Оплата аварийного заказа {rand_order_code} ({pages} стр.)", now_str))

    # Создаем тикет
    rand_ticket_num = f"TCK-2026-{random.randint(100, 999)}"
    cursor.execute("""
    INSERT INTO tickets (ticket_number, user_id, order_id, terminal_id, issue_type, status, compensation_rub, created_at, updated_at)
    VALUES (?, ?, ?, ?, 'Замятие бумаги (E-04)', 'В работе', 0.0, ?, ?)
    """, (rand_ticket_num, user["id"], order_id, terminal_id, now_str, now_str))
    ticket_id = cursor.lastrowid

    # Создаем первое тревожное сообщение от студента
    msg_text = (
        f"Зажевало бумагу! Терминал издал громкий треск и заблокировался с кодом «E-04: Замятие бумаги». "
        f"Печать файла «{doc_name}» прервалась, списано {cost:.0f} руб. Помогите вернуть деньги или перенесите заказ на другой корпус!"
    )
    sender_name = f"{user['full_name']} ({user['group_code']})"
    cursor.execute("""
    INSERT INTO ticket_messages (ticket_id, sender_type, sender_name, message, created_at)
    VALUES (?, 'student', ?, ?, ?)
    """, (ticket_id, sender_name, msg_text, now_str))

    conn.commit()
    conn.close()
    return {
        "terminal": get_terminal(terminal_id),
        "ticket_id": ticket_id,
        "ticket_number": rand_ticket_num,
        "user_name": user["full_name"],
        "order_code": rand_order_code
    }

# --- ФУНКЦИИ ДИСПЕТЧЕРА И ТЕХПОДДЕРЖКИ ---

def get_tickets_list(status_filter: str = None):
    """Получение списка обращений в техподдержку с данными пользователя и заказа."""
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
    SELECT 
        t.id, t.ticket_number, t.issue_type, t.status, t.compensation_rub, t.created_at, t.updated_at,
        u.id as user_id, u.full_name as user_name, u.group_code as user_group, u.student_card, u.balance_rub,
        o.id as order_id, o.order_code, o.file_name, o.page_count, o.price_rub, o.status as order_status, o.pickup_code,
        term.id as terminal_id, term.code as terminal_code, term.name as terminal_name, term.campus as terminal_campus
    FROM tickets t
    JOIN users u ON t.user_id = u.id
    LEFT JOIN orders o ON t.order_id = o.id
    JOIN terminals term ON t.terminal_id = term.id
    """
    params = []
    if status_filter:
        query += " WHERE t.status = ?"
        params.append(status_filter)

    query += " ORDER BY t.id DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    tickets = []
    for r in rows:
        tickets.append(dict(r))
    return tickets

def get_ticket_details(ticket_id: int):
    """Детальная информация о тикете вместе со всей историей переписки."""
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
    SELECT 
        t.id, t.ticket_number, t.issue_type, t.status, t.compensation_rub, t.created_at, t.updated_at,
        u.id as user_id, u.full_name as user_name, u.group_code as user_group, u.student_card, u.balance_rub, u.email as user_email,
        o.id as order_id, o.order_code, o.file_name, o.page_count, o.price_rub, o.status as order_status, o.pickup_code,
        term.id as terminal_id, term.code as terminal_code, term.name as terminal_name, term.campus as terminal_campus, term.status as terminal_status
    FROM tickets t
    JOIN users u ON t.user_id = u.id
    LEFT JOIN orders o ON t.order_id = o.id
    JOIN terminals term ON t.terminal_id = term.id
    WHERE t.id = ?
    """
    cursor.execute(query, (ticket_id,))
    ticket_row = cursor.fetchone()
    if not ticket_row:
        conn.close()
        return None

    ticket = dict(ticket_row)

    # Получаем сообщения
    cursor.execute("""
    SELECT id, sender_type, sender_name, message, created_at
    FROM ticket_messages
    WHERE ticket_id = ?
    ORDER BY id ASC
    """, (ticket_id,))
    messages = [dict(m) for m in cursor.fetchall()]
    ticket["messages"] = messages

    conn.close()
    return ticket

def add_ticket_message(ticket_id: int, sender_type: str, sender_name: str, message: str):
    """Добавление сообщения в чат тикета."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
    INSERT INTO ticket_messages (ticket_id, sender_type, sender_name, message, created_at)
    VALUES (?, ?, ?, ?, ?)
    """, (ticket_id, sender_type, sender_name, message, now_str))

    cursor.execute("UPDATE tickets SET updated_at = ? WHERE id = ?", (now_str, ticket_id))
    conn.commit()
    conn.close()
    return get_ticket_details(ticket_id)

def compensate_student(ticket_id: int, amount_rub: float = None, dispatcher_name: str = "Цырулев А. А."):
    """
    Начисление компенсации студенту (100% стоимости заказа, 1 балл = 1 рубль):
    - БАГ 1: Автоматически берет сумму стоимости привязанного заказа без ручного ввода;
    - Пополняет баланс студента в БД;
    - Создает запись транзакции;
    - Обновляет сумму компенсации в тикете;
    - Добавляет информационное сообщение в чат тикета.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
    SELECT t.user_id, t.order_id, t.compensation_rub,
           o.price_rub, o.order_code, o.file_name, o.page_count
    FROM tickets t
    LEFT JOIN orders o ON t.order_id = o.id
    WHERE t.id = ?
    """, (ticket_id,))
    ticket = cursor.fetchone()
    if not ticket:
        conn.close()
        return None

    user_id = ticket["user_id"]

    # Автоматически определяем 100% стоимости заказа
    if amount_rub is None or amount_rub <= 0:
        if ticket["price_rub"]:
            amount_rub = float(ticket["price_rub"])
        else:
            cursor.execute("SELECT price_rub, order_code FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,))
            last_o = cursor.fetchone()
            amount_rub = float(last_o["price_rub"]) if last_o else 60.0

    new_comp_total = ticket["compensation_rub"] + amount_rub

    # Обновляем баланс пользователя
    cursor.execute("UPDATE users SET balance_rub = balance_rub + ? WHERE id = ?", (amount_rub, user_id))
    cursor.execute("SELECT balance_rub, full_name FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    new_balance = user["balance_rub"]

    # Фиксируем сумму компенсации в тикете
    cursor.execute("""
    UPDATE tickets 
    SET compensation_rub = ?, updated_at = ?
    WHERE id = ?
    """, (new_comp_total, now_str, ticket_id))

    # Если привязан заказ, аннулируем его выдачу в связи со 100% возвратом средств
    if ticket["order_id"]:
        cursor.execute("UPDATE orders SET status = 'Отменен (Возврат)', pickup_code = NULL WHERE id = ?", (ticket["order_id"],))

    order_info = ticket["order_code"] or "заказа"
    # Записываем транзакцию
    cursor.execute("""
    INSERT INTO transactions (user_id, ticket_id, amount_rub, transaction_type, description, created_at)
    VALUES (?, ?, ?, 'Компенсация', ?, ?)
    """, (user_id, ticket_id, amount_rub, f"100% возврат средств за отмену печати ({order_info}, диспетчер {dispatcher_name})", now_str))

    # Добавляем сервисное сообщение в чат
    system_msg = (
        f"💰 Диспетчер {dispatcher_name} оформил 100% возврат средств за печать ({amount_rub:.2f} ₽). "
        f"Средства зачислены на бонусный счет студента. Печать заказа отменена. Актуальный баланс: {new_balance:.2f} руб."
    )
    cursor.execute("""
    INSERT INTO ticket_messages (ticket_id, sender_type, sender_name, message, created_at)
    VALUES (?, 'system', 'Биллинг CloudPrint', ?, ?)
    """, (ticket_id, system_msg, now_str))

    conn.commit()
    conn.close()
    details = get_ticket_details(ticket_id)
    if details:
        details["last_compensation_added"] = amount_rub
        details["compensation_added"] = amount_rub
    return details

def reroute_order_to_campus(ticket_id: int, dispatcher_name: str = "Цырулев А. А."):
    """
    Перевод заказа на 2-й корпус:
    - БАГ №1: Находит активный заказ студента и меняет его terminal_id на противоположный;
    - Генерирует уникальный цифровой 6-значный пин-код формата XXX-XXX;
    - Обновляет заказ и тикет, выводя уведомление с новым кодом и корпусом в чат.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
    SELECT t.id, t.user_id, t.terminal_id, t.order_id, term.code as term_code, term.campus as term_campus
    FROM tickets t
    JOIN terminals term ON t.terminal_id = term.id
    WHERE t.id = ?
    """, (ticket_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    user_id = row["user_id"]
    current_terminal_id = row["terminal_id"]
    order_id = row["order_id"]

    # БАГ №1: Если у тикета не привязан order_id, находим последний заказ студента
    if not order_id:
        cursor.execute("""
        SELECT id, terminal_id FROM orders 
        WHERE user_id = ? 
        ORDER BY id DESC LIMIT 1
        """, (user_id,))
        last_order = cursor.fetchone()
        if last_order:
            order_id = last_order["id"]
            current_terminal_id = last_order["terminal_id"]

    # Находим противоположный (целевой) терминал
    cursor.execute("SELECT id, name, campus, location, code FROM terminals WHERE id != ? LIMIT 1", (current_terminal_id,))
    target_term = cursor.fetchone()
    if not target_term:
        cursor.execute("SELECT id, name, campus, location, code FROM terminals LIMIT 1")
        target_term = cursor.fetchone()

    # Генерация 6-значного уникального пин-кода вида XXX-XXX
    p1 = random.randint(100, 999)
    p2 = random.randint(100, 999)
    pickup_code = f"{p1}-{p2}"

    # БАГ №1: Обновляем terminal_id на противоположный, статус на 'Перенаправлен' и новый пин-код
    if order_id:
        cursor.execute("""
        UPDATE orders 
        SET terminal_id = ?, status = 'Перенаправлен', pickup_code = ?
        WHERE id = ?
        """, (target_term["id"], pickup_code, order_id))

    # Обновляем терминал и order_id в тикете
    cursor.execute("""
    UPDATE tickets 
    SET terminal_id = ?, order_id = ?, updated_at = ?
    WHERE id = ?
    """, (target_term["id"], order_id, now_str, ticket_id))

    # Добавляем сообщение в чат
    dispatch_msg = (
        f"🔄 Заказ успешно перенаправлен на резервный терминал:\n"
        f"📍 Площадка: {target_term['name']} ({target_term['location']})\n"
        f"🔑 ВАШ НОВЫЙ ЦИФРОВОЙ КОД ПОЛУЧЕНИЯ: 【 {pickup_code} 】\n"
        f"ℹ️ Распечатка будет получена на резервном МФУ по новому коду без доплат (срок действия кода — 24 часа). "
        f"Компенсация не начисляется, так как печать будет выполнена в полном объеме."
    )
    cursor.execute("""
    INSERT INTO ticket_messages (ticket_id, sender_type, sender_name, message, created_at)
    VALUES (?, 'dispatcher', ?, ?, ?)
    """, (ticket_id, f"{dispatcher_name} (Диспетчер)", dispatch_msg, now_str))

    cursor.execute("UPDATE tickets SET updated_at = ? WHERE id = ?", (now_str, ticket_id))
    conn.commit()
    conn.close()
    return get_ticket_details(ticket_id)

def call_on_duty_technician(ticket_id: int, dispatcher_name: str = "Цырулев А. А."):
    """
    Вызов дежурного специалиста площадки:
    - Переводит терминал в статус 'Ожидает ТО';
    - Добавляет запись в чат тикета.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("SELECT terminal_id FROM tickets WHERE id = ?", (ticket_id,))
    ticket = cursor.fetchone()
    if not ticket:
        conn.close()
        return None

    terminal_id = ticket["terminal_id"]

    cursor.execute("""
    UPDATE terminals 
    SET status = 'Ожидает ТО', updated_at = ?
    WHERE id = ?
    """, (now_str, terminal_id))

    cursor.execute("SELECT name, location FROM terminals WHERE id = ?", (terminal_id,))
    term_info = cursor.fetchone()

    log_msg = (
        f"🛠️ Диспетчер {dispatcher_name} вызвал дежурного специалиста площадки!\n"
        f"Объект: {term_info['name']} ({term_info['location']}).\n"
        f"Статус терминала переведен в режим «Ожидает ТО». Специалист уже направлен для устранения замятия/проведения регламентных работ."
    )
    cursor.execute("""
    INSERT INTO ticket_messages (ticket_id, sender_type, sender_name, message, created_at)
    VALUES (?, 'system', 'Служба эксплуатации СТАНКИН', ?, ?)
    """, (ticket_id, log_msg, now_str))

    cursor.execute("UPDATE tickets SET updated_at = ? WHERE id = ?", (now_str, ticket_id))
    conn.commit()
    conn.close()
    return get_ticket_details(ticket_id)

def resolve_ticket(ticket_id: int, dispatcher_name: str = "Цырулев А. А."):
    """Закрытие/перевод тикета в статус 'Решен'."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("UPDATE tickets SET status = 'Решен', updated_at = ? WHERE id = ?", (now_str, ticket_id))

    msg = f"✅ Обращение успешно решено и закрыто диспетчером ({dispatcher_name}). Благодарим за обращение в CloudPrint СТАНКИН!"
    cursor.execute("""
    INSERT INTO ticket_messages (ticket_id, sender_type, sender_name, message, created_at)
    VALUES (?, 'system', 'Система CloudPrint', ?, ?)
    """, (ticket_id, msg, now_str))

    conn.commit()
    conn.close()
    return get_ticket_details(ticket_id)

# --- ЖУРНАЛЫ И СТАТИСТИКА ---

def get_orders_list(limit: int = 50):
    """Список последних заказов на печать."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT 
        o.id, o.order_code, o.file_name, o.page_count, o.price_rub, o.status, o.pickup_code, o.is_gost, o.stapling, o.is_color, o.created_at,
        u.full_name as user_name, u.group_code as user_group,
        term.name as terminal_name, term.code as terminal_code
    FROM orders o
    JOIN users u ON o.user_id = u.id
    JOIN terminals term ON o.terminal_id = term.id
    ORDER BY o.id DESC
    LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_transactions_list(limit: int = 50):
    """Список финансовых транзакций."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT 
        t.id, t.amount_rub, t.transaction_type, t.description, t.created_at,
        u.full_name as user_name, u.group_code as user_group
    FROM transactions t
    JOIN users u ON t.user_id = u.id
    ORDER BY t.id DESC
    LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_dashboard_stats():
    """Сводные показатели системы для верхних карточек дашборда."""
    conn = get_db_connection()
    cursor = conn.cursor()

    terminals = get_terminals_list()
    total_terminals = len(terminals)
    online_terminals = sum(1 for t in terminals if t["status"] == "Онлайн")
    error_terminals = sum(1 for t in terminals if t["status"] in ("Замятие E-04", "Ожидает ТО"))

    cursor.execute("SELECT COUNT(*) as count FROM tickets WHERE status != 'Решен'")
    active_tickets = cursor.fetchone()["count"]

    cursor.execute("SELECT SUM(total_printed_pages) as total_pages FROM terminals")
    total_pages = cursor.fetchone()["total_pages"] or 0

    cursor.execute("SELECT SUM(amount_rub) as total_comp FROM transactions WHERE transaction_type = 'Компенсация'")
    total_compensation = cursor.fetchone()["total_comp"] or 0.0

    conn.close()
    return {
        "total_terminals": total_terminals,
        "online_terminals": online_terminals,
        "error_terminals": error_terminals,
        "active_tickets": active_tickets,
        "total_printed_pages": total_pages,
        "total_compensation_rub": round(total_compensation, 2)
    }

# --- КЛИЕНТСКИЙ ФУНКЦИОНАЛ ДЛЯ СТУДЕНТА (MOBILE WEB APP) ---

def get_student_user(user_id: int = 1):
    """Получение профиля студента (по умолчанию Иванов М. В., ИДБ-25-15)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row["id"],
        "full_name": row["full_name"],
        "group_code": row["group_code"],
        "student_card": row["student_card"],
        "balance_rub": round(row["balance_rub"], 2),
        "email": row["email"],
        "created_at": row["created_at"]
    }

def create_client_order(user_id: int = 1, terminal_id: int = 1, file_name: str = "Курсовой_проект_Детали_машин.pdf", page_count: int = 20, price_rub: float = 60.0, payment_method: str = "sbp", is_gost: bool = True, stapling: bool = False, is_color: bool = True):
    """
    Создание и оплата заказа через мобильный интерфейс студента:
    - Выбор режима: оформление по ГОСТ 7.32 (is_gost=True) или стандартная печать (is_gost=False);
    - Опция сшития страниц степлером (+15 ₽): stapling=True;
    - Опция цветности печати: is_color=True (цветная) или False (ч/б);
    - БАГ №2: Запрет создания и запуска печати студентом на неработающем МФУ;
    - Генерирует уникальный цифровой код выдачи (например, 654-321);
    - Выполняет транзакцию (СБП или списание бонусных баллов);
    - Моделирует физическую печать на терминале (списывает листы, скобы и пересчитывает тонер);
    - Возвращает полные данные заказа для экрана выдачи.
    """
    # Проверяем терминал и его статус перед оформлением
    term = get_terminal(terminal_id)
    if not term:
        return {"error": "Терминал не найден"}

    # БАГ №2: Запрет печати на неработающем терминале
    if term["status"] != "Онлайн":
        return {
            "error": f"Терминал «{term['name']}» ({term['campus']}) временно недоступен для печати. Текущий статус: «{term['status']}». Выберите другой корпус для получения распечатки!"
        }
    if term["paper_sheets"] < page_count:
        return {
            "error": f"В лотке терминала недостаточно бумаги ({term['paper_sheets']} л. из {page_count} л.). Выберите другой корпус."
        }
    if term["toner_percent"] <= 0:
        return {
            "error": f"В картридже терминала закончился тонер (0%). Выберите другой корпус."
        }

    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Проверяем пользователя
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return {"error": "Пользователь не найден"}

    # Генерируем уникальный код заказа и 6-значный номер выдачи
    rand_order_code = f"ORD-{random.randint(10000, 99999)}"
    part1 = random.randint(100, 999)
    part2 = random.randint(100, 999)
    pickup_code = f"{part1}-{part2}"

    # Обработка оплаты
    if payment_method == "bonus":
        if user["balance_rub"] < price_rub:
            conn.close()
            return {"error": f"Недостаточно бонусов на балансе. Требуется: {price_rub:.2f} ₽, доступно: {user['balance_rub']:.2f} ₽"}
        cursor.execute("UPDATE users SET balance_rub = balance_rub - ? WHERE id = ?", (price_rub, user_id))
        cursor.execute("""
        INSERT INTO transactions (user_id, ticket_id, amount_rub, transaction_type, description, created_at)
        VALUES (?, NULL, ?, 'Списание', ?, ?)
        """, (user_id, -price_rub, f"Оплата заказа {rand_order_code} бонусами ({page_count} стр.{', со сшитием' if stapling else ''})", now_str))
    else:
        # Оплата через СБП
        cursor.execute("""
        INSERT INTO transactions (user_id, ticket_id, amount_rub, transaction_type, description, created_at)
        VALUES (?, NULL, ?, 'Пополнение', 'Оплата печати через СБП СТАНКИН', ?)
        """, (user_id, price_rub, now_str))
        cursor.execute("""
        INSERT INTO transactions (user_id, ticket_id, amount_rub, transaction_type, description, created_at)
        VALUES (?, NULL, ?, 'Списание', ?, ?)
        """, (user_id, -price_rub, f"Оплата заказа {rand_order_code} ({page_count} стр.{', со сшитием' if stapling else ''})", now_str))

    # Создаем заказ (статус 'Готов к выдаче' для активного получения)
    cursor.execute("""
    INSERT INTO orders (order_code, user_id, terminal_id, file_name, page_count, price_rub, status, pickup_code, is_gost, stapling, is_color, created_at)
    VALUES (?, ?, ?, ?, ?, ?, 'Готов к выдаче', ?, ?, ?, ?, ?)
    """, (rand_order_code, user_id, terminal_id, file_name, page_count, price_rub, pickup_code, 1 if is_gost else 0, 1 if stapling else 0, 1 if is_color else 0, now_str))
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # Физическое списание бумаги, тонера и скобы степлера на выбранном терминале
    sim_res = simulate_print_job(terminal_id, page_count, create_order=False, stapling=stapling)
    if isinstance(sim_res, dict) and "error" in sim_res:
        return sim_res

    term = get_terminal(terminal_id)
    updated_user = get_student_user(user_id)

    return {
        "success": True,
        "order_id": order_id,
        "order_code": rand_order_code,
        "pickup_code": pickup_code,
        "file_name": file_name,
        "page_count": page_count,
        "price_rub": price_rub,
        "payment_method": payment_method,
        "is_gost": bool(is_gost),
        "stapling": bool(stapling),
        "is_color": bool(is_color),
        "terminal_id": terminal_id,
        "terminal_code": term["code"] if term else "STANKIN-01",
        "terminal_name": term["name"] if term else "Терминал СТАНКИН",
        "terminal_campus": term["campus"] if term else "Корпус СТАНКИН",
        "terminal_location": term["location"] if term else "Холл 1 этажа",
        "terminal_status": term["status"] if term else "Онлайн",
        "user_balance": updated_user["balance_rub"],
        "created_at": now_str
    }

def report_student_issue(user_id: int = 1, order_id: int = None, terminal_id: int = None, order_code: str = None, issue_text: str = "Зажевало бумагу! Терминал заблокирован с кодом E-04!"):
    """
    Отправка студентом жалобы на замятие бумаги / сбой печати:
    - БАГ 1: Обязательно привязывает конкретный заказ по order_id (внешний ключ);
    - Переводит терминал выбранного заказа в аварийное состояние 'Замятие E-04';
    - Переводит статус заказа в 'Ошибка печати';
    - Создает тикет в техподдержку с привязкой order_id;
    - Создает сообщение студента в чате с деталями заказа;
    - Возвращает созданный тикет.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Находим выбранный заказ
    order = None
    if order_id:
        cursor.execute("SELECT * FROM orders WHERE id = ? AND user_id = ?", (order_id, user_id))
        order = cursor.fetchone()
    if not order and order_code:
        cursor.execute("SELECT * FROM orders WHERE order_code = ? AND user_id = ?", (order_code, user_id))
        order = cursor.fetchone()
    if not order:
        cursor.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,))
        order = cursor.fetchone()

    if not order:
        conn.close()
        return {"error": "Заказ для подачи обращения не найден"}

    target_order_id = order["id"]
    target_terminal_id = order["terminal_id"]

    # Переводим терминал в статус 'Замятие E-04'
    cursor.execute("UPDATE terminals SET status = 'Замятие E-04', updated_at = ? WHERE id = ?", (now_str, target_terminal_id))

    # Переводим статус заказа в 'Ошибка печати'
    cursor.execute("UPDATE orders SET status = 'Ошибка печати' WHERE id = ?", (target_order_id,))

    # Создаем тикет строго с внешним ключом order_id
    rand_ticket_num = f"TCK-2026-{random.randint(100, 999)}"
    cursor.execute("""
    INSERT INTO tickets (ticket_number, user_id, order_id, terminal_id, issue_type, status, compensation_rub, created_at, updated_at)
    VALUES (?, ?, ?, ?, 'Замятие бумаги (E-04)', 'В работе', 0.0, ?, ?)
    """, (rand_ticket_num, user_id, target_order_id, target_terminal_id, now_str, now_str))
    ticket_id = cursor.lastrowid

    # Имя студента
    cursor.execute("SELECT full_name, group_code FROM users WHERE id = ?", (user_id,))
    user_row = cursor.fetchone()
    sender_name = f"{user_row['full_name']} ({user_row['group_code']})" if user_row else "Студент СТАНКИН"

    # Формируем подробный текст инцидента с указанием конкретного заказа
    formatted_msg = (
        f"Заказ {order['order_code']} ({order['file_name']}, {order['page_count']} стр., стоимость: {order['price_rub']:.2f} ₽): "
        f"{issue_text}"
    )

    cursor.execute("""
    INSERT INTO ticket_messages (ticket_id, sender_type, sender_name, message, created_at)
    VALUES (?, 'student', ?, ?, ?)
    """, (ticket_id, sender_name, formatted_msg, now_str))

    conn.commit()
    conn.close()

    return get_ticket_details(ticket_id)

def get_student_orders_list(user_id: int = 1):
    """
    Возвращает список ВСЕХ заказов студента, отсортированный по дате (сначала новые).
    БАГ 2: Обеспечивает отображение полной истории заказов на вкладке «Мои заказы» 
    и наполнение выпадающего списка выбора заказа в форме техподдержки.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT 
        o.id, o.order_code, o.user_id, o.terminal_id, o.file_name, o.page_count, 
        o.price_rub, o.status as order_status, o.pickup_code, o.is_gost, o.stapling, o.is_color, o.created_at,
        t.code as terminal_code, t.name as terminal_name, t.campus as terminal_campus, 
        t.location as terminal_location, t.status as terminal_status
    FROM orders o
    JOIN terminals t ON o.terminal_id = t.id
    WHERE o.user_id = ?
    ORDER BY o.id DESC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_student_active_ticket(user_id: int = 1):
    """Получение последнего активного тикета студента со всеми сообщениями."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id FROM tickets 
    WHERE user_id = ? 
    ORDER BY id DESC LIMIT 1
    """, (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return get_ticket_details(row["id"])

def student_send_message(ticket_id: int, user_id: int = 1, message: str = ""):
    """Отправка дополнительного сообщения студентом в чат тикета."""
    user = get_student_user(user_id)
    sender_name = f"{user['full_name']} ({user['group_code']})" if user else "Студент СТАНКИН"
    return add_ticket_message(
        ticket_id=ticket_id,
        sender_type="student",
        sender_name=sender_name,
        message=message
    )

def compensate_and_reroute(ticket_id: int, amount_rub: float = None, dispatcher_name: str = "Цырулев А. А."):
    """
    Регламент: при переводе заказа на 2-й корпус компенсация не начисляется,
    так как печать будет выполнена на резервном оборудовании.
    """
    return reroute_order_to_campus(ticket_id=ticket_id, dispatcher_name=dispatcher_name)

def get_student_active_order(user_id: int = 1):
    """
    Возвращает актуальный заказ студента с данными о терминале, корпусе, 
    статусе заказа, пин-коде выдачи и статусе МФУ.
    Используется для авто-обновления экрана выдачи студента при переводе на другой корпус.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT 
        o.id, o.order_code, o.user_id, o.terminal_id, o.file_name, o.page_count, 
        o.price_rub, o.status as order_status, o.pickup_code, o.is_gost, o.stapling, o.is_color, o.created_at,
        t.code as terminal_code, t.name as terminal_name, t.campus as terminal_campus, 
        t.location as terminal_location, t.status as terminal_status, t.paper_sheets, t.paper_max,
        t.toner_printed_pages, t.cartridge_nominal
    FROM orders o
    JOIN terminals t ON o.terminal_id = t.id
    WHERE o.user_id = ?
    ORDER BY o.id DESC LIMIT 1
    """, (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    res = dict(row)
    res["toner_percent"] = calculate_toner_percent(res["toner_printed_pages"], res["cartridge_nominal"])
    return res

def bind_user_telegram_chat(user_id: int, chat_id: int):
    """Привязка Telegram chat_id к профилю студента."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET telegram_chat_id = ? WHERE id = ?", (chat_id, user_id))
    conn.commit()
    conn.close()

def get_user_by_telegram_chat(chat_id: int):
    """Поиск пользователя по telegram chat_id."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE telegram_chat_id = ?", (chat_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_telegram_chat_id_by_ticket(ticket_id: int):
    """Получение telegram chat_id студента, создавшего тикет."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT u.telegram_chat_id 
    FROM tickets t 
    JOIN users u ON t.user_id = u.id 
    WHERE t.id = ?
    """, (ticket_id,))
    row = cursor.fetchone()
    conn.close()
    return row["telegram_chat_id"] if row and row["telegram_chat_id"] else None

def get_telegram_chat_id_by_user(user_id: int):
    """Получение telegram chat_id студента по user_id."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT telegram_chat_id FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row["telegram_chat_id"] if row and row["telegram_chat_id"] else None

# Псевдоним для полной совместимости
compensate_ticket_100 = compensate_student

def get_system_setting(key: str, default: str = "") -> str:
    """Получение настройки системы по ключу."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM system_settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else default

def set_system_setting(key: str, value: str):
    """Сохранение настройки системы."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()



