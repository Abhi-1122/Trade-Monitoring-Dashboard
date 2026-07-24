import random
import time
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from monitoring.constants import DESKS, REJECT_REASONS, SYMBOLS
from monitoring.models import Fill, Order, Trader

# The first few orders get deterministically forced into interesting outcomes
# so a reviewer watching the dashboard (or the --duration 60 smoke test) sees
# every anomaly type's precondition quickly, rather than waiting on
# probability. Everything after this warm-up draws from the normal
# distribution below.
FORCED_OUTCOMES = ["reject", "stale", "fill_high_latency", "fill_duplicate"]

REJECT_PROBABILITY = 0.05
STALE_PROBABILITY = 0.03
HIGH_LATENCY_PROBABILITY = 0.02
DUPLICATE_FILL_PROBABILITY = 0.01


def _log_uniform_quantity():
    """10-5000, log-distributed so most orders are small with occasional large ones."""
    return int(round(10 * (500 ** random.random())))


def _next_sequence(model, field):
    last = model.objects.order_by(f"-{field}").values_list(field, flat=True).first()
    if last:
        try:
            return int(last.split("-")[-1]) + 1
        except ValueError:
            pass
    return 1


class Command(BaseCommand):
    help = "Continuously generate a synthetic stream of orders, acks, fills, and rejects."

    def add_arguments(self, parser):
        parser.add_argument(
            "--duration",
            type=int,
            default=None,
            help="Stop after this many seconds (default: run forever).",
        )
        parser.add_argument(
            "--inject-reject-burst",
            action="store_true",
            help=(
                "Fire desk-level reject bursts (4-6 rejects in a couple of seconds) "
                "aggressively/soon, to guarantee a REJECT_SPIKE demo case quickly. "
                "Bursts happen periodically either way; this just speeds up the first one."
            ),
        )

        parser.add_argument(
            "--interval-min",
            type=float,
            default=0.5,
            help="Minimum seconds between new orders (default 0.5).",
        )
        parser.add_argument(
            "--interval-max",
            type=float,
            default=2.0,
            help="Maximum seconds between new orders (default 2.0).",
        )

    def handle(self, *args, **options):
        traders = list(Trader.objects.all())
        if not traders:
            self.stderr.write(
                self.style.ERROR("No traders found — run `python manage.py seed_data` first.")
            )
            return

        self.interval_min = options["interval_min"]
        self.interval_max = options["interval_max"]
        duration = options["duration"]
        inject_bursts = options["inject_reject_burst"]

        self.order_seq = _next_sequence(Order, "order_id")
        self.fill_seq = _next_sequence(Fill, "fill_id")
        self.pending = []
        self.orders_created = 0

        burst_delay_range = (5, 10) if inject_bursts else (15, 30)
        self.next_burst_at = time.monotonic() + random.uniform(*burst_delay_range)
        self.burst_recurrence_range = (20, 45) if inject_bursts else (45, 90)

        start = time.monotonic()
        self.stdout.write(self.style.SUCCESS("Feed generator started. Ctrl+C to stop."))
        try:
            while duration is None or (time.monotonic() - start) < duration:
                self._create_order(traders)
                if time.monotonic() >= self.next_burst_at:
                    self._inject_reject_burst(traders)
                    self.next_burst_at = time.monotonic() + random.uniform(*self.burst_recurrence_range)
                self._process_pending()
                time.sleep(random.uniform(self.interval_min, self.interval_max))
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Feed generator stopped."))
            return

        # Drain: keep resolving already-scheduled lifecycle transitions for a
        # few more seconds so a bounded --duration run actually persists the
        # anomaly preconditions it kicked off near the end of the window.
        drain_until = time.monotonic() + 10
        while self.pending and time.monotonic() < drain_until:
            self._process_pending()
            time.sleep(0.5)

        self.stdout.write(self.style.SUCCESS("Feed generator finished (duration elapsed)."))

    # -- order creation -----------------------------------------------------

    def _create_order(self, traders):
        trader = random.choice(traders)
        symbol = random.choice(list(SYMBOLS))
        seed_price = SYMBOLS[symbol]
        side = random.choice(["BUY", "SELL"])
        order_type = random.choice(["MARKET", "LIMIT"])
        quantity = _log_uniform_quantity()

        limit_price = None
        if order_type == "LIMIT":
            pct = random.uniform(-0.02, 0.02)
            limit_price = Decimal(str(round(seed_price * (1 + pct), 4)))

        order_id = f"ORD-{self.order_seq:06d}"
        self.order_seq += 1

        order = Order.objects.create(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            limit_price=limit_price,
            status=Order.Status.NEW,
            desk=trader.desk,
            trader=trader,
        )

        outcome = self._next_outcome()
        self._schedule(order, outcome)
        self.orders_created += 1

    def _next_outcome(self):
        if self.orders_created < len(FORCED_OUTCOMES):
            return FORCED_OUTCOMES[self.orders_created]

        roll = random.random()
        if roll < REJECT_PROBABILITY:
            return "reject"
        if roll < REJECT_PROBABILITY + STALE_PROBABILITY:
            return "stale"
        return "fill"

    # -- lifecycle scheduling -------------------------------------------------
    #
    # Rather than resolving an order's whole lifecycle the instant it's
    # created, each order gets a "plan" (target outcome + timing) that the
    # loop advances tick by tick using real wall-clock delays. This is what
    # makes the dashboard show orders actually sitting in NEW/ACKNOWLEDGED
    # for a few seconds before settling, instead of everything appearing
    # FILLED instantly.

    def _schedule(self, order, outcome):
        force_high_latency = outcome == "fill_high_latency"
        force_duplicate = outcome == "fill_duplicate"
        if outcome in ("fill_high_latency", "fill_duplicate"):
            outcome = "fill"

        high_latency = force_high_latency or random.random() < HIGH_LATENCY_PROBABILITY
        latency_ms = random.randint(3000, 8000) if high_latency else random.randint(50, 1800)

        plan = {
            "order_id": order.pk,
            "outcome": outcome,
            "stage": "awaiting_ack",
            "latency_ms": latency_ms,
            "due_at": time.monotonic() + latency_ms / 1000.0,
            "force_duplicate": force_duplicate,
        }
        if outcome == "stale":
            # About half of stale orders never even get acknowledged.
            plan["skip_ack"] = random.random() < 0.5

        self.pending.append(plan)

    def _process_pending(self):
        """
        Advance each plan through as many due stages as have elapsed in a
        single pass. This matters for closely-spaced transitions (e.g. a
        multi-fill sequence): the outer loop only ticks every 0.5-2s, so
        without draining same-plan stages here, two events scheduled a few
        hundred ms apart could end up separated by a full tick instead.
        """
        now = time.monotonic()
        still_pending = []
        for plan in self.pending:
            keep = True
            while keep and plan["due_at"] <= now:
                if plan["stage"] == "awaiting_ack":
                    keep = self._resolve_ack(plan)
                elif plan["stage"] == "awaiting_fill":
                    keep = self._resolve_fill_step(plan)
            if keep:
                still_pending.append(plan)

        self.pending = still_pending

    def _resolve_ack(self, plan):
        order = Order.objects.get(pk=plan["order_id"])

        if plan["outcome"] == "stale" and plan.get("skip_ack"):
            return False  # left in NEW forever, dropped from the schedule

        if plan["outcome"] == "reject":
            order.status = Order.Status.REJECTED
            order.latency_ms = plan["latency_ms"]
            order.reject_reason = random.choice(REJECT_REASONS)
            order.save(update_fields=["status", "latency_ms", "reject_reason", "updated_at"])
            return False

        order.status = Order.Status.ACKNOWLEDGED
        order.latency_ms = plan["latency_ms"]
        order.save(update_fields=["status", "latency_ms", "updated_at"])

        if plan["outcome"] == "stale":
            return False  # acknowledged, then deliberately never resolved further

        self._plan_fills(order, plan)
        return True

    def _plan_fills(self, order, plan):
        qty = order.quantity
        price = self._fill_price(order)

        segments = [qty]
        if qty > 1000 and random.random() < 0.5:
            n = random.randint(2, 4)
            remaining = qty
            segments = []
            for i in range(n - 1):
                part = max(1, int(remaining * random.uniform(0.2, 0.4)))
                part = min(part, remaining - (n - i - 1))
                segments.append(part)
                remaining -= part
            segments.append(remaining)

        fills = []
        cursor = 0.0
        for seg_qty in segments:
            cursor += random.uniform(0.3, 2.0)
            fills.append({"delay": cursor, "qty": seg_qty, "price": price})

        plan["stage"] = "awaiting_fill"
        plan["fills"] = fills
        plan["fill_index"] = 0
        plan["scheduled_at"] = time.monotonic()
        plan["due_at"] = plan["scheduled_at"] + fills[0]["delay"]

    def _fill_price(self, order):
        base = float(order.limit_price) if order.limit_price else SYMBOLS[order.symbol]
        slip = random.uniform(-0.001, 0.001)
        return Decimal(str(round(base * (1 + slip), 4)))

    def _resolve_fill_step(self, plan):
        order = Order.objects.get(pk=plan["order_id"])
        idx = plan["fill_index"]
        seg = plan["fills"][idx]

        filled_at = timezone.now()
        fill_id = f"FILL-{self.fill_seq:06d}"
        self.fill_seq += 1
        Fill.objects.create(
            fill_id=fill_id,
            order=order,
            fill_quantity=seg["qty"],
            fill_price=seg["price"],
            filled_at=filled_at,
        )

        is_last = idx == len(plan["fills"]) - 1
        order.status = Order.Status.FILLED if is_last else Order.Status.PARTIALLY_FILLED
        order.save(update_fields=["status", "updated_at"])

        if is_last:
            duplicate = plan["force_duplicate"] or random.random() < DUPLICATE_FILL_PROBABILITY
            if duplicate:
                # Set the timestamp explicitly (rather than relying on
                # further tick-based scheduling) so the two fills are
                # guaranteed to land under the 500ms DUPLICATE_FILL window,
                # regardless of the outer loop's 0.5-2s tick interval.
                dup_fill_id = f"FILL-{self.fill_seq:06d}"
                self.fill_seq += 1
                Fill.objects.create(
                    fill_id=dup_fill_id,
                    order=order,
                    fill_quantity=seg["qty"],
                    fill_price=seg["price"],
                    filled_at=filled_at + timedelta(milliseconds=random.randint(50, 400)),
                )
            return False  # done, drop from schedule

        plan["fill_index"] += 1
        plan["due_at"] = plan["scheduled_at"] + plan["fills"][idx + 1]["delay"]
        return True

    # -- reject burst injection ----------------------------------------------

    def _inject_reject_burst(self, traders):
        desk = random.choice(DESKS)
        desk_traders = [t for t in traders if t.desk == desk] or traders
        self.stdout.write(self.style.WARNING(f"Injecting reject burst on desk {desk}"))

        for _ in range(random.randint(4, 6)):
            trader = random.choice(desk_traders)
            order_id = f"ORD-{self.order_seq:06d}"
            self.order_seq += 1
            Order.objects.create(
                order_id=order_id,
                symbol=random.choice(list(SYMBOLS)),
                side=random.choice(["BUY", "SELL"]),
                order_type=random.choice(["MARKET", "LIMIT"]),
                quantity=_log_uniform_quantity(),
                status=Order.Status.REJECTED,
                desk=desk,
                trader=trader,
                latency_ms=random.randint(50, 500),
                reject_reason=random.choice(REJECT_REASONS),
            )
            time.sleep(random.uniform(0.1, 0.3))
