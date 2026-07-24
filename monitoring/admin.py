from django.contrib import admin

from .models import AnomalyFlag, Fill, Order, Trader


@admin.register(Trader)
class TraderAdmin(admin.ModelAdmin):
    list_display = ("trader_id", "name", "desk")
    list_filter = ("desk",)
    search_fields = ("trader_id", "name")


class FillInline(admin.TabularInline):
    model = Fill
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_id",
        "symbol",
        "side",
        "order_type",
        "quantity",
        "status",
        "desk",
        "trader",
        "latency_ms",
        "created_at",
    )
    list_filter = ("status", "desk", "side", "order_type", "symbol")
    search_fields = ("order_id", "symbol")
    date_hierarchy = "created_at"
    inlines = [FillInline]


@admin.register(Fill)
class FillAdmin(admin.ModelAdmin):
    list_display = ("fill_id", "order", "fill_quantity", "fill_price", "filled_at")
    search_fields = ("fill_id", "order__order_id")


@admin.register(AnomalyFlag)
class AnomalyFlagAdmin(admin.ModelAdmin):
    list_display = (
        "flag_type",
        "severity",
        "order",
        "desk",
        "acknowledged",
        "created_at",
    )
    list_filter = ("flag_type", "severity", "acknowledged")
    search_fields = ("detail", "desk", "order__order_id")
