from django.http import HttpResponse
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import api_views

router = DefaultRouter()
router.register("orders", api_views.OrderViewSet, basename="order")
router.register("flags", api_views.AnomalyFlagViewSet, basename="flag")


def placeholder(request):
    return HttpResponse("Trade Monitoring Dashboard — scaffold OK. Dashboard UI lands in a later commit.")


urlpatterns = [
    path("dashboard/", placeholder, name="dashboard"),
    path("api/", include(router.urls)),
    path("api/latency-series/", api_views.LatencySeriesView.as_view(), name="latency-series"),
    path("api/desk-summary/", api_views.DeskSummaryView.as_view(), name="desk-summary"),
]
