"""Каталог услуг и тарифные планы."""

from django.db import models


class Service(models.Model):
    """Услуга каталога."""

    name = models.CharField("Наименование", max_length=150)
    category = models.CharField("Категория", max_length=60)
    duration_min = models.PositiveSmallIntegerField("Длительность, мин", default=60)
    base_price = models.DecimalField("Базовая цена", max_digits=10, decimal_places=2)
    active = models.BooleanField("Доступна к заказу", default=True)

    class Meta:
        db_table = "services"
        ordering = ("category", "name")
        verbose_name = "Услуга"
        verbose_name_plural = "Услуги"

    def __str__(self):
        return f"{self.name} ({self.base_price} ₽)"


class TariffPlan(models.Model):
    """Тарифный план с коэффициентами."""

    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="tariffs",
                                verbose_name="Услуга")
    urgency_rate = models.DecimalField("Коэффициент срочности", max_digits=4, decimal_places=2,
                                       default=1)
    distance_rate = models.DecimalField("Коэффициент удалённости", max_digits=4, decimal_places=2,
                                        default=1)
    valid_from = models.DateField("Действует с")
    valid_to = models.DateField("Действует по", null=True, blank=True)

    class Meta:
        db_table = "tariff_plans"
        ordering = ("-valid_from",)
        verbose_name = "Тарифный план"
        verbose_name_plural = "Тарифные планы"

    def __str__(self):
        return f"{self.service.name}: срочность {self.urgency_rate}, удалённость {self.distance_rate}"

    def is_active(self, on_date):
        return self.valid_from <= on_date and (self.valid_to is None or on_date <= self.valid_to)


class ServiceRepository:
    """Доступ к каталогу услуг."""

    @staticmethod
    def active():
        return Service.objects.filter(active=True)

    @staticmethod
    def categories():
        return (Service.objects.filter(active=True)
                .values_list("category", flat=True).distinct().order_by("category"))

    @staticmethod
    def get(service_id):
        return Service.objects.get(pk=service_id, active=True)


class TariffRepository:
    """Выбор действующего тарифа."""

    @staticmethod
    def get_active(service_id, on_date=None):
        from datetime import date

        on_date = on_date or date.today()
        plans = TariffPlan.objects.filter(service_id=service_id, valid_from__lte=on_date)
        plans = plans.exclude(valid_to__lt=on_date).order_by("-valid_from")
        return plans.first() or TariffPlan(service_id=service_id, valid_from=on_date)
