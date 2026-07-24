from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import api_views, views

router = DefaultRouter()
router.register("orders", api_views.OrderViewSet, basename="order")
router.register("flags", api_views.AnomalyFlagViewSet, basename="flag")

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/orders-table/", views.orders_table, name="orders-table"),
    path("dashboard/desk-summary/", views.desk_summary, name="dashboard-desk-summary"),
    path("dashboard/flags-panel/", views.flags_panel, name="dashboard-flags-panel"),
    path("api/", include(router.urls)),
    path("api/latency-series/", api_views.LatencySeriesView.as_view(), name="latency-series"),
    path("api/desk-summary/", api_views.DeskSummaryView.as_view(), name="desk-summary"),
]
