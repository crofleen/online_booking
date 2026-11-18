"""Вход, регистрация и личный кабинет клиента."""

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render

from apps.accounts.forms import ClientProfileForm, ClientRegistrationForm
from apps.booking.models import Order
from apps.notifications.models import Notification


class UnifiedLoginView(LoginView):
    """Вход для клиентов и операторов: логин — телефон или имя пользователя."""

    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        redirect_to = self.get_redirect_url()
        if redirect_to:
            return redirect_to
        if self.request.user.is_staff:
            return "/operator/"
        return "/account/"


def register(request):
    """Регистрация клиента."""
    if request.user.is_authenticated:
        return redirect("client_profile")
    form = ClientRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Регистрация завершена. Добро пожаловать!")
        return redirect("client_profile")
    return render(request, "accounts/register.html", {"form": form})


@login_required
def client_profile(request):
    """Личный кабинет: заказы, статистика, контактные данные."""
    profile = getattr(request.user, "client_profile", None)
    if profile is None:
        if request.user.is_staff:
            return redirect("operator_dashboard")
        messages.info(request, "Заполните контактные данные для продолжения")
        return redirect("register")

    form = ClientProfileForm(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Контактные данные обновлены")
        return redirect("client_profile")

    orders = (Order.objects.filter(client=profile)
              .select_related("slot", "executor")
              .prefetch_related("items")
              .order_by("-created_at"))
    return render(request, "accounts/profile.html", {
        "profile": profile,
        "form": form,
        "orders": orders[:30],
        "orders_total": orders.count(),
        "active_total": orders.filter(status__in=(Order.Status.NEW,
                                                  Order.Status.CONFIRMED)).count(),
        "reviews_total": orders.filter(review__isnull=False).count(),
    })


@login_required
def notifications_list(request):
    """Все уведомления клиента."""
    profile = getattr(request.user, "client_profile", None)
    if profile is None:
        return redirect("client_profile")
    items = (Notification.objects.filter(order__client=profile)
             .select_related("order").order_by("-created_at")[:100])
    return render(request, "accounts/notifications.html", {
        "profile": profile,
        "items": items,
    })
