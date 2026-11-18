"""Маршрутизация проекта."""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.accounts.views import UnifiedLoginView
from apps.booking import views_console
from apps.booking.api import OrderViewSet, SlotViewSet

router = DefaultRouter()
router.register("orders", OrderViewSet, basename="api-orders")
router.register("slots", SlotViewSet, basename="api-slots")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include(router.urls)),
    path("", include("apps.catalog.urls")),
    path("", include("apps.accounts.urls")),
    path("", include("apps.booking.urls")),
    path("accounts/login/", UnifiedLoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("operator/", views_console.dashboard, name="operator_dashboard"),
    path("operator/orders/", views_console.order_list, name="operator_orders"),
    path("operator/orders/<int:order_id>/", views_console.order_detail, name="operator_order"),
    path("operator/orders/<int:order_id>/action/<str:action>/", views_console.order_action,
         name="operator_order_action"),
    path("operator/executors/<int:executor_id>/", views_console.executor_detail,
         name="operator_executor"),
    path("operator/claim/", views_console.claim_new, name="operator_claim"),
    path("operator/slots/", views_console.slots, name="operator_slots"),
    path("operator/report/", views_console.report, name="operator_report"),
    path("operator/tariffs/", views_console.tariffs, name="operator_tariffs"),
]
