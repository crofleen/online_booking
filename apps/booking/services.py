"""Сервисный слой бронирования."""

from django.db import transaction
from django.utils import timezone

from apps.booking.models import Client, Order, OrderItem, Slot
from apps.booking.pricing import PriceCalculator, PricingError
from apps.booking.validators import check_order_status, check_visit_date
from apps.catalog.models import TariffRepository
from apps.notifications.models import send_status_notification
from apps.reports.models import log_action


class SlotNotAvailable(Exception):
    """Слот занят или заблокирован."""


class OrderStateError(Exception):
    """Недопустимое состояние заказа."""


class BookingService:
    """Оформление, подтверждение и закрытие заказа."""

    def __init__(self, pricing=None, notifier=None):
        self.pricing = pricing or PriceCalculator(TariffRepository)
        self.notifier = notifier or send_status_notification

    @transaction.atomic
    def create_order(self, client, slot_id, items, urgent=False, distance_km=0, user=None):
        slot = (Slot.objects.select_for_update()
                .select_related("executor").filter(pk=slot_id).first())
        if slot is None or slot.status != Slot.Status.FREE:
            raise SlotNotAvailable("Выбранное время уже занято")
        if not slot.executor.is_available():
            raise SlotNotAvailable("Исполнитель недоступен")
        busy = Order.objects.filter(
            slot=slot, status__in=(Order.Status.NEW, Order.Status.CONFIRMED, Order.Status.DONE),
        ).exists()
        if busy:
            raise SlotNotAvailable("Выбранное время уже занято")

        try:
            total = self.pricing.calc(items, urgent=urgent, distance_km=distance_km)
        except PricingError as error:
            raise OrderStateError(str(error)) from error

        order = Order.objects.create(
            client=client,
            executor=slot.executor,
            slot=slot,
            total_sum=total,
            status=Order.Status.NEW,
        )
        for item in items:
            OrderItem.objects.create(
                order=order,
                service_id=item["service_id"],
                qty=item["qty"],
                price=item["price"],
            )
        slot.mark_blocked(ttl_minutes=10)
        log_action(f"order:{order.pk}", "create", user)
        return order

    @transaction.atomic
    def confirm_order(self, order_id, transaction_id=None, user=None):
        order = Order.objects.select_for_update().get(pk=order_id)
        if order.status != Order.Status.NEW:
            raise OrderStateError("Заказ уже обработан")
        order.confirm()
        order.slot.status = Slot.Status.BUSY
        order.slot.blocked_until = None
        order.slot.save(update_fields=["status", "blocked_until", "updated_at"])
        self.notifier(order, "confirmed")
        log_action(f"order:{order.pk}", f"confirm:{transaction_id or '-'}", user)
        return order

    @transaction.atomic
    def close_order(self, order_id, user=None):
        order = Order.objects.select_for_update().get(pk=order_id)
        order.close()
        self.notifier(order, "done")
        log_action(f"order:{order.pk}", "done", user)
        return order

    @transaction.atomic
    def cancel_order(self, order_id, reason="", user=None):
        order = Order.objects.select_for_update().get(pk=order_id)
        if order.status == Order.Status.DONE:
            raise OrderStateError("Выполненный заказ нельзя отменить")
        order.status = Order.Status.CANCELLED
        order.save(update_fields=["status", "updated_at"])
        order.slot.release()
        self.notifier(order, "cancelled")
        log_action(f"order:{order.pk}", f"cancel:{reason or '-'}", user)
        return order

    def reschedule(self, order_id, slot_id, user=None):
        """Перенос заказа на другой свободный слот."""
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=order_id)
            new_slot = Slot.objects.select_for_update().filter(
                pk=slot_id, status=Slot.Status.FREE).first()
            if new_slot is None:
                raise SlotNotAvailable("Новый слот недоступен")
            old_slot = order.slot
            new_slot.status = Slot.Status.BUSY
            new_slot.save(update_fields=["status", "updated_at"])
            order.slot = new_slot
            order.executor = new_slot.executor
            order.save(update_fields=["slot", "executor", "updated_at"])
            old_slot.release()
            log_action(f"order:{order.pk}", f"reschedule:{old_slot.pk}->{new_slot.pk}", user)
        return order

    def release_expired_blocks(self):
        expired = Slot.objects.filter(status=Slot.Status.BLOCKED,
                                      blocked_until__lt=timezone.now())
        count = 0
        for slot in expired.iterator():
            slot.release()
            count += 1
        return count

    def free_slots(self, service_id=None, on_date=None, limit=30):
        queryset = Slot.objects.filter(status=Slot.Status.FREE,
                                       executor__status="active").select_related("executor")
        if on_date:
            queryset = queryset.filter(date=on_date)
        return queryset.order_by("date", "time_from")[:limit]


def get_or_create_client(data):
    """Находит клиента по телефону или создаёт нового."""
    client = Client.objects.filter(phone=data["phone"]).first()
    if client:
        client.last_name = data["last_name"]
        client.first_name = data["first_name"]
        client.address = data["address"]
        client.email = data.get("email", "")
        client.save(update_fields=["last_name", "first_name", "address", "email", "updated_at"])
        return client
    return Client.objects.create(
        last_name=data["last_name"],
        first_name=data["first_name"],
        phone=data["phone"],
        email=data.get("email", ""),
        address=data["address"],
    )
