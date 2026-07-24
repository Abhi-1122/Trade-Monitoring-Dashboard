"""
Rule-based anomaly detection.

Each `find_*` function is a pure function: given an (optional) queryset, it
returns a list of `FlagCandidate` — it does not touch `AnomalyFlag` or the
database at all. This keeps the rules unit-testable against small hand-built
querysets (see tests/test_rules.py) independent of the random feed generator,
and keeps persistence/idempotency concerns in the `detect_anomalies`
management command where they belong.

No ML here by design — these are simple, explainable threshold/window rules,
which is what an ops/compliance reviewer actually wants (a clear "why was
this flagged" answer), and is all this project needs to demonstrate.
"""

from collections import defaultdict, namedtuple
from datetime import timedelta

from django.utils import timezone

from .constants import (
    DUPLICATE_FILL_WINDOW_MS,
    HIGH_LATENCY_HIGH_MS,
    HIGH_LATENCY_MEDIUM_MS,
    REJECT_SPIKE_THRESHOLD,
    REJECT_SPIKE_WINDOW_MINUTES,
    STALE_ORDER_MINUTES,
)
from .models import AnomalyFlag, Fill, Order

FlagCandidate = namedtuple("FlagCandidate", ["flag_type", "order", "desk", "detail", "severity"])


def find_high_latency(orders=None):
    """Rule 1: latency_ms > 2000ms -> MEDIUM; > 5000ms -> HIGH."""
    qs = orders if orders is not None else Order.objects.filter(latency_ms__isnull=False)
    candidates = []
    for order in qs.filter(latency_ms__gt=HIGH_LATENCY_MEDIUM_MS):
        severity = (
            AnomalyFlag.Severity.HIGH
            if order.latency_ms > HIGH_LATENCY_HIGH_MS
            else AnomalyFlag.Severity.MEDIUM
        )
        detail = (
            f"Order {order.order_id} ack latency {order.latency_ms}ms "
            f"exceeds {HIGH_LATENCY_MEDIUM_MS}ms threshold"
        )
        candidates.append(
            FlagCandidate(AnomalyFlag.FlagType.HIGH_LATENCY, order, order.desk, detail, severity)
        )
    return candidates


def find_duplicate_fills(fills=None):
    """Rule 2: two fills on the same order within 500ms with identical qty/price."""
    qs = fills if fills is not None else Fill.objects.select_related("order")
    by_order = defaultdict(list)
    for fill in qs.order_by("order_id", "filled_at"):
        by_order[fill.order_id].append(fill)

    window = timedelta(milliseconds=DUPLICATE_FILL_WINDOW_MS)
    candidates = []
    for order_fills in by_order.values():
        flagged_this_order = False
        for i in range(len(order_fills)):
            if flagged_this_order:
                break
            for j in range(i + 1, len(order_fills)):
                a, b = order_fills[i], order_fills[j]
                gap = b.filled_at - a.filled_at
                if gap > window:
                    break  # sorted by time — no later fill can be closer
                if a.fill_quantity == b.fill_quantity and a.fill_price == b.fill_price:
                    detail = (
                        f"Order {a.order.order_id} has duplicate fills {a.fill_id} and "
                        f"{b.fill_id} ({a.fill_quantity}@{a.fill_price}) "
                        f"{int(gap.total_seconds() * 1000)}ms apart"
                    )
                    candidates.append(
                        FlagCandidate(
                            AnomalyFlag.FlagType.DUPLICATE_FILL,
                            a.order,
                            a.order.desk,
                            detail,
                            AnomalyFlag.Severity.HIGH,
                        )
                    )
                    flagged_this_order = True
                    break
    return candidates


def find_reject_spikes(orders=None):
    """Rule 3: more than 3 REJECTED orders from the same desk in a rolling 5-minute window."""
    qs = orders if orders is not None else Order.objects.filter(status=Order.Status.REJECTED)
    by_desk = defaultdict(list)
    for order in qs.order_by("desk", "created_at"):
        by_desk[order.desk].append(order)

    window = timedelta(minutes=REJECT_SPIKE_WINDOW_MINUTES)
    breach_size = REJECT_SPIKE_THRESHOLD + 1
    candidates = []
    for desk, desk_orders in by_desk.items():
        left = 0
        for right, order in enumerate(desk_orders):
            while order.created_at - desk_orders[left].created_at > window:
                left += 1
            count = right - left + 1
            if count == breach_size:
                # Flag exactly once, at the order that pushes the rolling
                # count past the threshold — not on every order afterwards.
                window_orders = desk_orders[left : right + 1]
                order_ids = ", ".join(o.order_id for o in window_orders)
                detail = (
                    f"{count} rejected orders on desk {desk} within "
                    f"{REJECT_SPIKE_WINDOW_MINUTES}-minute window: {order_ids}"
                )
                candidates.append(
                    FlagCandidate(
                        AnomalyFlag.FlagType.REJECT_SPIKE,
                        None,
                        desk,
                        detail,
                        AnomalyFlag.Severity.HIGH,
                    )
                )
    return candidates


def find_stale_orders(orders=None, now=None):
    """Rule 4: order stuck in NEW/ACKNOWLEDGED for more than 10 minutes."""
    now = now or timezone.now()
    cutoff = now - timedelta(minutes=STALE_ORDER_MINUTES)
    qs = orders if orders is not None else Order.objects.filter(
        status__in=[Order.Status.NEW, Order.Status.ACKNOWLEDGED],
        created_at__lt=cutoff,
    )
    candidates = []
    for order in qs:
        age_minutes = int((now - order.created_at).total_seconds() // 60)
        detail = (
            f"Order {order.order_id} has been {order.status} for {age_minutes} minutes "
            f"without reaching a terminal status (threshold {STALE_ORDER_MINUTES}m)"
        )
        candidates.append(
            FlagCandidate(
                AnomalyFlag.FlagType.STALE_ORDER, order, order.desk, detail, AnomalyFlag.Severity.LOW
            )
        )
    return candidates


ALL_RULES = [find_high_latency, find_duplicate_fills, find_reject_spikes, find_stale_orders]
