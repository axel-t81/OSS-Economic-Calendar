"""Public calendar views: chronological list, month grid, and about."""

import calendar
import itertools
from datetime import datetime
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from .models import Event, Indicator

PAGE_SIZE = 50
TAB_CHOICES = ("upcoming", "past", "all")
MIN_YEAR = 1900
MAX_YEAR = 2100


def _start_of_today_sydney() -> datetime:
    """Sydney-midnight boundary for the upcoming/past tab split (aware).

    "Upcoming" deliberately includes the whole of today (Sydney) so that
    releases already published this morning still surface in the default view.
    """
    now = timezone.localtime()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def event_list(request: HttpRequest) -> HttpResponse:
    """Home page: chronological list with upcoming/past/all tabs and filters.

    htmx requests (HX-Request header) get just the swappable ``#event-list``
    region; everything else renders the full page around it.
    """
    tab = request.GET.get("tab", "upcoming")
    if tab not in TAB_CHOICES:
        tab = "upcoming"
    source = request.GET.get("source", "")
    if source not in Indicator.Source.values:
        source = ""
    indicator_slug = request.GET.get("indicator", "")
    # A stale indicator must not silently AND against an explicit source: if the
    # source changed while an indicator was selected (or an old bookmark carries
    # both), the combined filter would empty the calendar while the form shows
    # "All indicators". Drop the indicator when its source conflicts.
    if indicator_slug and source:
        indicator_source = (
            Indicator.objects.filter(slug=indicator_slug).values_list("source", flat=True).first()
        )
        if indicator_source != source:
            indicator_slug = ""

    events = Event.objects.select_related("indicator").filter(indicator__is_active=True)
    if source:
        events = events.filter(indicator__source=source)
    if indicator_slug:
        events = events.filter(indicator__slug=indicator_slug)

    start_of_today = _start_of_today_sydney()
    if tab == "upcoming":
        events = events.filter(release_at__gte=start_of_today).order_by("release_at")
    elif tab == "past":
        events = events.filter(release_at__lt=start_of_today).order_by("-release_at")
    else:  # all — newest first, matching the commercial-calendar convention
        events = events.order_by("-release_at")

    paginator = Paginator(events, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))

    # Indicator dropdown options, grouped by source. When a source filter is
    # active the options narrow to that source so the two selects stay coherent.
    indicator_qs = Indicator.objects.filter(is_active=True).order_by("source", "name")
    if source:
        indicator_qs = indicator_qs.filter(source=source)
    indicator_groups = [
        (Indicator.Source(code).label, list(group))
        for code, group in itertools.groupby(indicator_qs, key=lambda ind: ind.source)
    ]

    # Non-tab query params, kept when switching tabs or pages.
    extra = {k: v for k, v in (("source", source), ("indicator", indicator_slug)) if v}

    context = {
        "tab": tab,
        "tabs": TAB_CHOICES,
        "source": source,
        "source_choices": Indicator.Source.choices,
        "indicator": indicator_slug,
        "indicator_groups": indicator_groups,
        "qs_extra": urlencode(extra),
        "page": page,
        "today": start_of_today.date().isoformat(),
    }
    if request.headers.get("HX-Request") == "true":
        return render(request, "events/partials/event_list_region.html", context)
    return render(request, "events/event_list.html", context)


def _month_param(raw: str | None, default: int) -> int:
    """Parse ?year= / ?month=; missing means "current", garbage is a 404."""
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        raise Http404("Invalid year or month.") from None


def month_view(request: HttpRequest) -> HttpResponse:
    """Month grid: one cell per day, every event rendered inline with values."""
    now_sydney = timezone.localtime()
    year = _month_param(request.GET.get("year"), now_sydney.year)
    month = _month_param(request.GET.get("month"), now_sydney.month)
    if not MIN_YEAR <= year <= MAX_YEAR or not 1 <= month <= 12:
        raise Http404("Year or month out of range.")

    tz = timezone.get_current_timezone()  # Australia/Sydney
    start = datetime(year, month, 1, tzinfo=tz)
    end = (
        datetime(year + 1, 1, 1, tzinfo=tz)
        if month == 12
        else datetime(year, month + 1, 1, tzinfo=tz)
    )
    month_events = (
        Event.objects.select_related("indicator")
        .filter(indicator__is_active=True, release_at__gte=start, release_at__lt=end)
        .order_by("release_at")
    )
    # Group on the Sydney calendar day, so a 00:30 Sydney release stored as
    # 13:30 UTC the previous day still lands on the right date.
    events_by_day: dict[int, list] = {}
    for event in month_events:
        events_by_day.setdefault(timezone.localtime(event.release_at).day, []).append(event)

    # Cells are pre-joined with their events because Django templates cannot
    # do dynamic dict lookups (``events_by_day.day`` would be a literal key).
    weeks = [
        [{"day": day, "events": events_by_day.get(day, []) if day else []} for day in week]
        for week in calendar.monthcalendar(year, month)  # Monday-first, 0 = padding
    ]

    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)

    context = {
        "year": year,
        "month": month,
        "month_name": calendar.month_name[month],
        "weeks": weeks,
        "events_by_day": events_by_day,
        "today": {
            "year": now_sydney.year,
            "month": now_sydney.month,
            "day": now_sydney.day,
        },
        "prev": {
            "year": prev_year,
            "month": prev_month,
            "label": calendar.month_name[prev_month],
        },
        "next": {
            "year": next_year,
            "month": next_month,
            "label": calendar.month_name[next_month],
        },
    }
    if request.headers.get("HX-Request") == "true":
        return render(request, "events/partials/month_grid.html", context)
    return render(request, "events/month.html", context)


def about(request: HttpRequest) -> HttpResponse:
    """Project landing content: what this is, and where the data comes from."""
    return render(request, "events/about.html")
