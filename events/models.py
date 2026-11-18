"""Core domain models: Indicator (catalogue) and Event (one release period)."""

from decimal import Decimal

from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class Indicator(models.Model):
    """A named economic data series that is tracked on the calendar.

    One row per series exactly as it should be displayed — QoQ and YoY views of the
    same statistical release are separate indicators. The parent release that a
    series belongs to is named in ``source_release`` (e.g. "Labour Force, Australia").
    """

    class Frequency(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        QUARTERLY = "quarterly", "Quarterly"

    class Measure(models.TextChoices):
        MOM = "mom", "vs previous month"
        QOQ = "qoq", "vs previous quarter"
        YOY = "yoy", "vs same period last year"
        LEVEL = "level", "Level (index or value)"

    class Source(models.TextChoices):
        ABS = "abs", "Australian Bureau of Statistics"
        RBA = "rba", "Reserve Bank of Australia"
        WESTPAC_MI = "westpac_mi", "Westpac-Melbourne Institute"
        SP_GLOBAL = "sp_global", "S&P Global"
        TD_MI = "td_mi", "TD Securities-Melbourne Institute"
        AI_GROUP = "ai_group", "Ai Group"
        COTALITY = "cotality", "Cotality"

    name = models.CharField(
        max_length=200,
        unique=True,
        help_text="Source-faithful label for this series, e.g. 'Consumer Price Index (YoY)'.",
    )
    slug = models.SlugField(max_length=220, unique=True, editable=False)
    standard_name = models.CharField(
        max_length=200,
        blank=True,
        help_text=(
            "Generic, country-agnostic concept (e.g. 'CPI (YoY)') used to compare "
            "indicators across countries once non-AU calendars exist."
        ),
    )
    country = models.CharField(
        max_length=2,
        default="AU",
        help_text="ISO 3166-1 alpha-2 country code.",
    )
    frequency = models.CharField(max_length=12, choices=Frequency.choices)
    measure = models.CharField(max_length=6, choices=Measure.choices)
    unit = models.CharField(
        max_length=16,
        help_text="Display unit for values, e.g. '%', 'k persons', 'index', 'AUD m', 'pp'.",
    )
    source = models.CharField(max_length=16, choices=Source.choices)
    source_release = models.CharField(
        max_length=200,
        help_text="Parent statistical release, e.g. 'Labour Force, Australia'.",
    )
    source_url = models.URLField(blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(
        default=True,
        help_text="Untick to retire an indicator without deleting its event history.",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs) -> None:
        # Slugs are generated once and then kept stable, so renaming an indicator
        # later does not break any URLs that reference it.
        if not self.slug:
            base = slugify(self.name) or "indicator"
            slug = base
            suffix = 2
            while Indicator.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{suffix}"
                suffix += 1
            self.slug = slug
        super().save(*args, **kwargs)


class Event(models.Model):
    """One release period of an indicator: the calendar's core record.

    Lifecycle: created ahead of release with consensus (and, during cold-start,
    a manually entered previous), then updated with the actual once published.

    Two dates, deliberately separate:
      - ``reference_period`` — the window the data describes (first day of the
        reference month/quarter; e.g. Q3 GDP is 2026-07-01).
      - ``release_at`` — when the source actually publishes (e.g. early December,
        11:30am Sydney). The past/future split and the daily digest key off this.
    """

    indicator = models.ForeignKey(Indicator, on_delete=models.PROTECT, related_name="events")
    reference_period = models.DateField(
        help_text="First day of the reference month/quarter that the data describes."
    )
    release_at = models.DateTimeField(help_text="Scheduled/actual publication time (Sydney).")
    actual = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    previous = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    consensus = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    source_url = models.URLField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-release_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["indicator", "reference_period"],
                name="unique_indicator_reference_period",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.indicator.name} - {self.reference_period_label}"

    @property
    def is_past(self) -> bool:
        return timezone.now() >= self.release_at

    @property
    def surprise(self) -> Decimal | None:
        """Actual minus consensus; None until both are recorded."""
        if self.actual is None or self.consensus is None:
            return None
        return self.actual - self.consensus

    @property
    def reference_period_label(self) -> str:
        """Display label for the reference window: 'OCT 2026' or 'Q3 2026'."""
        if self.indicator.frequency == Indicator.Frequency.QUARTERLY:
            quarter = (self.reference_period.month - 1) // 3 + 1
            return f"Q{quarter} {self.reference_period.year}"
        return self.reference_period.strftime("%b %Y").upper()
