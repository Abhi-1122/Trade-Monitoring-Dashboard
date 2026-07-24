from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from monitoring.models import AnomalyFlag, Fill, Order, Trader


class TraderModelTests(TestCase):
    def test_str(self):
        trader = Trader.objects.create(trader_id="TR-001", name="Alice", desk="EQUITIES-1")
        self.assertEqual(str(trader), "Alice (EQUITIES-1)")


class OrderModelTests(TestCase):
    def setUp(self):
        self.trader = Trader.objects.create(trader_id="TR-001", name="Alice", desk="EQUITIES-1")

    def test_create_order_defaults_to_new_status(self):
        order = Order.objects.create(
            order_id="ORD-000001",
            symbol="AAPL",
            side=Order.Side.BUY,
            order_type=Order.OrderType.MARKET,
            quantity=100,
            desk="EQUITIES-1",
            trader=self.trader,
        )
        self.assertEqual(order.status, Order.Status.NEW)
        self.assertIsNone(order.limit_price)
        self.assertIsNone(order.reject_reason)

    def test_limit_order_can_have_price(self):
        order = Order.objects.create(
            order_id="ORD-000002",
            symbol="TSLA",
            side=Order.Side.SELL,
            order_type=Order.OrderType.LIMIT,
            quantity=50,
            limit_price=Decimal("245.50"),
            desk="EQUITIES-1",
            trader=self.trader,
        )
        self.assertEqual(order.limit_price, Decimal("245.50"))

    def test_str_contains_order_id_and_status(self):
        order = Order.objects.create(
            order_id="ORD-000003",
            symbol="AAPL",
            side=Order.Side.BUY,
            order_type=Order.OrderType.MARKET,
            quantity=10,
            desk="EQUITIES-1",
            trader=self.trader,
        )
        self.assertIn("ORD-000003", str(order))
        self.assertIn("NEW", str(order))

    def test_order_id_unique_constraint(self):
        Order.objects.create(
            order_id="ORD-000004",
            symbol="AAPL",
            side=Order.Side.BUY,
            order_type=Order.OrderType.MARKET,
            quantity=10,
            desk="EQUITIES-1",
            trader=self.trader,
        )
        with self.assertRaises(Exception):
            Order.objects.create(
                order_id="ORD-000004",
                symbol="TSLA",
                side=Order.Side.SELL,
                order_type=Order.OrderType.MARKET,
                quantity=20,
                desk="EQUITIES-1",
                trader=self.trader,
            )


class FillModelTests(TestCase):
    def setUp(self):
        self.trader = Trader.objects.create(trader_id="TR-001", name="Alice", desk="EQUITIES-1")
        self.order = Order.objects.create(
            order_id="ORD-000010",
            symbol="AAPL",
            side=Order.Side.BUY,
            order_type=Order.OrderType.MARKET,
            quantity=100,
            desk="EQUITIES-1",
            trader=self.trader,
        )

    def test_fill_linked_to_order(self):
        fill = Fill.objects.create(
            fill_id="FILL-000001",
            order=self.order,
            fill_quantity=100,
            fill_price=Decimal("189.23"),
            filled_at=timezone.now(),
        )
        self.assertEqual(fill.order, self.order)
        self.assertIn(fill, self.order.fills.all())


class AnomalyFlagModelTests(TestCase):
    def setUp(self):
        self.trader = Trader.objects.create(trader_id="TR-001", name="Alice", desk="EQUITIES-1")
        self.order = Order.objects.create(
            order_id="ORD-000020",
            symbol="AAPL",
            side=Order.Side.BUY,
            order_type=Order.OrderType.MARKET,
            quantity=100,
            desk="EQUITIES-1",
            trader=self.trader,
            latency_ms=4200,
        )

    def test_order_level_flag_str(self):
        flag = AnomalyFlag.objects.create(
            flag_type=AnomalyFlag.FlagType.HIGH_LATENCY,
            order=self.order,
            detail="Order ORD-000020 ack latency 4200ms exceeds 2000ms threshold",
            severity=AnomalyFlag.Severity.MEDIUM,
        )
        self.assertFalse(flag.acknowledged)
        self.assertIn("ORD-000020", str(flag))

    def test_desk_level_flag_allows_null_order(self):
        flag = AnomalyFlag.objects.create(
            flag_type=AnomalyFlag.FlagType.REJECT_SPIKE,
            desk="EQUITIES-1",
            detail="4 rejects on EQUITIES-1 in rolling 5-minute window",
            severity=AnomalyFlag.Severity.HIGH,
        )
        self.assertIsNone(flag.order)
        self.assertIn("EQUITIES-1", str(flag))
