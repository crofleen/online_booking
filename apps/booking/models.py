"""Модели предметной области: клиенты, исполнители, слоты, заказы."""

from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Изменено", auto_now=True)

    class Meta:
        abstract = True


class Client(TimeStampedModel):
    """Клиент сервиса."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                null=True, blank=True, related_name="client_profile",
                                verbose_name="Учётная запись")
    last_name = models.CharField("Фамилия", max_length=60)
    first_name = models.CharField("Имя", max_length=60)
    phone = models.CharField("Телефон", max_length=12)
    email = models.EmailField("Электронная почта", blank=True)
    address = models.CharField("Адрес визита", max_length=250)
    consent_at = models.DateTimeField("Дата согласия на обработку данных",
                                      default=timezone.now)

    class Meta:
        db_table = "clients"
        ordering = ("last_name", "first_name")
        verbose_name = "Клиент"
        verbose_name_plural = "Клиенты"

    def __str__(self):
        return f"{self.last_name} {self.first_name[:1]}."

    @property
    def display_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def active_orders(self):
        return self.orders.filter(status__in=(Order.Status.NEW, Order.Status.CONFIRMED))


class Executor(TimeStampedModel):
    """Исполнитель услуг."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Активен"
        SUSPENDED = "suspended", "Приостановлен"
        BLOCKED = "blocked", "Заблокирован"

    full_name = models.CharField("ФИО", max_length=120)
    phone = models.CharField("Телефон", max_length=12)
    qualification = models.CharField("Квалификация", max_length=120)
    geo_zone = models.CharField("Геозона", max_length=120)
    rating = models.DecimalField("Рейтинг", max_digits=2, decimal_places=1, default=5.0,
                                 validators=[MinValueValidator(0), MaxValueValidator(5)])
    status = models.CharField("Статус", max_length=16, choices=Status.choices,
                              default=Status.ACTIVE)

    class Meta:
        db_table = "executors"
        verbose_name = "Исполнитель"
        verbose_name_plural = "Исполнители"

    def __str__(self):
        return self.full_name

    def is_available(self):
        return self.status == self.Status.ACTIVE


class Slot(TimeStampedModel):
    """Интервал времени исполнителя."""

    class Status(models.TextChoices):
        FREE = "free", "Свободен"
        BLOCKED = "blocked", "Заблокирован"
        BUSY = "busy", "Занят"
        CANCELLED = "cancelled", "Отменён"

    executor = models.ForeignKey(Executor, on_delete=models.CASCADE, related_name="slots",
                                 verbose_name="Исполнитель")
    date = models.DateField("Дата")
    time_from = models.TimeField("Начало")
    time_to = models.TimeField("Окончание")
    status = models.CharField("Статус", max_length=16, choices=Status.choices,
                              default=Status.FREE)
    blocked_until = models.DateTimeField("Блокировка до", null=True, blank=True)

    class Meta:
        db_table = "slots"
        ordering = ("date", "time_from")
        indexes = [models.Index(fields=["executor", "date"])]
        verbose_name = "Слот"
        verbose_name_plural = "Слоты"

    def __str__(self):
        return f"{self.executor.full_name}: {self.date:%d.%m.%Y} {self.time_from:%H:%M}"

    def mark_blocked(self, ttl_minutes=10):
        from datetime import timedelta

        if self.status != Slot.Status.FREE:
            raise ValueError("Слот недоступен для блокировки")
        self.status = Slot.Status.BLOCKED
        self.blocked_until = timezone.now() + timedelta(minutes=ttl_minutes)
        self.save(update_fields=["status", "blocked_until", "updated_at"])

    def release(self):
        self.status = Slot.Status.FREE
        self.blocked_until = None
        self.save(update_fields=["status", "blocked_until", "updated_at"])


class Order(TimeStampedModel):
    """Заказ на выполнение услуг."""

    class Status(models.TextChoices):
        NEW = "new", "Новый"
        CONFIRMED = "confirmed", "Подтверждён"
        DONE = "done", "Выполнен"
        CANCELLED = "cancelled", "Отменён"

    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="orders",
                               verbose_name="Клиент")
    executor = models.ForeignKey(Executor, on_delete=models.PROTECT, related_name="orders",
                                 verbose_name="Исполнитель")
    slot = models.ForeignKey(Slot, on_delete=models.PROTECT, related_name="orders",
                              verbose_name="Слот")
    status = models.CharField("Статус", max_length=16, choices=Status.choices,
                              default=Status.NEW)
    total_sum = models.DecimalField("Сумма", max_digits=10, decimal_places=2, default=0)
    payment_method = models.CharField("Способ оплаты", max_length=20, default="card")

    class Meta:
        db_table = "orders"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["status", "created_at"])]
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"

    def __str__(self):
        return f"Заказ №{self.pk} от {self.created_at:%d.%m.%Y}"

    def confirm(self):
        if self.status != Order.Status.NEW:
            raise ValueError("Подтвердить можно только новый заказ")
        self.status = Order.Status.CONFIRMED
        self.save(update_fields=["status", "updated_at"])

    def close(self):
        if self.status != Order.Status.CONFIRMED:
            raise ValueError("Закрыть можно только подтверждённый заказ")
        self.status = Order.Status.DONE
        self.save(update_fields=["status", "updated_at"])

    @property
    def is_closed(self):
        return self.status in (Order.Status.DONE, Order.Status.CANCELLED)


class OrderItem(models.Model):
    """Позиция заказа."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items",
                              verbose_name="Заказ")
    service = models.ForeignKey("catalog.Service", on_delete=models.PROTECT,
                                verbose_name="Услуга")
    qty = models.PositiveSmallIntegerField("Количество", default=1)
    price = models.DecimalField("Цена", max_digits=10, decimal_places=2)
    amount = models.DecimalField("Стоимость", max_digits=10, decimal_places=2, default=0)

    class Meta:
        db_table = "order_items"
        verbose_name = "Позиция заказа"
        verbose_name_plural = "Позиции заказа"

    def save(self, *args, **kwargs):
        self.amount = self.price * self.qty
        super().save(*args, **kwargs)


class Review(TimeStampedModel):
    """Отзыв клиента о заказе."""

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="review",
                                 verbose_name="Заказ")
    rating = models.PositiveSmallIntegerField("Оценка",
                                              validators=[MinValueValidator(1),
                                                          MaxValueValidator(5)])
    comment = models.TextField("Текст отзыва", blank=True)

    class Meta:
        db_table = "reviews"
        verbose_name = "Отзыв"
        verbose_name_plural = "Отзывы"

    def __str__(self):
        return f"Отзыв к заказу №{self.order_id}: {self.rating}/5"
