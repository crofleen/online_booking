"""Маршруты личного кабинета."""

from django.urls import path

from apps.accounts import views

urlpatterns = [
    path("accounts/register/", views.register, name="register"),
    path("account/", views.client_profile, name="client_profile"),
    path("account/notifications/", views.notifications_list, name="client_notifications"),
]
