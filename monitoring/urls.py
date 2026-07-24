from django.http import HttpResponse
from django.urls import path


def placeholder(request):
    return HttpResponse("Trade Monitoring Dashboard — scaffold OK. Dashboard UI lands in a later commit.")


urlpatterns = [
    path("dashboard/", placeholder, name="dashboard"),
]
