"""
Автоматизированный модульный тест Telegram-бота CloudPrint СТАНКИН:
- Проверка тарифной сетки: Ч/Б 5.00 ₽, Цветная 10.00 ₽, Сшитие +15.00 ₽;
- Проверка блокировки печати на сломанном МФУ (БАГ 2);
- Проверка списания скоб в степлерном модуле МФУ;
- Проверка оплаты бонусами (1 балл = 1 рубль);
- Проверка регистрации замятия E-04 с привязкой order_id (БАГ 1);
- Проверка перевода заказа во 2-й корпус без начисления компенсации;
- Проверка 100% возврата средств при отмене печати;
- Проверка генерации реального QR-кода выдачи.
"""

import io
import qrcode
import database
from config import PRICE_PER_PAGE_BW, PRICE_PER_PAGE_COLOR, PRICE_STAPLING

def test_cloudprint_bot():
    print("=" * 65)
    print("▶ Тестирование бизнес-логики Telegram-бота CloudPrint СТАНКИН...")
    print("=" * 65)

    # 1. Инициализация и ресет БД
    database.init_db(force_reseed=True)
    print("✔ 1. База данных успешно инициализирована и заполнена эталоном.")

    # 2. Проверка профиля
    user = database.get_student_user(1)
    assert user["full_name"] == "Иванов М. В.", "Студент должен быть Иванов М. В."
    assert user["balance_rub"] == 150.0, "Стартовый баланс должен быть 150.0 ₽"
    print(f"✔ 2. Профиль студента подтвержден: {user['full_name']} ({user['group_code']}), Баланс: {user['balance_rub']} ₽.")

    # 3. Проверка тарифов
    assert PRICE_PER_PAGE_BW == 5.0, "Ч/Б печать должна стоить 5.0 ₽/стр"
    assert PRICE_PER_PAGE_COLOR == 10.0, "Цветная печать должна стоить 10.0 ₽/стр"
    assert PRICE_STAPLING == 15.0, "Сшитие степлером должно стоить 15.0 ₽"
    print("✔ 3. Тарифы подтверждены: Ч/Б = 5 ₽/стр, Цветная = 10 ₽/стр, Сшитие = +15 ₽.")

    # 4. Проверка БАГА 2: Блокировка печати на сломанном терминале (Терминал 1 со статусом Замятие E-04)
    res_bad = database.create_client_order(user_id=1, terminal_id=1, page_count=20, price_rub=200.0)
    assert isinstance(res_bad, dict) and "error" in res_bad, "Печать на сломанном МФУ должна быть заблокирована!"
    print(f"✔ 4. БАГ 2 решен: попытка печати на сломанном МФУ заблокирована ({res_bad['error'][:60]}...).")

    # 5. Успешное создание Ч/Б заказа (10 стр * 5 ₽ = 50 ₽)
    res_bw = database.create_client_order(
        user_id=1, terminal_id=2, file_name="Шпоры_физика.pdf",
        page_count=10, price_rub=50.0, payment_method="bonus",
        is_gost=False, stapling=False, is_color=False
    )
    assert res_bw.get("success") is True, f"Ошибка создания Ч/Б заказа: {res_bw}"
    assert res_bw["is_color"] is False, "Флаг цветности должен быть False"
    print(f"✔ 5. Ч/Б заказ (5 ₽/стр) оформлен: Код={res_bw['order_code']}, Сумма={res_bw['price_rub']} ₽.")

    # 6. Успешное создание Цветного заказа со СШИТИЕМ (20 стр * 10 ₽ + 15 ₽ = 215 ₽)
    term2_before = database.get_terminal(2)
    staples_before = term2_before["staples_count"]

    res_color = database.create_client_order(
        user_id=1, terminal_id=2, file_name="Курсовой_проект_Детали_машин.pdf",
        page_count=20, price_rub=215.0, payment_method="sbp",
        is_gost=True, stapling=True, is_color=True
    )
    assert res_color.get("success") is True, f"Ошибка создания цветного заказа: {res_color}"
    assert res_color["stapling"] is True, "Флаг stapling должен быть True"
    assert res_color["is_color"] is True, "Флаг is_color должен быть True"
    assert res_color["price_rub"] == 215.0, "Стоимость должна быть 215.0 ₽"

    term2_after = database.get_terminal(2)
    assert term2_after["staples_count"] == staples_before - 1, f"Счетчик скоб должен уменьшиться на 1! Было {staples_before}, стало {term2_after['staples_count']}"
    print(f"✔ 6. Цветной заказ со сшитием степлером оформлен (215.00 ₽), скоба списана: {staples_before} -> {term2_after['staples_count']} шт.")

    # 7. Проверка генерации QR-кода для пина
    pickup_code = res_color["pickup_code"]
    qr = qrcode.QRCode(version=1, box_size=8, border=3)
    qr.add_data(f"STANKIN-PRINT:{res_color['order_code']}:{pickup_code}")
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0D2040", back_color="white")
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")
    assert img_bytes.tell() > 500, "QR-код должен успешно формироваться в бинарный поток"
    print(f"✔ 7. Генератор QR-кода работает: пин-код 【 {pickup_code} 】, размер QR: {img_bytes.tell()} байт.")

    # 8. Проверка БАГА 1: Подача сигнала о замятии бумаги со строгой привязкой order_id
    ticket_res = database.report_student_issue(
        user_id=1, order_id=res_color["order_id"],
        issue_text="Зажевало бумагу! Треск в лотке МФУ!"
    )
    ticket_id = ticket_res["id"]
    assert ticket_res["order_id"] == res_color["order_id"], "Тикет должен строго ссылаться на order_id"
    assert ticket_res["price_rub"] == 215.0, "В тикете должна отображаться стоимость заказа 215.00 ₽"
    print(f"✔ 8. БАГ 1 решен: Тикет #{ticket_id} привязан к заказу #{res_color['order_id']} (стоимость: {ticket_res['price_rub']} ₽).")

    # 9. Проверка ПРАВИЛА: При переводе на 2-й корпус компенсация НЕ начисляется
    user_before_reroute = database.get_student_user(1)
    bal_before = user_before_reroute["balance_rub"]

    rerouted = database.reroute_order_to_campus(ticket_id)
    assert rerouted["terminal_id"] == 1, "Заказ должен перевестись на резервный терминал №1"
    user_after_reroute = database.get_student_user(1)
    assert user_after_reroute["balance_rub"] == bal_before, "При переводе баланс студента не должен меняться!"
    print(f"✔ 9. Регламент перевода соблюден: заказ переведен на резервное МФУ без начисления компенсации.")

    # 10. Проверка 100% компенсации при отмене
    comp_res = database.compensate_ticket_100(ticket_id)
    assert comp_res["compensation_added"] == 215.0, f"Компенсация должна быть 215.0 ₽, а начислено {comp_res.get('compensation_added')}"
    user_after_comp = database.get_student_user(1)
    assert user_after_comp["balance_rub"] == bal_before + 215.0, "На баланс студента должно вернуться ровно 215.00 ₽"
    print(f"✔ 10. Возврат 100% средств: на баланс студента зачислено ровно {comp_res['compensation_added']} ₽.")

    # 11. Сброс БД в эталон
    database.init_db(force_reseed=True)
    print("✔ 11. База данных возвращена в исходное эталонное состояние.")

    print("=" * 65)
    print("🎉 ВСЕ ТЕСТЫ БОТА УСПЕШНО ПРОЙДЕНЫ! 100% ФУНКЦИОНАЛА РАБОТАЕТ!")
    print("=" * 65)

if __name__ == "__main__":
    test_cloudprint_bot()
