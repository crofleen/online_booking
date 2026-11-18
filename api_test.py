"""Проверка REST API (Django REST framework)."""

import json
import os
import sys
from datetime import date

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.test import Client  # noqa: E402

from apps.booking.models import Order, Slot  # noqa: E402
from apps.catalog.models import Service  # noqa: E402


def main():
    client = Client()
    service = Service.objects.first()
    slots = Slot.objects.filter(status=Slot.Status.FREE, date__gte=date.today())
    slot = slots.first()

    listing = client.get("/api/v1/slots/")
    print("GET /api/v1/slots/:", listing.status_code, "слотов:", len(listing.json()))
    assert listing.status_code == 200 and listing.json()

    payload = {
        "slot_id": slot.pk,
        "items": [{"service_id": service.pk, "qty": 1}],
        "last_name": "Апи",
        "first_name": "Тест",
        "phone": "+79160000002",
        "address": "ул. Программная, 1",
        "urgent": True,
        "distance_km": 12,
    }
    created = client.post("/api/v1/orders/", data=json.dumps(payload),
                          content_type="application/json")
    print("POST /api/v1/orders/:", created.status_code, created.json())
    assert created.status_code == 201
    order_id = created.json()["order_id"]

    confirmed = client.post(f"/api/v1/orders/{order_id}/confirm/",
                            data=json.dumps({"transaction_id": "PAY-API-0001"}),
                            content_type="application/json")
    print("POST confirm:", confirmed.status_code, confirmed.json())
    assert confirmed.status_code == 200

    order = Order.objects.get(pk=order_id)
    print("     статус:", order.status, "| сумма:", order.total_sum)
    assert order.status == Order.Status.CONFIRMED

    cancelled = client.post(f"/api/v1/orders/{order_id}/cancel/",
                            data=json.dumps({"reason": "тест"}),
                            content_type="application/json")
    print("POST cancel:", cancelled.status_code, cancelled.json())

    order.payments.all().delete()
    order.notifications.all().delete()
    order.items.all().delete()
    slot = order.slot
    order.delete()
    slot.status = Slot.Status.FREE
    slot.save(update_fields=["status"])
    print("\nAPI: все проверки пройдены")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback

        with open("api_err.txt", "w", encoding="utf-8") as handle:
            handle.write(traceback.format_exc())
        raise
