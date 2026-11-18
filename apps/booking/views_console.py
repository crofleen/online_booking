"""Рабочее место оператора: календарь, заказы, отчёты, тарифы."""

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render

from apps.booking.models import Executor, Order, Slot
from apps.booking.services import (BookingService, OrderStateError, SlotNotAvailable,
                                   get_or_create_client)
from apps.catalog.models import Service, TariffPlan
from apps.payments.services import close_cash_payment, refund_payment
from apps.reports.models import load_report, log_action


def _week_start(request):
    raw = request.GET.get("start")
    if raw:
        try:
            return date.fromisoformat(raw)
        except ValueError:
            pass
    return date.today()


@login_required
def dashboard(request):
    """Календарь загрузки исполнителей на неделю."""
    start = _week_start(request)
    days = [start + timedelta(days=offset) for offset in range(7)]
    executors = Executor.objects.all().order_by("full_name")
    slots = list(Slot.objects.filter(date__gte=days[0], date__lte=days[-1])
                 .select_related("executor").order_by("time_from"))
    active = {order.slot_id: order for order in Order.objects.filter(
        slot__in=slots, status__in=(Order.Status.NEW, Order.Status.CONFIRMED),
    )}
    for slot in slots:
        slot.active_order = active.get(slot.pk)

    grid = {}
    for slot in slots:
        grid.setdefault((slot.executor_id, slot.date), []).append(slot)

    rows = []
    for executor in executors:
        rows.append({
            "executor": executor,
            "cells": [{"date": day, "slots": grid.get((executor.pk, day), [])}
                      for day in days],
        })

    mobile = []
    for day in days:
        mobile.append({
            "date": day,
            "rows": [{"executor": executor,
                      "slots": grid.get((executor.pk, day), [])}
                     for executor in executors],
        })

    return render(request, "console/calendar.html", {
        "rows": rows,
        "mobile": mobile,
        "days": days,
        "start": start,
        "prev_week": (start - timedelta(days=7)).isoformat(),
        "next_week": (start + timedelta(days=7)).isoformat(),
        "orders_today": Order.objects.filter(created_at__date=date.today()).count(),
        "free_slots": Slot.objects.filter(status=Slot.Status.FREE,
                                         date__gte=date.today()).count(),
        "today": date.today(),
    })


@login_required
def order_list(request):
    """Реестр заказов с фильтрами."""
    orders = Order.objects.select_related("client", "executor", "slot").prefetch_related("items")
    status = request.GET.get("status", "")
    query = request.GET.get("q", "").strip()
    if status:
        orders = orders.filter(status=status)
    if query:
        orders = orders.filter(Q(pk__icontains=query)
                               | Q(client__phone__icontains=query)
                               | Q(client__last_name__icontains=query))
    total = orders.count()
    return render(request, "console/orders.html", {
        "orders": orders[:100],
        "status": status,
        "query": query,
        "total": total,
        "statuses": Order.Status.choices,
    })


@login_required
def order_detail(request, order_id):
    """Карточка заказа для оператора."""
    order = get_object_or_404(
        Order.objects.select_related("client", "executor", "slot")
        .prefetch_related("items", "payments", "notifications"), pk=order_id)
    free_slots = (Slot.objects.filter(status=Slot.Status.FREE, date__gte=date.today())
                  .select_related("executor").order_by("date", "time_from")[:40])
    return render(request, "console/order.html", {"order": order, "free_slots": free_slots})


@login_required
def order_action(request, order_id, action):
    """Изменение состояния заказа."""
    order = get_object_or_404(Order, pk=order_id)
    service = BookingService()
    try:
        if action == "confirm":
            service.confirm_order(order.pk, user=request.user)
            messages.success(request, "Заказ подтверждён, клиент уведомлён")
        elif action == "close":
            close_cash_payment(order, user=request.user)
            service.close_order(order.pk, user=request.user)
            messages.success(request, "Заказ закрыт, акт выполненных работ сформирован")
        elif action == "cancel":
            service.cancel_order(order.pk, reason=request.POST.get("reason", "оператор"),
                                 user=request.user)
            refund_payment(order, user=request.user)
            messages.success(request, "Заказ отменён, слот освобождён")
        elif action == "reschedule":
            service.reschedule(order.pk, int(request.POST["slot_id"]), user=request.user)
            messages.success(request, "Заказ перенесён на выбранный слот")
        else:
            messages.error(request, "Неизвестное действие")
    except (OrderStateError, SlotNotAvailable, ValueError) as error:
        messages.error(request, str(error))
    return redirect("operator_order", order_id=order.pk)


@login_required
def executor_detail(request, executor_id):
    """Карточка исполнителя."""
    executor = get_object_or_404(Executor, pk=executor_id)
    orders = (Order.objects.filter(executor=executor)
              .select_related("slot", "client").order_by("-created_at")[:15])
    slots = (Slot.objects.filter(executor=executor, date__gte=date.today())
             .order_by("date", "time_from")[:30])
    stats = Order.objects.filter(executor=executor).aggregate(
        done=Count("id", filter=Q(status=Order.Status.DONE)),
        revenue=Sum("total_sum", filter=Q(status=Order.Status.DONE)),
        cancelled=Count("id", filter=Q(status=Order.Status.CANCELLED)),
        total=Count("id"),
    )
    return render(request, "console/executor.html", {
        "executor": executor,
        "orders": orders,
        "slots": slots,
        "stats": stats,
    })


@login_required
def claim_new(request):
    """Создание заявки оператором по телефонному обращению."""
    services = Service.objects.filter(active=True)
    free_slots = (Slot.objects.filter(status=Slot.Status.FREE, date__gte=date.today())
                  .select_related("executor").order_by("date", "time_from")[:60])
    if request.method == "POST":
        data = {
            "last_name": request.POST.get("last_name", "").strip(),
            "first_name": request.POST.get("first_name", "").strip(),
            "phone": request.POST.get("phone", "").strip(),
            "email": request.POST.get("email", "").strip(),
            "address": request.POST.get("address", "").strip(),
        }
        service_id = request.POST.get("service_id")
        slot_id = request.POST.get("slot_id")
        if not all([data["last_name"], data["first_name"], data["phone"], data["address"],
                    service_id, slot_id]):
            messages.error(request, "Заполните данные клиента, услугу и слот")
        else:
            service_obj = get_object_or_404(Service, pk=service_id)
            client = get_or_create_client(data)
            items = [{"service_id": service_obj.pk, "qty": 1, "price": service_obj.base_price}]
            try:
                order = BookingService().create_order(
                    client, int(slot_id), items,
                    urgent=request.POST.get("urgent") == "on",
                    distance_km=int(request.POST.get("distance_km") or 0),
                    user=request.user,
                )
                messages.success(request, f"Заявка №{order.pk} оформлена")
                return redirect("operator_order", order_id=order.pk)
            except (SlotNotAvailable, OrderStateError) as error:
                messages.error(request, str(error))
    return render(request, "console/claim.html", {"services": services, "slots": free_slots})


@login_required
def report(request):
    """Отчёт о загрузке исполнителей."""
    raw_start = request.GET.get("start")
    raw_end = request.GET.get("end")
    try:
        start = date.fromisoformat(raw_start) if raw_start else None
        end = date.fromisoformat(raw_end) if raw_end else None
    except ValueError:
        start = end = None
    data = load_report(start, end)
    return render(request, "console/report.html", data)


@login_required
def slots(request):
    """Управление слотами исполнителей."""
    from datetime import datetime

    executors = Executor.objects.all().order_by("full_name")
    if request.method == "POST":
        if request.POST.get("action") == "delete":
            slot = get_object_or_404(Slot, pk=request.POST.get("slot_id"))
            if slot.status == Slot.Status.FREE:
                slot.delete()
                messages.success(request, "Слот удалён")
            else:
                messages.error(request, "Занятый слот удалить нельзя")
            return redirect("operator_slots")

        executor = get_object_or_404(Executor, pk=request.POST.get("executor_id"))
        try:
            start_day = date.fromisoformat(request.POST["date_from"])
            start_time = datetime.strptime(request.POST["time_from"], "%H:%M").time()
            days = max(1, min(60, int(request.POST.get("days") or 1)))
            duration = max(30, min(480, int(request.POST.get("duration") or 90)))
        except (KeyError, ValueError):
            messages.error(request, "Проверьте дату, время и длительность")
            return redirect("operator_slots")

        created = 0
        for offset in range(days):
            day = start_day + timedelta(days=offset)
            end_time = (datetime.combine(day, start_time)
                        + timedelta(minutes=duration)).time()
            _, is_new = Slot.objects.get_or_create(
                executor=executor, date=day, time_from=start_time,
                defaults={"time_to": end_time},
            )
            created += int(is_new)
        log_action(f"executor:{executor.pk}", f"slots:+{created}", request.user)
        messages.success(request, f"Добавлено слотов: {created}")
        return redirect("operator_slots")

    upcoming = (Slot.objects.filter(date__gte=date.today() - timedelta(days=1))
                .select_related("executor").order_by("date", "time_from")[:120])
    return render(request, "console/slots.html", {"executors": executors,
                                                  "slots": upcoming,
                                                  "today": date.today()})


@login_required
def tariffs(request):
    """Настройка тарифных планов."""
    if request.method == "POST":
        service_id = request.POST.get("service_id")
        try:
            urgency = Decimal(request.POST.get("urgency_rate", "1").replace(",", "."))
            distance = Decimal(request.POST.get("distance_rate", "1").replace(",", "."))
        except InvalidOperation:
            messages.error(request, "Коэффициенты должны быть числами")
            return redirect("operator_tariffs")
        service_obj = get_object_or_404(Service, pk=service_id)
        TariffPlan.objects.create(
            service=service_obj,
            urgency_rate=urgency,
            distance_rate=distance,
            valid_from=date.today(),
        )
        log_action(f"service:{service_obj.pk}", f"tariff:{urgency}/{distance}", request.user)
        messages.success(request, "Тариф обновлён, ранее оформленные заказы сохраняют стоимость")
        return redirect("operator_tariffs")

    services = Service.objects.filter(active=True)
    plans = (TariffPlan.objects.select_related("service").order_by("service__name",
                                                                  "-valid_from")[:60])
    return render(request, "console/tariffs.html", {"services": services, "plans": plans})
