from django.db.models import Count, Q
from django.shortcuts import render
from django.utils import timezone

from .constants import DESKS, SYMBOLS
from .models import AnomalyFlag, Order

ALLOWED_SORT_FIELDS = {"symbol", "quantity", "status", "desk", "latency_ms", "created_at"}


def _orders_table_context(request):
    orders = Order.objects.select_related("trader")

    desk = request.GET.get("desk") or ""
    status = request.GET.get("status") or ""
    symbol = request.GET.get("symbol") or ""
    sort = request.GET.get("sort") or "-created_at"

    if sort.lstrip("-") not in ALLOWED_SORT_FIELDS:
        sort = "-created_at"

    if desk:
        orders = orders.filter(desk=desk)
    if status:
        orders = orders.filter(status=status)
    if symbol:
        orders = orders.filter(symbol=symbol)

    orders = orders.order_by(sort)

    return {
        "orders": orders[:50],
        "desks": DESKS,
        "symbols": sorted(SYMBOLS),
        "statuses": Order.Status.choices,
        "selected_desk": desk,
        "selected_status": status,
        "selected_symbol": symbol,
        "current_sort": sort,
    }


def _desk_summary_context():
    summary = (
        Order.objects.values("desk")
        .annotate(
            order_count=Count("id"),
            reject_count=Count("id", filter=Q(status=Order.Status.REJECTED)),
        )
        .order_by("desk")
    )
    rows = []
    for row in summary:
        reject_rate = (
            round(row["reject_count"] / row["order_count"] * 100, 1) if row["order_count"] else 0.0
        )
        rows.append({**row, "reject_rate_pct": reject_rate})
    return {"desk_rows": rows}


def _flags_panel_context(request):
    flags = (
        AnomalyFlag.objects.filter(acknowledged=False)
        .select_related("order")
        .order_by("-created_at")[:30]
    )
    return {"flags": flags, "can_acknowledge": request.user.is_authenticated}


def dashboard(request):
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    context = {
        "open_orders_count": Order.objects.filter(
            status__in=[
                Order.Status.NEW,
                Order.Status.ACKNOWLEDGED,
                Order.Status.PARTIALLY_FILLED,
            ]
        ).count(),
        "flags_today_count": AnomalyFlag.objects.filter(created_at__gte=today_start).count(),
        **_orders_table_context(request),
        **_desk_summary_context(),
        **_flags_panel_context(request),
    }
    return render(request, "monitoring/dashboard.html", context)


def orders_table(request):
    return render(request, "monitoring/partials/orders_table.html", _orders_table_context(request))


def desk_summary(request):
    return render(request, "monitoring/partials/desk_summary.html", _desk_summary_context())


def flags_panel(request):
    return render(request, "monitoring/partials/flags_panel.html", _flags_panel_context(request))
