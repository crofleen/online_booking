"""Платежи по заказам."""

from django.db import models


class Payment(models.Model):
    """Платёж по заказу (имитация платёжного шлюза)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает"
        PAID = "paid", "Проведён"
        REJECTED = "rejected", "Отклонён"
        REFUNDED = "refunded", "Возвращён"

    order = models.ForeignKey("booking.Order", on_delete=models.PROTECT,
                              related_name="payments", verbose_name="Заказ")
    amount = models.DecimalField("Сумма", max_digits=10, decimal_places=2)
    method = models.CharField("Способ", max_length=20)
    status = models.CharField("Статус", max_length=16, choices=Status.choices,
                              default=Status.PENDING)
    transaction_id = models.CharField("Идентификатор транзакции", max_length=64, unique=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        db_table = "payments"
        ordering = ("-created_at",)
        verbose_name = "Платёж"
        verbose_name_plural = "Платежи"

    def __str__(self):
        return f"Платёж {self.transaction_id}: {self.amount} ₽"
