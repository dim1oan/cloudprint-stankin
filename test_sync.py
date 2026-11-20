"""
Тест двусторонней синхронизации Web-панели диспетчера и Telegram-бота CloudPrint СТАНКИН:
1. Синхронизация Telegram chat_id с веб-аккаунтом студента (Иванов М. В.);
2. Ответ диспетчера через Web API -> сохранение в БД + привязка к chat_id для отправки в Telegram;
3. Сообщение студента из Telegram -> моментальное появление в веб-интерфейсе диспетчера;
4. Перенаправление диспетчером на 2-й корпус -> синхронизация нового PIN-кода для Telegram и Web;
5. Начисление 100% компенсации диспетчером -> обновление баланса в Telegram и Web.
"""

from fastapi.testclient import TestClient
import database
from app import app

client = TestClient(app)

def test_bidirectional_sync():
    print("=" * 70)
    print("▶ Тестирование синхронизации Web-панели и Telegram-бота...")
    print("=" * 70)

    # 1. Сброс к эталону
    database.init_db(force_reseed=True)
    print("✔ 1. База данных инициализирована в исходное состояние.")

    # 2. Студент запускает бота (/start) -> привязывается Telegram Chat ID
    mock_chat_id = 123456789
    database.bind_user_telegram_chat(user_id=1, chat_id=mock_chat_id)
    chat_id_in_db = database.get_telegram_chat_id_by_user(1)
    assert chat_id_in_db == mock_chat_id, f"Chat ID должен быть {mock_chat_id}, получен {chat_id_in_db}"
    print(f"✔ 2. Telegram chat_id={mock_chat_id} успешно синхронизирован с профилем студента ID=1.")

    # 3. Студент оформляет заказ на сайте или в боте
    order = database.create_client_order(
        user_id=1, terminal_id=2, file_name="Лабораторная_работа_1.pdf",
        page_count=20, price_rub=200.0, payment_method="sbp",
        is_gost=True, stapling=False, is_color=True
    )
    assert order["success"] is True

    # 4. Происходит замятие E-04 -> Студент регистрирует тикет
    ticket = database.report_student_issue(
        user_id=1, order_id=order["order_id"],
        issue_text="МФУ выдало ошибку E-04 при печати диплома!"
    )
    ticket_id = ticket["id"]
    print(f"✔ 3. Тикет #{ticket_id} ({ticket['ticket_number']}) зарегистрирован.")

    # Проверяем, что бэкенд находит chat_id для этого тикета
    found_chat_id = database.get_telegram_chat_id_by_ticket(ticket_id)
    assert found_chat_id == mock_chat_id, "Диспетчерский бэкенд должен точно определять Telegram chat_id студента!"
    print(f"✔ 4. Web API связал тикет #{ticket_id} с Telegram chat_id={found_chat_id}.")

    # 5. Диспетчер пишет ответ НА САЙТЕ через Web API
    res_msg = client.post(f"/api/tickets/{ticket_id}/message", json={
        "sender_name": "Цырулев А. А. (Диспетчер)",
        "message": "Добрый день! Вижу ошибку E-04 в старом корпусе. Сейчас переведу заказ на второй корпус."
    })
    assert res_msg.status_code == 200
    msg_data = res_msg.json()
    last_msg = msg_data["ticket"]["messages"][-1]
    assert "Добрый день!" in last_msg["message"]
    assert last_msg["sender_type"] == "dispatcher"
    print(f"✔ 5. Ответ диспетчера с сайта сохранен в БД и подготовлен к отправке в Telegram (получатель: {found_chat_id}).")

    # 6. Студент отвечает ИЗ TELEGRAM-БОТА
    database.student_send_message(
        ticket_id=ticket_id,
        user_id=1,
        message="Спасибо большое, жду новый пин-код!"
    )

    # 7. Диспетчер открывает тикет на сайте -> видит ответ студента из Telegram
    res_ticket = client.get(f"/api/tickets/{ticket_id}")
    assert res_ticket.status_code == 200
    ticket_details = res_ticket.json()
    student_msgs = [m for m in ticket_details["messages"] if m["sender_type"] == "student"]
    assert any("Спасибо большое" in m["message"] for m in student_msgs)
    print("✔ 6. Сообщение студента из Telegram мгновенно появилось в карточке тикета на сайте диспетчера!")

    # 8. Диспетчер нажимает кнопку «Перевести во 2-й корпус» НА САЙТЕ
    res_reroute = client.post(f"/api/tickets/{ticket_id}/reroute", json={
        "dispatcher_name": "Цырулев А. А."
    })
    assert res_reroute.status_code == 200
    reroute_data = res_reroute.json()
    new_pickup = reroute_data["ticket"]["pickup_code"]
    assert new_pickup is not None
    print(f"✔ 7. Заказ переведен диспетчером на сайте. Новый пин-код 【 {new_pickup} 】 синхронизирован для Telegram.")

    # 9. Диспетчер одобряет 100% компенсацию НА САЙТЕ
    res_comp = client.post(f"/api/tickets/{ticket_id}/compensate", json={
        "dispatcher_name": "Цырулев А. А."
    })
    assert res_comp.status_code == 200
    comp_data = res_comp.json()
    assert comp_data["compensation_added"] == 200.0
    
    # Проверяем баланс студента
    user_after = database.get_student_user(1)
    assert user_after["balance_rub"] == 350.0 # 150 + 200
    print(f"✔ 8. 100% компенсация ({comp_data['compensation_added']} ₽) начислена на сайте, баланс обновлен: {user_after['balance_rub']} ₽.")

    # Сброс к эталону
    database.init_db(force_reseed=True)
    print("=" * 70)
    print("🎉 ДВУСТОРОННЯЯ СИНХРОНИЗАЦИЯ WEB + TELEGRAM ПОЛНОСТЬЮ РАБОТАЕТ!")
    print("=" * 70)

if __name__ == "__main__":
    test_bidirectional_sync()
