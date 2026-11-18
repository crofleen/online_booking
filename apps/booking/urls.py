"""Маршруты клиентских сценариев."""

from django.urls import path

from apps.booking import views

urlpatterns = [
    path("order/create/", views.create_order, name="create_order"),
    path("checkout/<int:order_id>/", views.checkout, name="checkout"),
    path("checkout/<int:order_id>/pay/", views.pay, name="pay"),
    path("order/<int:order_id>/", views.order_status, name="order_status"),
    path("order/<int:order_id>/cancel/", views.cancel, name="cancel_order"),
    path("order/<int:order_id>/review/", views.leave_review, name="leave_review"),
    path("account/orders/<int:order_id>/repeat/", views.repeat_order, name="repeat_order"),
    path("api/slots/", views.api_slots, name="api_slots"),
]
