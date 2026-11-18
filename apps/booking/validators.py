"""Проверки данных задачи бронирования."""

from datetime import date


class ValidationError(ValueError):
    """Нарушено правило предметной области."""


def check_slot_interval(starts_at, ends_at):
    """Проверяет корректность интервала слота."""
    if starts_at >= ends_at:
        raise ValidationError("Время окончания должно быть позже начала")
    return True


def check_slot_overlap(existing, starts_at, ends_at):
    """Проверяет отсутствие пересечений с уже занятыми интервалами."""
    for slot in existing:
        if slot.date != starts_at.date():
            continue
        if starts_at.time() < slot.time_to and ends_at.time() > slot.time_from:
            raise ValidationError("Интервал пересекается с занятым слотом")
    return True


def check_order_status(order, allowed):
    """Проверяет допустимость перехода статуса заказа."""
    if order.status not in allowed:
        raise ValidationError(
            f"Недопустимый статус заказа: {order.get_status_display()}")
    return True


def check_visit_date(visit_date, max_days=60):
    """Проверяет диапазон даты визита."""
    if visit_date < date.today():
        raise ValidationError("Дата визита не может быть в прошлом")
    if (visit_date - date.today()).days > max_days:
        raise ValidationError(f"Дата визита не может быть позже {max_days} дней")
    return True
