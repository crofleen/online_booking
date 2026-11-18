"""Клиентские страницы каталога."""

from datetime import date, timedelta

from django.db.models import Avg, Count, OuterRef, Subquery
from django.shortcuts import get_object_or_404, render

from apps.booking.models import OrderItem, Slot
from apps.catalog.models import Service, TariffRepository


def _rated_services():
    """Услуги с рейтингом по отзывам и числом заказов."""
    ratings = (OrderItem.objects
               .filter(service=OuterRef("pk"), order__review__isnull=False)
               .values("service")
               .annotate(value=Avg("order__review__rating"))
               .values("value"))
    return (Service.objects.filter(active=True)
            .annotate(avg_rating=Subquery(ratings), orders_count=Count("orderitem")))


def home(request):
    """Главная страница: категории и услуги каталога."""
    query = request.GET.get("q", "").strip()
    active_category = request.GET.get("category", "").strip()

    services = _rated_services()
    if query:
        services = services.filter(name__icontains=query)
    if active_category:
        services = services.filter(category=active_category)

    grouped = {}
    for service in services.order_by("category", "name"):
        grouped.setdefault(service.category, []).append(service)

    categories = (Service.objects.filter(active=True)
                  .values_list("category", flat=True).distinct().order_by("category"))

    return render(request, "catalog/home.html", {
        "grouped": grouped,
        "categories": categories,
        "query": query,
        "active_category": active_category,
        "today": date.today(),
    })


def _dates(days=14):
    today = date.today()
    return [today + timedelta(days=offset) for offset in range(days)]


def service_detail(request, service_id):
    """Карточка услуги и выбор свободного слота."""
    service = get_object_or_404(_rated_services(), pk=service_id)
    tariff = TariffRepository.get_active(service.pk)
    dates = _dates(14)
    selected = request.GET.get("date")
    try:
        selected_date = date.fromisoformat(selected) if selected else dates[0]
    except ValueError:
        selected_date = dates[0]

    slots = (Slot.objects.filter(status=Slot.Status.FREE,
                                 executor__status="active",
                                 date=selected_date)
             .select_related("executor")
             .order_by("time_from"))

    groups = {}
    for slot in slots:
        groups.setdefault(slot.executor, []).append(slot)

    available = set(
        Slot.objects.filter(status=Slot.Status.FREE, executor__status="active",
                            date__gte=dates[0], date__lte=dates[-1])
        .values_list("date", flat=True)
    )

    profile = getattr(request.user, "client_profile", None)

    return render(request, "catalog/service.html", {
        "service": service,
        "tariff": tariff,
        "dates": dates,
        "selected_date": selected_date,
        "groups": groups,
        "slots_count": slots.count(),
        "available": available,
        "profile": profile,
    })
