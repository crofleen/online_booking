"""Расчёт стоимости заказа."""

from decimal import Decimal, ROUND_HALF_UP


class PricingError(ValueError):
    """Ошибка расчёта стоимости."""


class PriceCalculator:
    """Применяет тарифные коэффициенты к составу заказа."""

    DISCOUNT_THRESHOLD = Decimal("10000")
    DISCOUNT_RATE = Decimal("0.05")

    def __init__(self, tariff_repository):
        self.tariffs = tariff_repository

    def calc(self, items, urgent=False, distance_km=0):
        if not items:
            raise PricingError("Состав заказа пуст")
        base = Decimal("0")
        for item in items:
            if item["qty"] <= 0:
                raise PricingError("Количество должно быть положительным")
            base += Decimal(str(item["price"])) * Decimal(item["qty"])

        plan = self.tariffs.get_active(items[0]["service_id"])
        rate = Decimal("1")
        if urgent:
            rate *= Decimal(plan.urgency_rate)
        if distance_km > 10:
            rate *= Decimal(plan.distance_rate)

        total = base * rate
        if total >= self.DISCOUNT_THRESHOLD:
            total -= total * self.DISCOUNT_RATE
        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
