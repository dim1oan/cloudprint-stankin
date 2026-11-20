"""
Веб-панель администратора и диспетчера техподдержки CloudPrint СТАНКИН.
Локальная система облачной студенческой смарт-полиграфии МГТУ «СТАНКИН».

Разработчики проекта:
- Цырулев А. А. (удаленный диспетчер техподдержки)
- Ткачук Д. В. (технический администратор)
Физическое обслуживание: дежурные специалисты площадок (Старый и Новый корпус).
"""

import os
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
import uvicorn

import database

# Инициализация путей
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
INDEX_HTML_PATH = os.path.join(TEMPLATES_DIR, "index.html")
CLIENT_HTML_PATH = os.path.join(TEMPLATES_DIR, "client.html")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Инициализация базы данных при старте приложения
    database.init_db()
    yield

app = FastAPI(
    title="CloudPrint СТАНКИН — Панель диспетчера и студенческий сервис",
    description="Комплекс диспетчеризации, мониторинга МФУ и мобильного веб-приложения студента",
    version="2.0.0",
    lifespan=lifespan
)

# Шаблоны Jinja2
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# --- МОДЕЛИ ЗАПРОСОВ (PYDANTIC) ---

class MessageRequest(BaseModel):
    message: str = Field(..., description="Текст сообщения")
    sender_name: Optional[str] = Field("Цырулев А. А. (Диспетчер)", description="Имя отправителя")

class CompensateRequest(BaseModel):
    amount_rub: Optional[float] = Field(None, description="Сумма компенсации (если None - берется 100% стоимости привязанного заказа)")
    dispatcher_name: Optional[str] = Field("Цырулев А. А.", description="Имя диспетчера")

class ActionRequest(BaseModel):
    dispatcher_name: Optional[str] = Field("Цырулев А. А.", description="Имя диспетчера")

class CompensateAndRerouteRequest(BaseModel):
    amount_rub: Optional[float] = Field(None, description="Сумма компенсации (если None - берется 100% стоимости заказа)")
    dispatcher_name: Optional[str] = Field("Цырулев А. А.", description="Имя диспетчера")

class SimulatePrintRequest(BaseModel):
    terminal_id: int = Field(..., description="ID терминала")
    pages: Optional[int] = Field(20, gt=0, le=500, description="Количество отпечатанных страниц")

class SimulateJamRequest(BaseModel):
    terminal_id: int = Field(..., description="ID терминала")

# Модели для студенческого интерфейса (Client)
class ClientOrderRequest(BaseModel):
    user_id: Optional[int] = Field(1, description="ID студента")
    terminal_id: int = Field(1, description="ID выбранного терминала")
    file_name: Optional[str] = Field("Курсовой_проект_Детали_машин.pdf", description="Имя файла")
    page_count: Optional[int] = Field(20, gt=0, description="Число страниц")
    price_rub: Optional[float] = Field(60.0, gt=0, description="Стоимость печати")
    payment_method: Optional[str] = Field("sbp", description="Способ оплаты: sbp или bonus")
    is_gost: Optional[bool] = Field(True, description="Оформление по ГОСТ 7.32 (True) или стандартная печать (False)")

class ClientIssueRequest(BaseModel):
    user_id: Optional[int] = Field(1, description="ID студента")
    order_id: int = Field(..., description="ID проблемного заказа (внешний ключ)")
    terminal_id: Optional[int] = Field(None, description="ID терминала")
    order_code: Optional[str] = Field(None, description="Код заказа")
    issue_text: Optional[str] = Field("Зажевало бумагу! Терминал заблокирован с кодом E-04!", description="Текст проблемы")

class ClientMessageRequest(BaseModel):
    ticket_id: int = Field(..., description="ID тикета")
    user_id: Optional[int] = Field(1, description="ID студента")
    message: str = Field(..., description="Текст сообщения студента")

# --- СТРАНИЦЫ (HTML / SPA) ---

@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request):
    """Главная страница: веб-панель администратора и диспетчера техподдержки."""
    if os.path.exists(INDEX_HTML_PATH):
        return FileResponse(INDEX_HTML_PATH, media_type="text/html; charset=utf-8")
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/client", response_class=HTMLResponse)
async def serve_client(request: Request):
    """Студенческий интерфейс: Mobile-First Web App смарт-полиграфии."""
    if os.path.exists(CLIENT_HTML_PATH):
        return FileResponse(CLIENT_HTML_PATH, media_type="text/html; charset=utf-8")
    return templates.TemplateResponse(request=request, name="client.html")

# --- REST API: СТУДЕНЧЕСКИЙ КЛИЕНТ (MOBILE APP) ---

@app.get("/api/client/user")
async def api_client_get_user(user_id: int = 1):
    """Получение профиля авторизованного студента (баланс, билет, группа)."""
    user = database.get_student_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Студент не найден")
    return user

@app.get("/api/client/orders")
async def api_client_orders(user_id: int = 1):
    """
    БАГ 2: Список ВСЕХ заказов студента, отсортированный по дате (сначала новые).
    Используется для вкладки «Мои заказы» и выпадающего списка выбора заказа в поддержке.
    """
    orders = database.get_student_orders_list(user_id)
    return {"orders": orders}

@app.get("/api/client/active-order")
async def api_client_active_order(user_id: int = 1):
    """
    Получение активного заказа студента с актуальным терминалом и пин-кодом.
    Используется для обновления статуса и перевода заказа во 2-й корпус на клиенте.
    """
    order = database.get_student_active_order(user_id)
    return {"order": order}

@app.post("/api/client/order")
async def api_client_create_order(req: ClientOrderRequest):
    """
    Создание и оплата заказа студентом:
    - Проверка доступности терминала (БАГ №2: запрет печати на сломанном МФУ);
    - Проверка оплаты (СБП или бонусные баллы);
    - Генерация уникального цифрового номера выдачи (например, 654-321);
    - Списание бумаги и тонера на выбранном терминале в реальном времени.
    """
    res = database.create_client_order(
        user_id=req.user_id,
        terminal_id=req.terminal_id,
        file_name=req.file_name,
        page_count=req.page_count,
        price_rub=req.price_rub,
        payment_method=req.payment_method,
        is_gost=req.is_gost if req.is_gost is not None else True
    )
    if not res:
        raise HTTPException(status_code=400, detail="Ошибка при создании заказа")
    if isinstance(res, dict) and "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res

@app.post("/api/client/report-issue")
async def api_client_report_issue(req: ClientIssueRequest):
    """
    Студент отправляет сигнал о замятии бумаги (E-04) по конкретному заказу:
    - БАГ 1: Обязательно связывает тикет с внешним ключом order_id;
    - Немедленно переводит МФУ в статус 'Замятие E-04';
    - Переводит заказ в статус 'Ошибка печати';
    - Создает тикет в техподдержку от имени студента;
    - Уведомляет удаленного диспетчера Цырулева А. А.
    """
    ticket = database.report_student_issue(
        user_id=req.user_id,
        order_id=req.order_id,
        terminal_id=req.terminal_id,
        order_code=req.order_code,
        issue_text=req.issue_text
    )
    if not ticket or (isinstance(ticket, dict) and "error" in ticket):
        error_msg = ticket.get("error", "Не удалось зарегистрировать обращение") if isinstance(ticket, dict) else "Не удалось зарегистрировать обращение"
        raise HTTPException(status_code=400, detail=error_msg)
    return {"success": True, "ticket": ticket}

@app.get("/api/client/my-ticket")
async def api_client_my_ticket(user_id: int = 1):
    """Получение активного обращения студента и всей истории переписки."""
    ticket = database.get_student_active_ticket(user_id)
    return {"ticket": ticket}

@app.post("/api/client/send-message")
async def api_client_send_message(req: ClientMessageRequest):
    """Отправка сообщения студентом в чат техподдержки."""
    ticket = database.student_send_message(
        ticket_id=req.ticket_id,
        user_id=req.user_id,
        message=req.message
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Тикет не найден")
    return {"success": True, "ticket": ticket}

# --- REST API: СТАТИСТИКА И ДАШБОРД ---

@app.get("/api/stats")
async def api_get_stats():
    """Сводные метрики для информеров в шапке дашборда."""
    return database.get_dashboard_stats()

# --- REST API: ТЕРМИНАЛЫ ---

@app.get("/api/terminals")
async def api_get_terminals():
    """Список всех терминалов с динамически рассчитанными показателями тонера и бумаги."""
    return database.get_terminals_list()

@app.get("/api/terminals/{terminal_id}")
async def api_get_terminal(terminal_id: int):
    """Информация по конкретному терминалу."""
    term = database.get_terminal(terminal_id)
    if not term:
        raise HTTPException(status_code=404, detail="Терминал не найден")
    return term

@app.post("/api/terminals/{terminal_id}/refill-paper")
async def api_refill_paper(terminal_id: int):
    """Заправка бумаги (+500 листов) дежурным специалистом."""
    term = database.refill_paper(terminal_id)
    if not term:
        raise HTTPException(status_code=404, detail="Терминал не найден")
    return {"success": True, "message": f"Бумага заправлена в {term['name']}", "terminal": term}

@app.post("/api/terminals/{terminal_id}/replace-cartridge")
async def api_replace_cartridge(terminal_id: int):
    """Замена тонер-картриджа TK-1150 и сброс счетчика тонера дежурным специалистом."""
    term = database.replace_cartridge(terminal_id)
    if not term:
        raise HTTPException(status_code=404, detail="Терминал не найден")
    return {"success": True, "message": f"Тонер-картридж заменен в {term['name']}", "terminal": term}

@app.post("/api/terminals/{terminal_id}/clear-jam")
async def api_clear_jam(terminal_id: int):
    """Устранение замятия бумаги дежурным специалистом (сброс ошибки E-04)."""
    term = database.clear_jam(terminal_id)
    if not term:
        raise HTTPException(status_code=404, detail="Терминал не найден")
    return {"success": True, "message": f"Замятие устранено в {term['name']}", "terminal": term}

# --- REST API: ТИКЕТЫ И ЧАТ ТЕХПОДДЕРЖКИ ---

@app.get("/api/tickets")
async def api_get_tickets(status: Optional[str] = None):
    """Список обращений в техподдержку с фильтрацией по статусу."""
    return database.get_tickets_list(status_filter=status)

@app.get("/api/tickets/{ticket_id}")
async def api_get_ticket(ticket_id: int):
    """Полная карточка тикета со всей историей переписки."""
    ticket = database.get_ticket_details(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Тикет не найден")
    return ticket

@app.post("/api/tickets/{ticket_id}/message")
async def api_add_message(ticket_id: int, req: MessageRequest):
    """Отправка ответа диспетчером в чат тикета."""
    ticket = database.add_ticket_message(
        ticket_id=ticket_id,
        sender_type="dispatcher",
        sender_name=req.sender_name,
        message=req.message
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Тикет не найден")
    return {"success": True, "ticket": ticket}

@app.post("/api/tickets/{ticket_id}/compensate")
async def api_compensate(ticket_id: int, req: CompensateRequest):
    """
    БАГ 1: Начисление 100% компенсации стоимости привязанного заказа студенту.
    Бэкенд автоматически определяет стоимость заказа и начисляет точную сумму без ручного ввода.
    """
    ticket = database.compensate_student(
        ticket_id=ticket_id,
        amount_rub=req.amount_rub,
        dispatcher_name=req.dispatcher_name
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Тикет не найден")
    comp_added = ticket.get("last_compensation_added", req.amount_rub or ticket.get("price_rub") or ticket["compensation_rub"])
    return {
        "success": True, 
        "message": f"100% компенсация ({comp_added:.2f} ₽) успешно начислена на баланс студента", 
        "compensation_added": comp_added,
        "ticket": ticket
    }

@app.post("/api/tickets/{ticket_id}/reroute")
async def api_reroute(ticket_id: int, req: ActionRequest):
    """Перенаправление заказа на терминал 2-го корпуса с генерацией цифрового пин-кода."""
    ticket = database.reroute_order_to_campus(
        ticket_id=ticket_id,
        dispatcher_name=req.dispatcher_name
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Тикет не найден")
    return {"success": True, "message": "Заказ переведен на резервный терминал", "ticket": ticket}

@app.post("/api/tickets/{ticket_id}/compensate-and-reroute")
async def api_compensate_and_reroute(ticket_id: int, req: CompensateAndRerouteRequest):
    """
    Регламент: при переводе на 2-й корпус компенсация не начисляется,
    так как заказ будет распечатан на резервном оборудовании по новому коду.
    """
    ticket = database.reroute_order_to_campus(
        ticket_id=ticket_id,
        dispatcher_name=req.dispatcher_name
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Тикет не найден")
    return {
        "success": True,
        "message": "Заказ переведен на 2-й корпус (компенсация не начисляется, так как печать состоится)",
        "ticket": ticket
    }

@app.post("/api/tickets/{ticket_id}/call-technician")
async def api_call_technician(ticket_id: int, req: ActionRequest):
    """Вызов дежурного специалиста площадки (перевод МФУ в режим 'Ожидает ТО')."""
    ticket = database.call_on_duty_technician(
        ticket_id=ticket_id,
        dispatcher_name=req.dispatcher_name
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Тикет не найден")
    return {"success": True, "message": "Дежурный специалист вызван к терминалу", "ticket": ticket}

@app.post("/api/tickets/{ticket_id}/resolve")
async def api_resolve_ticket(ticket_id: int, req: ActionRequest):
    """Закрытие обращения и перевод в статус 'Решен'."""
    ticket = database.resolve_ticket(
        ticket_id=ticket_id,
        dispatcher_name=req.dispatcher_name
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Тикет не найден")
    return {"success": True, "message": "Тикет успешно закрыт", "ticket": ticket}

# --- REST API: ПАНЕЛЬ СИМУЛЯЦИИ (DEMO MODE) ---

@app.post("/api/simulate/print")
async def api_simulate_print(req: SimulatePrintRequest):
    """
    Симуляция печати (по умолчанию 20 стр.):
    - Проверяет статус терминала (БАГ №2: отклоняет печать, если МФУ заблокировано);
    - Прибавляет 20 стр к счетчикам;
    - Вычитает 20 листов бумаги;
    - Динамически пересчитывает тонер;
    - Фиксирует выполненный заказ.
    """
    term = database.simulate_print_job(terminal_id=req.terminal_id, pages=req.pages)
    if not term:
        raise HTTPException(status_code=404, detail="Терминал не найден")
    if isinstance(term, dict) and "error" in term:
        raise HTTPException(status_code=400, detail=term["error"])
    return {
        "success": True,
        "message": f"Симуляция печати: отпечатано {req.pages} стр. на {term['name']}",
        "terminal": term
    }

@app.post("/api/simulate/jam")
async def api_simulate_jam(req: SimulateJamRequest):
    """
    Симуляция замятия бумаги (E-04):
    - Блокирует терминал со статусом 'Замятие E-04';
    - Создает аварийный заказ;
    - Создает новый тикет в техподдержку от студента.
    """
    result = database.simulate_jam_event(terminal_id=req.terminal_id)
    if not result:
        raise HTTPException(status_code=404, detail="Терминал не найден")
    return {
        "success": True,
        "message": f"Смоделирована аппаратная авария E-04 на терминале {result['terminal']['code']}. Создан тикет {result['ticket_number']}!",
        "result": result
    }

# --- REST API: ЖУРНАЛЫ И СБРОС ---

@app.get("/api/orders")
async def api_get_orders():
    """История всех заказов на печать."""
    return database.get_orders_list(limit=50)

@app.get("/api/transactions")
async def api_get_transactions():
    """Аудиторский лог финансовых операций."""
    return database.get_transactions_list(limit=50)

@app.post("/api/reset-demo")
async def api_reset_demo():
    """Сброс всей базы данных к эталонному демонстрационному состоянию для защиты."""
    database.init_db(force_reseed=True)
    return {"success": True, "message": "База данных успешно сброшена к эталонным демо-данным!"}

# --- ТОЧКА ВХОДА ДЛЯ ЗАПУСКА ОДНОЙ КОМАНДОЙ ---

if __name__ == "__main__":
    print("=" * 75)
    print("  🚀 Запуск CloudPrint СТАНКИН v2.0")
    print("  👨‍💼 Диспетчер техподдержки: Цырулев А. А.")
    print("  🛠️ Технический администратор: Ткачук Д. В.")
    print("  🖥️ Панель администратора: http://127.0.0.1:8000")
    print("  📱 Клиентский интерфейс студента: http://127.0.0.1:8000/client")
    print("=" * 75)
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 8000))
    print(f"  🌐 Сервер слушает на http://{host}:{port}")
    uvicorn.run("app:app", host=host, port=port, reload=False)
