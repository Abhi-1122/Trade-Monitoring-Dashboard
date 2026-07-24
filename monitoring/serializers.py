from rest_framework import serializers

from .models import AnomalyFlag, Fill, Order


class FillSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fill
        fields = ["fill_id", "fill_quantity", "fill_price", "filled_at"]


class OrderListSerializer(serializers.ModelSerializer):
    trader_name = serializers.CharField(source="trader.name", read_only=True)

    class Meta:
        model = Order
        fields = [
            "order_id",
            "symbol",
            "side",
            "order_type",
            "quantity",
            "limit_price",
            "status",
            "desk",
            "trader_name",
            "latency_ms",
            "reject_reason",
            "created_at",
            "updated_at",
        ]


class OrderDetailSerializer(OrderListSerializer):
    fills = FillSerializer(many=True, read_only=True)

    class Meta(OrderListSerializer.Meta):
        fields = OrderListSerializer.Meta.fields + ["fills"]


class AnomalyFlagSerializer(serializers.ModelSerializer):
    order_id = serializers.CharField(source="order.order_id", read_only=True, default=None)
    acknowledged_by_username = serializers.CharField(
        source="acknowledged_by.username", read_only=True, default=None
    )

    class Meta:
        model = AnomalyFlag
        fields = [
            "id",
            "flag_type",
            "order_id",
            "desk",
            "detail",
            "severity",
            "created_at",
            "acknowledged",
            "acknowledged_by_username",
        ]
