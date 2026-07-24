from django.conf import settings
from django.db import models


class Trader(models.Model):
    trader_id = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    desk = models.CharField(max_length=50)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.desk})"


class Order(models.Model):
    class Side(models.TextChoices):
        BUY = "BUY", "Buy"
        SELL = "SELL", "Sell"

    class OrderType(models.TextChoices):
        MARKET = "MARKET", "Market"
        LIMIT = "LIMIT", "Limit"

    class Status(models.TextChoices):
        NEW = "NEW", "New"
        ACKNOWLEDGED = "ACKNOWLEDGED", "Acknowledged"
        PARTIALLY_FILLED = "PARTIALLY_FILLED", "Partially Filled"
        FILLED = "FILLED", "Filled"
        CANCELLED = "CANCELLED", "Cancelled"
        REJECTED = "REJECTED", "Rejected"

    class RejectReason(models.TextChoices):
        RISK_LIMIT_BREACH = "RISK_LIMIT_BREACH", "Risk Limit Breach"
        INSUFFICIENT_MARGIN = "INSUFFICIENT_MARGIN", "Insufficient Margin"
        INVALID_SYMBOL = "INVALID_SYMBOL", "Invalid Symbol"
        EXCHANGE_TIMEOUT = "EXCHANGE_TIMEOUT", "Exchange Timeout"

    order_id = models.CharField(max_length=20, unique=True)
    symbol = models.CharField(max_length=20)
    side = models.CharField(max_length=10, choices=Side.choices)
    order_type = models.CharField(max_length=10, choices=OrderType.choices)
    quantity = models.PositiveIntegerField()
    limit_price = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    desk = models.CharField(max_length=50)
    trader = models.ForeignKey(Trader, on_delete=models.CASCADE, related_name="orders")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    reject_reason = models.CharField(
        max_length=30, choices=RejectReason.choices, null=True, blank=True
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["desk", "status"]),
            models.Index(fields=["status"]),
            models.Index(fields=["symbol"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.order_id} {self.symbol} {self.side} {self.quantity}@{self.status}"


class Fill(models.Model):
    fill_id = models.CharField(max_length=20, unique=True)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="fills")
    fill_quantity = models.PositiveIntegerField()
    fill_price = models.DecimalField(max_digits=12, decimal_places=4)
    filled_at = models.DateTimeField()

    class Meta:
        ordering = ["-filled_at"]
        indexes = [
            models.Index(fields=["order", "filled_at"]),
        ]

    def __str__(self):
        return f"{self.fill_id} order={self.order.order_id} {self.fill_quantity}@{self.fill_price}"


class AnomalyFlag(models.Model):
    class FlagType(models.TextChoices):
        HIGH_LATENCY = "HIGH_LATENCY", "High Latency"
        DUPLICATE_FILL = "DUPLICATE_FILL", "Duplicate Fill"
        REJECT_SPIKE = "REJECT_SPIKE", "Reject Spike"
        STALE_ORDER = "STALE_ORDER", "Stale Order"

    class Severity(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"

    flag_type = models.CharField(max_length=20, choices=FlagType.choices)
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="flags", null=True, blank=True
    )
    desk = models.CharField(max_length=50, null=True, blank=True)
    detail = models.TextField()
    severity = models.CharField(max_length=10, choices=Severity.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    acknowledged = models.BooleanField(default=False)
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acknowledged_flags",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["acknowledged", "-created_at"]),
            models.Index(fields=["flag_type"]),
        ]

    def __str__(self):
        target = self.order.order_id if self.order else self.desk
        return f"{self.flag_type} [{self.severity}] {target}"
