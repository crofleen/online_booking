"""Уведомления участникам заказа."""

from django.db import models


class Notification(models.Model):
    """Запись об отправленном уведомлении."""

    class Channel(models.TextChoices):
        EMAIL = "email", "Электронная почта"
        SMS = "sms", "SMS"
        IN_APP = "in_app", "В приложении"

    order = models.ForeignKey("booking.Order", on_delete=models.CASCADE,
                              related_name="notifications", verbose_name="Заказ")
    channel = models.CharField("Канал", max_length=16, choices=Channel.choices,
                               default=Channel.IN_APP)
    recipient = models.CharField("Получатель", max_length=120)
    subject = models.CharField("Тема", max_length=200)
    body = models.TextField("Текст")
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        db_table = "notifications"
        ordering = ("-created_at",)
        verbose_name = "Уведомление"
        verbose_name_plural = "Уведомления"

    def __str__(self):
        return f"{self.recipient}: {self.subject}"


def send_status_notification(order, event):
    """Формирует уведомления клиенту и исполнителю по событию заказа."""
    titles = {
        "created": "Заявка принята",
        "confirmed": "Запись подтверждена",
        "cancelled": "Заказ отменён",
        "done": "Заказ выполнен",
    }
    subject = titles.get(event, "Изменение статуса заказа")
    body = (
        f"Заказ №{order.pk}. Услуга: "
        f"{', '.join(item.service.name for item in order.items.all())}. "
        f"Дата визита: {order.slot.date:%d.%m.%Y} в {order.slot.time_from:%H:%M}. "
        f"Исполнитель: {order.executor.full_name}. Сумма: {order.total_sum} руб."
    )
    created = []
    for recipient in (order.client.email or f"{order.client.phone}",
                      f"{order.executor.full_name} ({order.executor.phone})"):
        created.append(Notification.objects.create(
            order=order,
            channel=Notification.Channel.IN_APP,
            recipient=recipient,
            subject=subject,
            body=body,
        ))
    return created
