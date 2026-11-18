"""Дымовой тест: сквозной сценарий клиента, кабинет и рабочее место оператора."""

import os
import sys
from datetime import date

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.test import Client  # noqa: E402

from apps.booking.models import Order, Slot  # noqa: E402
from apps.catalog.models import Service  # noqa: E402

RESULTS = []


def check(label, response, expect=200):
    ok = response.status_code == expect
    RESULTS.append(ok)
    print(f"{'OK  ' if ok else 'FAIL'} {label}: {response.status_code}")
    return ok


def cleanup(order):
    order.payments.all().delete()
    order.notifications.all().delete()
    order.items.all().delete()
    if hasattr(order, "review"):
        order.review.delete()
    slot = order.slot
    order.delete()
    slot.status = Slot.Status.FREE
    slot.save(update_fields=["status"])


def main():
    client = Client()
    ok = True

    ok &= check("GET /", client.get("/"))
    service = Service.objects.first()
    ok &= check(f"GET /service/{service.pk}/", client.get(f"/service/{service.pk}/"))
    ok &= check("GET /accounts/register/", client.get("/accounts/register/"))
    ok &= check("GET /accounts/login/", client.get("/accounts/login/"))

    slot = Slot.objects.filter(status=Slot.Status.FREE, date__gte=date.today()).first()
    created = client.post("/order/create/", {
        "service_id": service.pk,
        "slot_id": slot.pk,
        "last_name": "Тестов",
        "first_name": "Тест",
        "phone": "+79160000001",
        "email": "test@example.com",
        "address": "ул. Тестовая, 1",
        "consent": "on",
        "distance_km": "12",
    })
    ok &= check("POST /order/create/ (гость)", created, 302)
    order_id = int(created["Location"].rstrip("/").split("/")[-1])

    ok &= check(f"GET /checkout/{order_id}/", client.get(f"/checkout/{order_id}/"))
    rejected = client.post(f"/checkout/{order_id}/pay/",
                           {"method": "card", "card_number": "4111 1111 1111 0000"})
    ok &= check("POST pay (отказ банка)", rejected, 302)
    paid = client.post(f"/checkout/{order_id}/pay/",
                       {"method": "card", "card_number": "4111 1111 1111 1111"})
    ok &= check("POST pay (успех)", paid, 302)

    order = Order.objects.get(pk=order_id)
    print("     статус заказа:", order.status, "| сумма:", order.total_sum)
    ok &= order.status == Order.Status.CONFIRMED
    ok &= check(f"GET /order/{order_id}/", client.get(f"/order/{order_id}/"))
    ok &= check("GET /api/v1/slots/", client.get("/api/v1/slots/"))

    ok &= check("POST login (оператор)", client.post("/accounts/login/",
                                                     {"username": "operator",
                                                      "password": "operator123"}), 302)
    for url in ("/operator/", "/operator/orders/", f"/operator/orders/{order_id}/",
                "/operator/claim/", "/operator/slots/", "/operator/report/",
                "/operator/tariffs/", "/operator/executors/1/"):
        ok &= check(f"GET {url}", client.get(url))

    ok &= check("POST close order",
                client.post(f"/operator/orders/{order_id}/action/close/"), 302)
    order.refresh_from_db()
    ok &= order.status == Order.Status.DONE
    print("     статус после закрытия:", order.status)

    client.post("/accounts/logout/")
    ok &= check("POST login (клиент)", client.post("/accounts/login/",
                                                   {"username": "+79001112233",
                                                    "password": "client123"}), 302)
    ok &= check("GET /account/", client.get("/account/"))
    ok &= check("GET /account/notifications/", client.get("/account/notifications/"))

    ok &= check("POST регистрация нового клиента", client.post("/accounts/register/", {
        "phone": "+7 916 000-00-77",
        "last_name": "Новиков",
        "first_name": "Пётр",
        "email": "novikov@example.com",
        "address": "ул. Новая, 7",
        "password1": "demo12345",
        "password2": "demo12345",
        "consent": "on",
    }), 302)
    ok &= check("GET /account/ (новый клиент)", client.get("/account/"))

    cleanup(order)

    from django.contrib.auth import get_user_model
    from apps.booking.models import Client as ClientModel

    get_user_model().objects.filter(username="+79160000077").delete()
    ClientModel.objects.filter(phone="+79160000077").delete()

    print("\nИТОГ:", "все проверки пройдены" if all(RESULTS) else "есть ошибки")
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback

        with open("smoke_err.txt", "w", encoding="utf-8") as handle:
            handle.write(traceback.format_exc())
        raise
