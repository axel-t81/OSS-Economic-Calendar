"""Admin for the indicator catalogue and release events.

The Event changelist is the day-to-day data-entry surface: create the event
ahead of release with consensus, then record the actual on the day.
"""

from django.contrib import admin

from .models import Event, Indicator


@admin.register(Indicator)
class IndicatorAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "standard_name",
        "country",
        "frequency",
        "measure",
        "unit",
        "source",
        "source_release",
        "is_active",
    )
    list_filter = ("country", "frequency", "source", "is_active")
    search_fields = ("name", "standard_name", "source_release")


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        "indicator",
        "reference_period_label",
        "release_at",
        "actual",
        "previous",
        "consensus",
        "is_past",
    )
    list_select_related = ("indicator",)
    list_filter = ("indicator__country", "indicator__frequency", "indicator__source")
    search_fields = ("indicator__name",)
    date_hierarchy = "release_at"
    autocomplete_fields = ["indicator"]
    readonly_fields = ("created_at", "updated_at")

    def save_model(self, request, obj, form, change):
        """Cold-start helper: leave `previous` blank and it is filled from the
        same indicator's most recent earlier recorded actual. A typed value
        always wins, so a revised "previous" from the source can be entered
        deliberately."""
        if obj.previous is None and obj.indicator_id:
            latest = (
                Event.objects.filter(
                    indicator_id=obj.indicator_id,
                    reference_period__lt=obj.reference_period,
                    actual__isnull=False,
                )
                .order_by("-reference_period")
                .first()
            )
            if latest is not None:
                obj.previous = latest.actual
        super().save_model(request, obj, form, change)
