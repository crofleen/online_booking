"""Шаблонные фильтры оформления."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django import template

register = template.Library()


@register.filter
def money(value):
    """Форматирует сумму как целое число с пробелами: 4 830."""
    try:
        number = int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, TypeError, ValueError):
        return value
    return f"{number:,}".replace(",", " ")


@register.filter
def rub(value):
    """Сумма с обозначением валюты."""
    return f"{money(value)} ₽"


@register.filter
def plural_ru(value, forms):
    """Склоняет существительное: plural_ru:"заказ,заказа,заказов"."""
    try:
        number = abs(int(value))
    except (TypeError, ValueError):
        return forms
    one, few, many = [item.strip() for item in forms.split(",")]
    if number % 10 == 1 and number % 100 != 11:
        word = one
    elif 2 <= number % 10 <= 4 and not 12 <= number % 100 <= 14:
        word = few
    else:
        word = many
    return f"{number} {word}"
