from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def home(request: HttpRequest) -> HttpResponse:
    """Landing page — a temporary placeholder until the calendar UI is built."""
    return render(request, "events/home.html")
