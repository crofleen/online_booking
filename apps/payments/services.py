"""Имитация платёжного шлюза."""

import uuid

from apps.booking.services import BookingService
from apps.payments.models import Payment
from apps.reports.models import log_action


class PaymentError(Exception):
    """Ошибка проведения платежа."""


def _transaction_id():
    return f"PAY-{uuid.uuid4().hex[:10].upper()}"


def process_payment(order, method="card", card_number="", user=None):
    """Проводит платёж и подтверждает заказ.

    Демонстрационная логика: карта, номер которой оканчивается на 0000,
    отклоняется; остальные способы считаются успешными.
    """
    if order.status != order.Status.NEW:
        raise PaymentError("Заказ уже обработан")

    digits = "".join(ch for ch in card_number if ch.isdigit())

    if method == "cash":
        payment = Payment.objects.create(
            order=order,
            amount=order.total_sum,
            method=method,
            status=Payment.Status.PENDING,
            transaction_id=_transaction_id(),
        )
        order.payment_method = method
        order.save(update_fields=["payment_method", "updated_at"])
        BookingService().confirm_order(order.pk, payment.transaction_id, user=user)
        return payment

    if method == "card":
        if len(digits) != 16:
            raise PaymentError("Проверьте номер карты: требуется 16 цифр")
        if digits.endswith("0000"):
            Payment.objects.create(
                order=order,
                amount=order.total_sum,
                method=method,
                status=Payment.Status.REJECTED,
                transaction_id=_transaction_id(),
            )
            log_action(f"order:{order.pk}", "payment-rejected", user)
            raise PaymentError("Платёж отклонён банком. Попробуйте другую карту")

    payment = Payment.objects.create(
        order=order,
        amount=order.total_sum,
        method=method,
        status=Payment.Status.PAID,
        transaction_id=_transaction_id(),
    )
    order.payment_method = method
    order.save(update_fields=["payment_method", "updated_at"])
    BookingService().confirm_order(order.pk, payment.transaction_id, user=user)
    return payment


def close_cash_payment(order, user=None):
    """Отмечает оплату по факту при закрытии заказа."""
    payment = order.payments.filter(status=Payment.Status.PENDING).first()
    if payment is not None:
        payment.status = Payment.Status.PAID
        payment.save(update_fields=["status"])
        log_action(f"order:{order.pk}", "cash-paid", user)
    return payment


def refund_payment(order, user=None):
    """Возврат средств по отменённому заказу."""
    payment = order.payments.filter(status=Payment.Status.PAID).first()
    if payment is None:
        return None
    payment.status = Payment.Status.REFUNDED
    payment.save(update_fields=["status"])
    log_action(f"order:{order.pk}", "refund", user)
    return payment
