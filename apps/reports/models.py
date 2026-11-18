"""Журнал аудита и агрегированные отчёты."""

from django.db import models
from django.db.models import Avg, Count, Sum
from django.utils import timezone
from datetime import timedelta


class AuditEvent(models.Model):
    """Событие журнала аудита."""

    user_id = models.BigIntegerField("Пользователь", default=0)
    entity = models.CharField("Объект", max_length=60)
    action = models.CharField("Действие", max_length=60)
    created_at = models.DateTimeField("Время", auto_now_add=True)

    class Meta:
        db_table = "audit_events"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["entity", "created_at"])]
        verbose_name = "Событие журнала"
        verbose_name_plural = "Журнал событий"

    def __str__(self):
        return f"{self.created_at:%d.%m.%Y %H:%M} {self.entity} {self.action}"


def log_action(entity, action, user=None):
    """Записывает действие в журнал аудита."""
    return AuditEvent.objects.create(
        user_id=getattr(user, "pk", 0) or 0,
        entity=entity,
        action=action,
    )


def load_report(period_start=None, period_end=None):
    """Показатели загрузки исполнителей за период."""
    from apps.booking.models import Executor, Order, Slot

    period_end = period_end or timezone.now().date()
    period_start = period_start or period_end.replace(day=1)

    orders = Order.objects.filter(created_at__date__gte=period_start,
                                  created_at__date__lte=period_end)
    done = orders.filter(status=Order.Status.DONE)
    cancelled = orders.filter(status=Order.Status.CANCELLED)
    total = orders.count() or 1

    by_executor = (Executor.objects
                   .annotate(orders_count=Count("orders"),
                             done_count=Count("orders", filter=models.Q(orders__status="done")),
                             revenue=Sum("orders__total_sum"))
                   .order_by("-orders_count"))

    slots_total = Slot.objects.filter(date__gte=period_start, date__lte=period_end).count() or 1
    busy = Slot.objects.filter(date__gte=period_start, date__lte=period_end,
                               status=Slot.Status.BUSY).count()

    daily = []
    max_daily = 1
    cursor = period_start
    while cursor <= period_end:
        count = Order.objects.filter(created_at__date=cursor).count()
        daily.append({"date": cursor, "count": count})
        max_daily = max(max_daily, count)
        cursor += timedelta(days=1)

    for point in daily:
        point["percent"] = round(point["count"] / max_daily * 100)

    return {
        "daily": daily,
        "period_start": period_start,
        "period_end": period_end,
        "orders_total": orders.count(),
        "orders_done": done.count(),
        "orders_cancelled": cancelled.count(),
        "cancel_rate": round(cancelled.count() / total * 100, 1),
        "avg_check": done.aggregate(value=Avg("total_sum"))["value"] or 0,
        "revenue": done.aggregate(value=Sum("total_sum"))["value"] or 0,
        "load_percent": round(busy / slots_total * 100, 1),
        "by_executor": by_executor,
    }
