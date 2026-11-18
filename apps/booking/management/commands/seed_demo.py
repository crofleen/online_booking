"""Заполнение демонстрационными данными."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.booking.models import Client, Executor, Order, Review, Slot
from apps.catalog.models import Service, TariffPlan
from apps.notifications.models import send_status_notification
from apps.payments.models import Payment

SERVICES = [
    ("Сборка корпусной мебели", "Сборка и ремонт мебели", 120, "1800"),
    ("Ремонт мебели", "Сборка и ремонт мебели", 90, "1400"),
    ("Сборка кухни", "Сборка и ремонт мебели", 240, "4800"),
    ("Уборка квартиры", "Клининг", 120, "2600"),
    ("Химчистка дивана", "Клининг", 90, "2200"),
    ("Помощь в переезде", "Грузоперевозки", 180, "3500"),
    ("Навеска полок и карнизов", "Мелкий ремонт", 60, "900"),
    ("Замена смесителя", "Мелкий ремонт", 60, "1100"),
]

EXECUTORS = [
    ("Иванов Алексей Петрович", "+79031112211", "Сборка и ремонт мебели", "САО, ЦАО", "4.8"),
    ("Петров Сергей Викторович", "+79032223322", "Сборка и ремонт мебели", "ЮЗАО, ЦАО", "4.9"),
    ("Сидорова Мария Игоревна", "+79033334433", "Клининг", "ВАО, ЮВАО", "4.7"),
    ("Кузнецов Дмитрий Олегович", "+79034445544", "Мелкий ремонт, переезды", "САО, СВАО", "4.6"),
]

CLIENTS = [
    ("Смирнова", "Ольга", "+79161112233", "olga@example.com", "ул. Профсоюзная, 42, кв. 17"),
    ("Ковалёв", "Игорь", "+79162223344", "kovalev@example.com", "Ленинский пр-т, 15, кв. 4"),
    ("Лебедева", "Марина", "+79163334455", "", "ул. Гарибальди, 8, кв. 92"),
]

TIMES = [time(9, 0), time(11, 0), time(14, 0), time(16, 30)]


class Command(BaseCommand):
    help = "Создаёт демонстрационные услуги, исполнителей, слоты и заказы"

    def handle(self, *args, **options):
        User = get_user_model()
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@example.com", "admin123")
        if not User.objects.filter(username="+79001112233").exists():
            User.objects.create_user("+79001112233", "client@example.com", "client123")

        if not User.objects.filter(username="operator").exists():
            User.objects.create_user("operator", "operator@example.com", "operator123",
                                     is_staff=True)

        if Order.objects.exists():
            self.stdout.write(self.style.WARNING("Демонстрационные данные уже созданы"))
            return

        services = {}
        for name, category, duration, price in SERVICES:
            service = Service.objects.create(name=name, category=category,
                                             duration_min=duration,
                                             base_price=Decimal(price))
            TariffPlan.objects.create(service=service, urgency_rate=Decimal("1.15"),
                                      distance_rate=Decimal("1.20"),
                                      valid_from=date.today() - timedelta(days=30))
            services[name] = service

        executors = []
        for full_name, phone, qualification, geo_zone, rating in EXECUTORS:
            executors.append(Executor.objects.create(
                full_name=full_name, phone=phone, qualification=qualification,
                geo_zone=geo_zone, rating=Decimal(rating)))

        clients = []
        for last_name, first_name, phone, email, address in CLIENTS:
            clients.append(Client.objects.create(
                last_name=last_name, first_name=first_name, phone=phone, email=email,
                address=address))

        client_user = User.objects.filter(username="+79001112233").first()
        if client_user and clients:
            clients[0].user = client_user
            clients[0].save(update_fields=["user"])

        today = date.today()
        created_slots = 0
        for executor in executors:
            for offset in range(0, 14):
                day = today + timedelta(days=offset)
                for start in TIMES:
                    end = (datetime.combine(day, start) + timedelta(minutes=90)).time()
                    Slot.objects.create(executor=executor, date=day,
                                        time_from=start, time_to=end)
                    created_slots += 1

        self._create_demo_orders(services, executors, clients)

        self.stdout.write(self.style.SUCCESS(
            f"Создано: услуг {len(services)}, исполнителей {len(executors)}, "
            f"клиентов {len(clients)}, слотов {created_slots}"))

    def _create_demo_orders(self, services, executors, clients):
        """Создаёт заказы в разных статусах для наполнения отчётов."""
        demo = [
            (0, 0, "Сборка корпусной мебели", Order.Status.DONE, 2),
            (1, 2, "Уборка квартиры", Order.Status.DONE, 5),
            (2, 1, "Ремонт мебели", Order.Status.CONFIRMED, 1),
            (0, 2, "Химчистка дивана", Order.Status.CANCELLED, 3),
            (1, 0, "Навеска полок и карнизов", Order.Status.DONE, 7),
            (2, 3, "Помощь в переезде", Order.Status.NEW, 0),
        ]
        used_slots = set()
        for client_index, executor_index, service_name, status, days_ago in demo:
            client = clients[client_index]
            executor = executors[executor_index]
            service = services[service_name]
            created = datetime.now() - timedelta(days=days_ago, hours=2)

            slot = (Slot.objects.filter(executor=executor, date=created.date())
                    .exclude(pk__in=used_slots).order_by("time_from").first())
            if slot is None:
                slot = (Slot.objects.filter(executor=executor, status=Slot.Status.FREE)
                        .exclude(pk__in=used_slots).order_by("date", "time_from").first())
            if slot is None:
                continue
            used_slots.add(slot.pk)

            order = Order.objects.create(
                client=client,
                executor=executor,
                slot=slot,
                status=status,
                total_sum=service.base_price,
                payment_method="card",
            )
            order.items.create(service=service, qty=1, price=service.base_price)

            if status == Order.Status.NEW:
                payment_status = Payment.Status.PENDING
            else:
                payment_status = Payment.Status.PAID
            if status in (Order.Status.CONFIRMED, Order.Status.DONE):
                slot.status = Slot.Status.BUSY
                slot.save(update_fields=["status"])

            Payment.objects.create(
                order=order,
                amount=order.total_sum,
                method="card",
                status=payment_status,
                transaction_id=f"PAY-DEMO{order.pk:05d}",
            )
            Order.objects.filter(pk=order.pk).update(created_at=created)

            if status in (Order.Status.CONFIRMED, Order.Status.DONE):
                send_status_notification(order, "confirmed")
            if status == Order.Status.DONE:
                Review.objects.create(order=order, rating=5,
                                      comment="Всё выполнено аккуратно, мастер приехал вовремя")
                send_status_notification(order, "done")
