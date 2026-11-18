from django.urls import path

from . import views

app_name = "events"

urlpatterns = [
    path("", views.event_list, name="event_list"),
    path("calendar/", views.month_view, name="month"),
    path("about/", views.about, name="about"),
]
