from django.db.models import Count, Q
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .constants import HIGH_LATENCY_MEDIUM_MS
from .models import AnomalyFlag, Order
from .serializers import AnomalyFlagSerializer, OrderDetailSerializer, OrderListSerializer


class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/orders/            — list, filterable by ?desk= ?status= ?symbol=
    GET /api/orders/<order_id>/ — detail including fills
    """

    queryset = Order.objects.select_related("trader").prefetch_related("fills")
    lookup_field = "order_id"

    def get_serializer_class(self):
        if self.action == "retrieve":
            return OrderDetailSerializer
        return OrderListSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if desk := params.get("desk"):
            qs = qs.filter(desk=desk)
        if status_ := params.get("status"):
            qs = qs.filter(status=status_)
        if symbol := params.get("symbol"):
            qs = qs.filter(symbol=symbol)
        return qs


class AnomalyFlagViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET  /api/flags/              — list flags, filterable by ?severity=; defaults to
                                     active (non-acknowledged) flags unless ?acknowledged= is given
    POST /api/flags/<id>/acknowledge/ — mark acknowledged (requires login)
    """

    queryset = AnomalyFlag.objects.select_related("order", "acknowledged_by")
    serializer_class = AnomalyFlagSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if severity := params.get("severity"):
            qs = qs.filter(severity=severity)
        if "acknowledged" in params:
            qs = qs.filter(acknowledged=params.get("acknowledged") == "true")
        else:
            qs = qs.filter(acknowledged=False)
        return qs

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def acknowledge(self, request, pk=None):
        flag = self.get_object()
        flag.acknowledged = True
        flag.acknowledged_by = request.user
        flag.save(update_fields=["acknowledged", "acknowledged_by"])
        return Response(AnomalyFlagSerializer(flag).data)


class LatencySeriesView(APIView):
    """GET /api/latency-series/ — last N orders' ack latency values + timestamps, for the chart."""

    def get(self, request):
        limit = int(request.query_params.get("limit", 50))
        orders = (
            Order.objects.filter(latency_ms__isnull=False)
            .order_by("-created_at")[:limit]
            .values("order_id", "latency_ms", "created_at")
        )
        data = list(reversed(orders))  # chronological order for the chart
        return Response(
            {
                "threshold_ms": HIGH_LATENCY_MEDIUM_MS,
                "points": data,
            }
        )


class DeskSummaryView(APIView):
    """GET /api/desk-summary/ — per-desk aggregate counts for the summary strip."""

    def get(self, request):
        summary = (
            Order.objects.values("desk")
            .annotate(
                order_count=Count("id"),
                reject_count=Count("id", filter=Q(status=Order.Status.REJECTED)),
            )
            .order_by("desk")
        )
        results = []
        for row in summary:
            reject_rate = (
                round(row["reject_count"] / row["order_count"] * 100, 1)
                if row["order_count"]
                else 0.0
            )
            results.append({**row, "reject_rate_pct": reject_rate})
        return Response(results)
