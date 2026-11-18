"""Маршруты каталога."""

from django.urls import path

from apps.catalog import views

urlpatterns = [
    path("", views.home, name="home"),
    path("service/<int:service_id>/", views.service_detail, name="service_detail"),
]
