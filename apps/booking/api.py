"""Программный интерфейс бронирования (REST, Django REST framework)."""

from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.booking.models import Order, Slot
from apps.booking.services import (BookingService, OrderStateError, SlotNotAvailable,
                                   get_or_create_client)
from apps.catalog.models import Service


class SlotSerializer(serializers.ModelSerializer):
    executor_name = serializers.CharField(source="executor.full_name", read_only=True)

    class Meta:
        model = Slot
        fields = ("id", "executor_name", "date", "time_from", "time_to", "status")


class OrderItemSerializer(serializers.Serializer):
    service_id = serializers.IntegerField(min_value=1)
    qty = serializers.IntegerField(min_value=1, max_value=20)


class OrderCreateSerializer(serializers.Serializer):
    slot_id = serializers.IntegerField(min_value=1)
    items = OrderItemSerializer(many=True, allow_empty=False)
    last_name = serializers.CharField(max_length=60)
    first_name = serializers.CharField(max_length=60)
    phone = serializers.CharField(max_length=12)
    address = serializers.CharField(max_length=250)
    email = serializers.EmailField(required=False, allow_blank=True)
    urgent = serializers.BooleanField(default=False)
    distance_km = serializers.IntegerField(min_value=0, max_value=200, default=0)


class OrderViewSet(viewsets.GenericViewSet):
    """Создание, подтверждение и отмена заказа через API."""

    serializer_class = OrderCreateSerializer

    def create(self, request):
        payload = self.get_serializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        client = get_or_create_client({
            "last_name": data["last_name"],
            "first_name": data["first_name"],
            "phone": data["phone"],
            "address": data["address"],
            "email": data.get("email", ""),
        })
        items = []
        for item in data["items"]:
            service = Service.objects.get(pk=item["service_id"], active=True)
            items.append({"service_id": service.pk, "qty": item["qty"],
                          "price": service.base_price})
        try:
            order = BookingService().create_order(
                client=client,
                slot_id=data["slot_id"],
                items=items,
                urgent=data["urgent"],
                distance_km=data["distance_km"],
            )
        except (SlotNotAvailable, OrderStateError) as error:
            return Response({"detail": str(error)}, status=status.HTTP_409_CONFLICT)
        return Response({"order_id": order.pk, "total": str(order.total_sum)},
                        status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        transaction_id = request.data.get("transaction_id", "")
        try:
            order = BookingService().confirm_order(int(pk), transaction_id)
        except OrderStateError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"order_id": order.pk, "status": order.status})

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        try:
            order = BookingService().cancel_order(int(pk), request.data.get("reason", ""))
        except OrderStateError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"order_id": order.pk, "status": order.status})

    @action(detail=False, methods=["get"])
    def available_slots(self, request):
        date = request.query_params.get("date")
        slots = BookingService().free_slots(on_date=date)
        return Response({"count": len(slots), "slots": SlotSerializer(slots, many=True).data})


class SlotViewSet(viewsets.ReadOnlyModelViewSet):
    """Справочник свободных слотов."""

    serializer_class = SlotSerializer

    def get_queryset(self):
        queryset = Slot.objects.filter(status=Slot.Status.FREE).select_related("executor")
        date = self.request.query_params.get("date")
        if date:
            queryset = queryset.filter(date=date)
        return queryset.order_by("date", "time_from")
