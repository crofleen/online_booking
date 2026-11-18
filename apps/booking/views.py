"""Клиентские сценарии: оформление, оплата, статус заказа."""

from decimal import Decimal

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.booking.models import Order, Review, Slot
from apps.booking.services import (BookingService, OrderStateError, SlotNotAvailable,
                                   get_or_create_client)
from apps.catalog.models import Service
from apps.payments.services import PaymentError, process_payment, refund_payment


def _back(service_id):
    return redirect(f"/service/{service_id}/")


def _client_form(request):
    return {
        "last_name": request.POST.get("last_name", "").strip(),
        "first_name": request.POST.get("first_name", "").strip(),
        "phone": request.POST.get("phone", "").strip(),
        "email": request.POST.get("email", "").strip(),
        "address": request.POST.get("address", "").strip(),
    }


@require_POST
def create_order(request):
    """Создание заказа из карточки услуги."""
    service = get_object_or_404(Service, pk=request.POST.get("service_id"), active=True)
    profile = getattr(request.user, "client_profile", None)

    if profile is not None:
        client = profile
        address = request.POST.get("address", "").strip()
        if address and address != profile.address:
            profile.address = address
            profile.save(update_fields=["address", "updated_at"])
    else:
        data = _client_form(request)
        if not (data["last_name"] and data["first_name"] and data["phone"]
                and data["address"]):
            messages.error(request, "Заполните фамилию, имя, телефон и адрес визита")
            return _back(service.pk)
        if not request.POST.get("consent"):
            messages.error(request,
                           "Для оформления записи нужно согласие на обработку данных")
            return _back(service.pk)
        client = get_or_create_client(data)

    items = [{"service_id": service.pk, "qty": 1, "price": service.base_price}]
    try:
        distance = int(request.POST.get("distance_km") or 0)
    except ValueError:
        distance = 0

    try:
        order = BookingService().create_order(
            client=client,
            slot_id=int(request.POST["slot_id"]),
            items=items,
            urgent=request.POST.get("urgent") == "on",
            distance_km=distance,
            user=request.user if request.user.is_authenticated else None,
        )
    except (SlotNotAvailable, OrderStateError) as error:
        messages.error(request, str(error))
        return _back(service.pk)

    messages.success(request, f"Заказ №{order.pk} создан. Слот удерживается 10 минут.")
    return redirect("checkout", order_id=order.pk)


def checkout(request, order_id):
    """Экран оплаты."""
    order = get_object_or_404(Order, pk=order_id)
    return render(request, "booking/checkout.html", {"order": order})


@require_POST
def pay(request, order_id):
    """Проведение демонстрационного платежа."""
    order = get_object_or_404(Order, pk=order_id)
    method = request.POST.get("method", "card")
    try:
        process_payment(order, method=method, card_number=request.POST.get("card_number", ""))
    except PaymentError as error:
        messages.error(request, str(error))
        return redirect("checkout", order_id=order.pk)
    messages.success(request, "Оплата прошла успешно, запись подтверждена")
    return redirect("order_status", order_id=order.pk)


def order_status(request, order_id):
    """Статус заказа для клиента."""
    order = get_object_or_404(Order.objects.prefetch_related("items", "payments", "notifications"),
                              pk=order_id)
    profile = getattr(request.user, "client_profile", None)
    owner_ok = (order.client.user_id is None or
                (profile is not None and order.client_id == profile.pk) or
                (request.user.is_authenticated and request.user.is_staff))
    if not owner_ok:
        return render(request, "404.html", status=404)
    review = getattr(order, "review", None)
    return render(request, "booking/order.html", {"order": order, "review": review})


@require_POST
def repeat_order(request, order_id):
    """Повтор заказа: возврат к услуге из истории."""
    order = get_object_or_404(Order.objects.prefetch_related("items"), pk=order_id)
    profile = getattr(request.user, "client_profile", None)
    if profile is None or order.client_id != profile.pk:
        return render(request, "404.html", status=404)
    item = order.items.first()
    if item is None:
        return redirect("home")
    messages.info(request, "Выберите дату и время для повторного заказа")
    return redirect("service_detail", service_id=item.service_id)


@require_POST
def cancel(request, order_id):
    """Отмена заказа клиентом."""
    order = get_object_or_404(Order, pk=order_id)
    try:
        BookingService().cancel_order(order.pk, reason="клиент")
        refund_payment(order)
        messages.success(request, "Заказ отменён")
    except OrderStateError as error:
        messages.error(request, str(error))
    return redirect("order_status", order_id=order.pk)


@require_POST
def leave_review(request, order_id):
    """Отзыв клиента после выполнения заказа."""
    order = get_object_or_404(Order, pk=order_id)
    if order.status != Order.Status.DONE:
        messages.error(request, "Отзыв можно оставить только после выполнения заказа")
        return redirect("order_status", order_id=order.pk)
    rating = int(request.POST.get("rating", 5))
    Review.objects.update_or_create(
        order=order,
        defaults={"rating": max(1, min(5, rating)),
                  "comment": request.POST.get("comment", "").strip()},
    )
    messages.success(request, "Спасибо за отзыв")
    return redirect("order_status", order_id=order.pk)


def api_slots(request):
    """JSON со свободными слотами (упрощённый программный интерфейс)."""
    service_id = request.GET.get("service_id")
    on_date = request.GET.get("date")
    slots = BookingService().free_slots(service_id=service_id, on_date=on_date)
    return JsonResponse({
        "count": len(slots),
        "slots": [
            {
                "id": slot.pk,
                "executor": slot.executor.full_name,
                "date": slot.date.isoformat(),
                "time_from": slot.time_from.strftime("%H:%M"),
                "time_to": slot.time_to.strftime("%H:%M"),
            }
            for slot in slots
        ],
    })


def not_found(request, exception=None):
    return render(request, "404.html", status=404)
