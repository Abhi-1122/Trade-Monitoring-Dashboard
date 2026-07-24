from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from monitoring import rules
from monitoring.models import AnomalyFlag, Fill, Order, Trader


def _make_trader(desk="EQUITIES-1"):
    return Trader.objects.create(trader_id=f"TR-{desk}", name="Test Trader", desk=desk)


def _make_order(trader, order_id, **kwargs):
    defaults = {
        "symbol": "AAPL",
        "side": Order.Side.BUY,
        "order_type": Order.OrderType.MARKET,
        "quantity": 100,
        "desk": trader.desk,
        "trader": trader,
    }
    defaults.update(kwargs)
    return Order.objects.create(order_id=order_id, **defaults)


def _set_created_at(order, when):
    Order.objects.filter(pk=order.pk).update(created_at=when)
    order.refresh_from_db()


class HighLatencyRuleTests(TestCase):
    def setUp(self):
        self.trader = _make_trader()

    def test_latency_over_5000_is_high_severity(self):
        order = _make_order(self.trader, "ORD-1", latency_ms=6000)
        candidates = rules.find_high_latency()
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].order, order)
        self.assertEqual(candidates[0].severity, AnomalyFlag.Severity.HIGH)

    def test_latency_between_2000_and_5000_is_medium_severity(self):
        _make_order(self.trader, "ORD-2", latency_ms=3200)
        candidates = rules.find_high_latency()
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].severity, AnomalyFlag.Severity.MEDIUM)

    def test_latency_under_threshold_not_flagged(self):
        _make_order(self.trader, "ORD-3", latency_ms=1500)
        self.assertEqual(rules.find_high_latency(), [])

    def test_latency_exactly_at_threshold_not_flagged(self):
        _make_order(self.trader, "ORD-4", latency_ms=2000)
        self.assertEqual(rules.find_high_latency(), [])


class DuplicateFillRuleTests(TestCase):
    def setUp(self):
        self.trader = _make_trader()
        self.order = _make_order(self.trader, "ORD-10")

    def test_fills_300ms_apart_matching_qty_price_are_flagged(self):
        base = timezone.now()
        Fill.objects.create(
            fill_id="F-1", order=self.order, fill_quantity=100, fill_price=Decimal("10.00"), filled_at=base
        )
        Fill.objects.create(
            fill_id="F-2",
            order=self.order,
            fill_quantity=100,
            fill_price=Decimal("10.00"),
            filled_at=base + timezone.timedelta(milliseconds=300),
        )
        candidates = rules.find_duplicate_fills()
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].order, self.order)
        self.assertEqual(candidates[0].severity, AnomalyFlag.Severity.HIGH)

    def test_fills_800ms_apart_are_not_flagged(self):
        base = timezone.now()
        Fill.objects.create(
            fill_id="F-3", order=self.order, fill_quantity=100, fill_price=Decimal("10.00"), filled_at=base
        )
        Fill.objects.create(
            fill_id="F-4",
            order=self.order,
            fill_quantity=100,
            fill_price=Decimal("10.00"),
            filled_at=base + timezone.timedelta(milliseconds=800),
        )
        self.assertEqual(rules.find_duplicate_fills(), [])

    def test_fills_close_in_time_but_different_price_are_not_flagged(self):
        base = timezone.now()
        Fill.objects.create(
            fill_id="F-5", order=self.order, fill_quantity=100, fill_price=Decimal("10.00"), filled_at=base
        )
        Fill.objects.create(
            fill_id="F-6",
            order=self.order,
            fill_quantity=100,
            fill_price=Decimal("10.50"),
            filled_at=base + timezone.timedelta(milliseconds=100),
        )
        self.assertEqual(rules.find_duplicate_fills(), [])


class RejectSpikeRuleTests(TestCase):
    def setUp(self):
        self.trader = _make_trader(desk="DERIVATIVES-1")

    def _make_reject(self, order_id, when):
        order = _make_order(
            self.trader,
            order_id,
            status=Order.Status.REJECTED,
            reject_reason=Order.RejectReason.RISK_LIMIT_BREACH,
        )
        _set_created_at(order, when)
        return order

    def test_four_rejects_within_5_minutes_flagged(self):
        base = timezone.now()
        for i in range(4):
            self._make_reject(f"ORD-R{i}", base + timezone.timedelta(minutes=i))
        candidates = rules.find_reject_spikes()
        self.assertEqual(len(candidates), 1)
        self.assertIsNone(candidates[0].order)
        self.assertEqual(candidates[0].desk, "DERIVATIVES-1")

    def test_three_rejects_within_5_minutes_not_flagged(self):
        base = timezone.now()
        for i in range(3):
            self._make_reject(f"ORD-S{i}", base + timezone.timedelta(minutes=i))
        self.assertEqual(rules.find_reject_spikes(), [])

    def test_four_rejects_spread_over_10_minutes_not_flagged(self):
        base = timezone.now()
        for i in range(4):
            self._make_reject(f"ORD-T{i}", base + timezone.timedelta(minutes=i * 4))
        self.assertEqual(rules.find_reject_spikes(), [])

    def test_flags_only_once_for_the_same_cluster(self):
        base = timezone.now()
        for i in range(6):
            self._make_reject(f"ORD-U{i}", base + timezone.timedelta(minutes=i * 0.5))
        candidates = rules.find_reject_spikes()
        self.assertEqual(len(candidates), 1)


class StaleOrderRuleTests(TestCase):
    def setUp(self):
        self.trader = _make_trader()
        self.now = timezone.now()

    def test_order_new_for_over_10_minutes_is_flagged(self):
        order = _make_order(self.trader, "ORD-20", status=Order.Status.NEW)
        _set_created_at(order, self.now - timezone.timedelta(minutes=15))
        candidates = rules.find_stale_orders(now=self.now)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].order, order)
        self.assertEqual(candidates[0].severity, AnomalyFlag.Severity.LOW)

    def test_order_acknowledged_for_over_10_minutes_is_flagged(self):
        order = _make_order(self.trader, "ORD-21", status=Order.Status.ACKNOWLEDGED, latency_ms=500)
        _set_created_at(order, self.now - timezone.timedelta(minutes=12))
        candidates = rules.find_stale_orders(now=self.now)
        self.assertEqual(len(candidates), 1)

    def test_order_new_for_5_minutes_not_flagged(self):
        order = _make_order(self.trader, "ORD-22", status=Order.Status.NEW)
        _set_created_at(order, self.now - timezone.timedelta(minutes=5))
        self.assertEqual(rules.find_stale_orders(now=self.now), [])

    def test_filled_order_never_flagged_regardless_of_age(self):
        order = _make_order(self.trader, "ORD-23", status=Order.Status.FILLED, latency_ms=500)
        _set_created_at(order, self.now - timezone.timedelta(minutes=30))
        self.assertEqual(rules.find_stale_orders(now=self.now), [])
