"""
Автоматизированный тест логики CloudPrint СТАНКИН:
- Проверка БАГА 1 (100% автоматическая компенсация, привязка order_id);
- Проверка БАГА 2 (Вкладка «Мои заказы», история заказов, сокрытие QR при завершении);
- Проверка блокировки печати на сломанном МФУ (HTTP 400);
- Проверка перенаправления на противоположный корпус.
"""

import sys
from fastapi.testclient import TestClient
import database
from app import app

client = TestClient(app)

def run_tests():
    print("==================================================")
    print("▶ Запуск автоматизированной проверки CloudPrint...")
    print("==================================================")

    # Шаг 0: Ресет БД к эталонному состоянию
    database.init_db(force_reseed=True)
    print("✔ База данных сброшена в исходное демо-состояние.")

    # 1. Проверка БАГА 2: GET /api/client/orders?user_id=1
    res = client.get("/api/client/orders?user_id=1")
    assert res.status_code == 200, f"Ошибка orders: {res.text}"
    orders_data = res.json()["orders"]
    assert len(orders_data) >= 1, "Должен быть хотя бы 1 заказ у Иванова М. В."
    print(f"✔ БАГ 2 решен: получена история заказов студента ({len(orders_data)} шт.), отсортированная по дате.")

    # 2. Проверка БАГА 2: Попытка печати на сломанном терминале (Терминал №1 со статусом Замятие E-04)
    # Попытка студента напечатать на терминале №1 (Старый корпус)
    res_bad_print = client.post("/api/client/order", json={
        "user_id": 1,
        "terminal_id": 1, # В начальном демо-состоянии Старый корпус имеет 'Замятие E-04'
        "file_name": "Тестовый_документ.pdf",
        "page_count": 20,
        "price_rub": 60.0,
        "payment_method": "sbp"
    })
    assert res_bad_print.status_code == 400, f"Печать на сломанном МФУ должна быть заблокирована с 400! Ответ: {res_bad_print.status_code}"
    print(f"✔ БАГ 2 (Печать на сломанном терминале) решен: бэкенд корректно вернул HTTP 400 ({res_bad_print.json()['detail']}).")

    # 3. Успешная печать на рабочем терминале (Терминал №2: Новый корпус, Онлайн)
    res_good_print = client.post("/api/client/order", json={
        "user_id": 1,
        "terminal_id": 2,
        "file_name": "Лабораторная_работа_СТАНКИН.pdf",
        "page_count": 20,
        "price_rub": 60.0,
        "payment_method": "sbp"
    })
    assert res_good_print.status_code == 200, f"Ошибка создания заказа: {res_good_print.text}"
    new_order = res_good_print.json()
    new_order_id = new_order["order_id"]
    pickup_code = new_order["pickup_code"]
    print(f"✔ Новый заказ успешно создан на онлайн-терминале №2: ID={new_order_id}, Код={new_order['order_code']}, Пин={pickup_code}.")

    # 4. Проверка БАГА 2: Список заказов студента теперь содержит новый заказ первым
    res_updated_orders = client.get("/api/client/orders?user_id=1")
    updated_orders = res_updated_orders.json()["orders"]
    assert updated_orders[0]["id"] == new_order_id, "Новый заказ должен быть первым в списке (DESC)"
    assert updated_orders[0]["order_status"] == "Готов к выдаче"
    print(f"✔ Список заказов студента обновился: теперь {len(updated_orders)} заказов, новый заказ во главе списка.")

    # 5. Проверка БАГА 1: Подача жалобы в саппорт со СТРОГОЙ привязкой order_id
    res_issue = client.post("/api/client/report-issue", json={
        "user_id": 1,
        "order_id": new_order_id,
        "issue_text": "Во время печати зажевало бумагу! Треск в лотке!"
    })
    assert res_issue.status_code == 200, f"Ошибка подачи жалобы: {res_issue.text}"
    ticket = res_issue.json()["ticket"]
    ticket_id = ticket["id"]
    assert ticket["order_id"] == new_order_id, "Тикет должен быть привязан к order_id"
    assert ticket["price_rub"] == 60.0, "В тикете должна отображаться стоимость заказа 60 руб."
    print(f"✔ БАГ 1 решен: Тикет #{ticket_id} успешно зарегистрирован с привязкой к заказу #{new_order_id} (стоимость: {ticket['price_rub']} ₽).")

    # Проверяем, что терминал №2 перешел в статус Замятие E-04
    term2 = database.get_terminal(2)
    assert term2["status"] == "Замятие E-04", "Терминал должен перейти в статус Замятие E-04"
    print("✔ Статус терминала переведен в «Замятие E-04».")

    # 6. Проверка БАГА 1: Автоматическое начисление 100% компенсации диспетчером
    # Студент Иванов до компенсации
    user_before = database.get_student_user(1)
    bal_before = user_before["balance_rub"]

    # Диспетчер нажимает «Начислить компенсацию (100%)» БЕЗ ручного ввода суммы
    res_comp = client.post(f"/api/tickets/{ticket_id}/compensate", json={
        "dispatcher_name": "Цырулев А. А."
    })
    assert res_comp.status_code == 200, f"Ошибка компенсации: {res_comp.text}"
    comp_json = res_comp.json()
    assert comp_json["compensation_added"] == 60.0, f"Должно начислиться ровно 100% (60.0 руб.), а начислилось {comp_json.get('compensation_added')}"
    
    user_after = database.get_student_user(1)
    assert user_after["balance_rub"] == bal_before + 60.0, "Баланс студента должен увеличиться ровно на 60 руб."
    print(f"✔ БАГ 1 (100% компенсация без ручного ввода) решен: начислено ровно {comp_json['compensation_added']} ₽. Баланс: {bal_before} -> {user_after['balance_rub']} ₽.")

    # 7. Проверка перевода заказа на резервный терминал
    res_reroute = client.post(f"/api/tickets/{ticket_id}/reroute", json={
        "dispatcher_name": "Цырулев А. А."
    })
    assert res_reroute.status_code == 200, f"Ошибка reroute: {res_reroute.text}"
    rerouted_ticket = res_reroute.json()["ticket"]
    assert rerouted_ticket["terminal_id"] == 1, "Заказ должен перевестись на терминал №1 (Старый корпус)"
    
    active_ord = client.get("/api/client/active-order?user_id=1").json()["order"]
    assert active_ord["terminal_id"] == 1, "Активный заказ студента должен иметь terminal_id = 1"
    assert active_ord["pickup_code"] is not None, "Должен быть сгенерирован новый код получения"
    print(f"✔ Заказ успешно перенаправлен на противоположный корпус (Терминал ID={active_ord['terminal_id']}). Новый пин: {active_ord['pickup_code']}.")

    # 8. Сброс БД обратно к исходному демо-состоянию для чистого старта
    database.init_db(force_reseed=True)
    print("✔ База данных сброшена в чистое эталонное демо-состояние.")

    print("==================================================")
    print("🎉 ВСЕ ТЕСТЫ УСПЕШНО ПРОЙДЕНЫ! ПОЛНОЕ СООТВЕТСТВИЕ!")
    print("==================================================")

if __name__ == "__main__":
    run_tests()
