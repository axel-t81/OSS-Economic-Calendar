"""Tests: site smoke tests, models, seed command, admin, and calendar views."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core import management
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from .models import Event, Indicator
from .templatetags.event_tags import fmt_value

SYDNEY = ZoneInfo("Australia/Sydney")


def sydney_datetime(year: int, month: int, day: int, hour: int, minute: int = 0):
    """Sydney-aware datetime — lets tests pin exact wall-clock times."""
    return datetime(year, month, day, hour, minute, tzinfo=SYDNEY)


class HomeViewTests(TestCase):
    def test_home_page_returns_200(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_home_page_renders_site_name(self) -> None:
        response = self.client.get("/")
        self.assertContains(response, "OSS Economic Calendar")

    def test_admin_login_reachable(self) -> None:
        response = self.client.get("/admin/login/")
        self.assertEqual(response.status_code, 200)


class IndicatorTests(TestCase):
    def test_slug_generated_and_stable(self) -> None:
        indicator = Indicator.objects.create(
            name="Consumer Price Index (YoY)",
            frequency=Indicator.Frequency.MONTHLY,
            measure=Indicator.Measure.YOY,
            unit="%",
            source=Indicator.Source.ABS,
            source_release="Monthly Consumer Price Index Indicator",
        )
        self.assertEqual(indicator.slug, "consumer-price-index-yoy")
        indicator.name = "Renamed Later"
        indicator.save()
        indicator.refresh_from_db()
        self.assertEqual(indicator.slug, "consumer-price-index-yoy")

    def test_duplicate_names_rejected(self) -> None:
        fields = {
            "frequency": Indicator.Frequency.MONTHLY,
            "measure": Indicator.Measure.LEVEL,
            "unit": "%",
            "source": Indicator.Source.ABS,
            "source_release": "Test Release",
        }
        Indicator.objects.create(name="Unemployment Rate", **fields)
        with self.assertRaises(IntegrityError):
            Indicator.objects.create(name="Unemployment Rate", **fields)


class EventTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.monthly = Indicator.objects.create(
            name="Unemployment Rate",
            frequency=Indicator.Frequency.MONTHLY,
            measure=Indicator.Measure.LEVEL,
            unit="%",
            source=Indicator.Source.ABS,
            source_release="Labour Force, Australia",
        )
        cls.quarterly = Indicator.objects.create(
            name="Gross Domestic Product (QoQ)",
            frequency=Indicator.Frequency.QUARTERLY,
            measure=Indicator.Measure.QOQ,
            unit="%",
            source=Indicator.Source.ABS,
            source_release="Australian National Accounts",
        )

    def test_unique_indicator_reference_period(self) -> None:
        Event.objects.create(
            indicator=self.monthly, reference_period="2026-10-01", release_at=timezone.now()
        )
        with self.assertRaises(IntegrityError):
            Event.objects.create(
                indicator=self.monthly, reference_period="2026-10-01", release_at=timezone.now()
            )

    def test_reference_period_label_monthly(self) -> None:
        event = Event.objects.create(
            indicator=self.monthly, reference_period=date(2026, 10, 1), release_at=timezone.now()
        )
        self.assertEqual(event.reference_period_label, "OCT 2026")

    def test_reference_period_label_quarterly(self) -> None:
        event = Event.objects.create(
            indicator=self.quarterly, reference_period=date(2026, 7, 1), release_at=timezone.now()
        )
        self.assertEqual(event.reference_period_label, "Q3 2026")

    def test_is_past(self) -> None:
        past = Event.objects.create(
            indicator=self.monthly,
            reference_period="2026-10-01",
            release_at=timezone.now() - timedelta(hours=1),
        )
        future = Event.objects.create(
            indicator=self.monthly,
            reference_period="2026-11-01",
            release_at=timezone.now() + timedelta(days=7),
        )
        self.assertTrue(past.is_past)
        self.assertFalse(future.is_past)

    def test_surprise(self) -> None:
        event = Event.objects.create(
            indicator=self.monthly,
            reference_period="2026-10-01",
            release_at=timezone.now(),
            actual=Decimal("4.200"),
            consensus=Decimal("4.000"),
        )
        self.assertEqual(event.surprise, Decimal("0.200"))

    def test_surprise_none_without_both_values(self) -> None:
        no_actual = Event.objects.create(
            indicator=self.monthly,
            reference_period="2026-10-01",
            release_at=timezone.now(),
            consensus=Decimal("4.000"),
        )
        self.assertIsNone(no_actual.surprise)


class SeedIndicatorsCommandTests(TestCase):
    def test_seed_is_idempotent_and_loads_catalogue(self) -> None:
        management.call_command("seed_indicators")
        self.assertEqual(Indicator.objects.count(), 51)
        management.call_command("seed_indicators")
        self.assertEqual(Indicator.objects.count(), 51)

    def test_seed_source_faithful_names(self) -> None:
        management.call_command("seed_indicators")
        cpi = Indicator.objects.get(name="Consumer Price Index (YoY)")
        self.assertEqual(cpi.source, Indicator.Source.ABS)
        self.assertEqual(cpi.standard_name, "CPI (YoY)")
        self.assertTrue(Indicator.objects.filter(name="Balance on Goods and Services").exists())
        self.assertTrue(Indicator.objects.filter(name="Cotality Home Value Index (MoM)").exists())

    def test_reseed_does_not_reactivate_retired(self) -> None:
        management.call_command("seed_indicators")
        indicator = Indicator.objects.get(name="Unemployment Rate")
        indicator.is_active = False
        indicator.save()
        management.call_command("seed_indicators")
        indicator.refresh_from_db()
        self.assertFalse(indicator.is_active)


class EventListViewTests(TestCase):
    """The home page: chronological list with tabs, filters, paging, htmx partials.

    Membership assertions go through response.context["page"] — the indicator
    dropdown lists every active indicator, so HTML string checks would lie.
    """

    def setUp(self) -> None:
        def indicator(name: str, source: str = Indicator.Source.ABS) -> Indicator:
            return Indicator.objects.create(
                name=name,
                frequency=Indicator.Frequency.MONTHLY,
                measure=Indicator.Measure.LEVEL,
                unit="%",
                source=source,
                source_release="Test Release",
            )

        self.abs_retail = indicator("Retail Trade (MoM)")
        self.abs_labour = indicator("Labour Force Unemployment Rate")
        self.abs_participation = indicator("Participation Rate")
        self.rba_cash_rate = indicator("Cash Rate Target", Indicator.Source.RBA)

        # Sydney-midnight boundary: the same split the view uses.
        self.today_mid = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        self.past_event = Event.objects.create(  # released yesterday evening
            indicator=self.abs_retail,
            reference_period=(self.today_mid - timedelta(days=35)).date(),
            release_at=self.today_mid - timedelta(hours=3),
            actual=Decimal("4.100"),
            consensus=Decimal("4.200"),
            previous=Decimal("4.000"),
        )
        self.today_released = Event.objects.create(  # published this morning
            indicator=self.abs_labour,
            reference_period=(self.today_mid - timedelta(days=34)).date(),
            release_at=self.today_mid + timedelta(hours=1),
            actual=Decimal("3.900"),
            consensus=Decimal("4.000"),
            previous=Decimal("4.100"),
        )
        self.today_upcoming = Event.objects.create(  # later today
            indicator=self.abs_participation,
            reference_period=(self.today_mid - timedelta(days=33)).date(),
            release_at=self.today_mid + timedelta(hours=23),
            consensus=Decimal("66.100"),
            previous=Decimal("65.900"),
        )
        self.tomorrow_event = Event.objects.create(
            indicator=self.rba_cash_rate,
            reference_period=(self.today_mid - timedelta(days=32)).date(),
            release_at=self.today_mid + timedelta(hours=25),
            consensus=Decimal("3.850"),
            previous=Decimal("3.600"),
        )
        # Pagination filler: several releases beyond tomorrow.
        self.extras = [
            Event.objects.create(
                indicator=self.abs_retail,
                reference_period=(self.today_mid - timedelta(days=20 - i)).date(),
                release_at=self.today_mid + timedelta(days=30 + i),
                consensus=Decimal("1.000"),
            )
            for i in range(3)
        ]

    def _pks(self, response) -> set:
        return set(response.context["page"].object_list.values_list("pk", flat=True))

    def test_default_tab_is_upcoming_including_today(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        pks = self._pks(response)
        self.assertIn(self.today_released.pk, pks)  # today, already released
        self.assertIn(self.today_upcoming.pk, pks)  # today, later today
        self.assertIn(self.tomorrow_event.pk, pks)
        self.assertNotIn(self.past_event.pk, pks)

    def test_past_tab(self) -> None:
        response = self.client.get("/", {"tab": "past"})
        pks = self._pks(response)
        self.assertIn(self.past_event.pk, pks)
        self.assertNotIn(self.today_released.pk, pks)
        self.assertNotIn(self.tomorrow_event.pk, pks)

    def test_all_tab(self) -> None:
        response = self.client.get("/", {"tab": "all"})
        pks = self._pks(response)
        for event in (
            self.past_event,
            self.today_released,
            self.today_upcoming,
            self.tomorrow_event,
        ):
            self.assertIn(event.pk, pks)

    def test_invalid_tab_falls_back_to_upcoming(self) -> None:
        response = self.client.get("/", {"tab": "nonsense"})
        pks = self._pks(response)
        self.assertIn(self.tomorrow_event.pk, pks)
        self.assertNotIn(self.past_event.pk, pks)

    def test_source_filter(self) -> None:
        response = self.client.get("/", {"tab": "all", "source": "rba"})
        pks = self._pks(response)
        self.assertIn(self.tomorrow_event.pk, pks)
        self.assertNotIn(self.today_released.pk, pks)

    def test_invalid_source_is_ignored(self) -> None:
        response = self.client.get("/", {"tab": "all", "source": "not-a-source"})
        pks = self._pks(response)
        self.assertIn(self.tomorrow_event.pk, pks)
        self.assertIn(self.today_released.pk, pks)

    def test_indicator_filter(self) -> None:
        response = self.client.get("/", {"tab": "all", "indicator": self.abs_participation.slug})
        self.assertEqual(self._pks(response), {self.today_upcoming.pk})

    def test_inactive_indicator_hidden(self) -> None:
        self.abs_retail.is_active = False
        self.abs_retail.save()
        response = self.client.get("/", {"tab": "all"})
        self.assertNotIn(self.past_event.pk, self._pks(response))

    def test_pagination(self) -> None:
        with mock.patch("events.views.PAGE_SIZE", 3):
            response = self.client.get("/", {"tab": "all"})
            self.assertEqual(len(response.context["page"].object_list), 3)
            page_one = self._pks(response)
            self.assertEqual(response.context["page"].paginator.num_pages, 3)

            response = self.client.get("/", {"tab": "all", "page": 3})
            page_three = self._pks(response)
            self.assertNotIn(self.past_event.pk, page_one)
            self.assertIn(self.past_event.pk, page_three)  # oldest on the last page

    def test_full_page_vs_htmx_partial(self) -> None:
        full = self.client.get("/")
        self.assertContains(full, 'class="site-nav"')
        self.assertContains(full, 'id="event-list"')

        partial = self.client.get("/", HTTP_HX_REQUEST="true")
        self.assertEqual(partial.status_code, 200)
        self.assertNotContains(partial, 'class="site-nav"')
        self.assertContains(partial, 'id="event-list"')

    def test_upcoming_rows_show_forecast_not_actual(self) -> None:
        response = self.client.get("/")
        self.assertContains(response, "3.85%")  # consensus
        self.assertContains(response, "3.6%")  # previous
        self.assertContains(response, 'class="pending"')  # actual placeholder
        # The yesterday release is not on this tab at all — its consensus
        # (unique to it) must be absent (today's released event legitimately
        # shows its actual: it IS on the Upcoming tab).
        self.assertNotContains(response, "4.2%")

    def test_past_rows_show_actual_and_signed_surprise(self) -> None:
        response = self.client.get("/", {"tab": "past"})
        self.assertContains(response, "4.1%")  # actual
        self.assertContains(response, "miss")  # below-consensus colour class
        self.assertContains(response, "-0.1% vs forecast")  # signed surprise

    def test_today_rows_highlighted(self) -> None:
        response = self.client.get("/")
        self.assertContains(response, "row-today")

    def test_empty_state_renders(self) -> None:
        response = self.client.get("/", {"tab": "past", "indicator": "no-such-slug"})
        self.assertContains(response, "No past releases match")


class MonthViewTests(TestCase):
    def setUp(self) -> None:
        self.cpi = Indicator.objects.create(
            name="Consumer Price Index (YoY)",
            frequency=Indicator.Frequency.MONTHLY,
            measure=Indicator.Measure.YOY,
            unit="%",
            source=Indicator.Source.ABS,
            source_release="Monthly Consumer Price Index Indicator",
        )
        # 00:30 Sydney on the 19th is 13:30 UTC on the 18th (AEDT, UTC+11):
        # the event must still land on the 19th in the grid.
        self.boundary_event = Event.objects.create(
            indicator=self.cpi,
            reference_period=date(2026, 10, 1),
            release_at=sydney_datetime(2026, 11, 19, 0, 30),
            consensus=Decimal("3.000"),
        )
        self.mid_month_event = Event.objects.create(
            indicator=self.cpi,
            reference_period=date(2026, 9, 1),
            release_at=sydney_datetime(2026, 11, 17, 11, 30),
            actual=Decimal("3.100"),
            consensus=Decimal("3.000"),
            previous=Decimal("3.200"),
        )

    def _get(self, **params):
        return self.client.get("/calendar/", params)

    def test_events_grouped_on_sydney_calendar_day(self) -> None:
        response = self._get(year=2026, month=11)
        by_day = response.context["events_by_day"]
        self.assertIn(19, by_day)
        self.assertIn(self.boundary_event.pk, [e.pk for e in by_day[19]])
        self.assertNotIn(18, by_day)

    def test_month_page_renders_values_inline(self) -> None:
        response = self._get(year=2026, month=11)
        self.assertContains(response, "November 2026")
        self.assertContains(response, "11:30")  # Sydney time
        # Chip values are unitless; the unit shows once per chip (v-unit).
        self.assertContains(response, "3.1")  # actual
        self.assertContains(response, "3.2")  # previous
        self.assertContains(response, "v-unit")

    def test_full_page_vs_htmx_partial(self) -> None:
        full = self._get(year=2026, month=11)
        self.assertContains(full, 'class="site-nav"')
        self.assertContains(full, 'id="month-grid"')

        partial = self.client.get("/calendar/", {"year": 2026, "month": 11}, HTTP_HX_REQUEST="true")
        self.assertEqual(partial.status_code, 200)
        self.assertNotContains(partial, 'class="site-nav"')
        self.assertContains(partial, 'id="month-grid"')

    def test_prev_and_next_month_links(self) -> None:
        response = self._get(year=2026, month=11)
        self.assertContains(response, "?year=2026&amp;month=10")
        self.assertContains(response, "?year=2026&amp;month=12")

    def test_invalid_params_return_404(self) -> None:
        self.assertEqual(self._get(year=2026, month=13).status_code, 404)
        self.assertEqual(self._get(year="abc").status_code, 404)
        self.assertEqual(self._get(year=1899, month=6).status_code, 404)

    def test_defaults_to_current_sydney_month(self) -> None:
        response = self._get()
        now = timezone.localtime()
        self.assertEqual(response.context["year"], now.year)
        self.assertEqual(response.context["month"], now.month)


class AboutViewTests(TestCase):
    def test_about_page_renders(self) -> None:
        response = self.client.get("/about/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Browse the calendar")
        self.assertContains(response, "No paywall, ever")


class FmtValueFilterTests(TestCase):
    def test_none_becomes_em_dash(self) -> None:
        self.assertEqual(fmt_value(None, "%"), "—")

    def test_trailing_zeros_stripped(self) -> None:
        self.assertEqual(fmt_value(Decimal("4.200"), "%"), "4.2%")

    def test_keeps_significant_decimals(self) -> None:
        self.assertEqual(fmt_value(Decimal("0.050")), "0.05")
        self.assertEqual(fmt_value(Decimal("3.000"), "%"), "3%")

    def test_negative_keeps_sign(self) -> None:
        self.assertEqual(fmt_value(Decimal("-0.100"), "%"), "-0.1%")

    def test_percent_units_glue(self) -> None:
        self.assertEqual(fmt_value(Decimal("0.300"), "pp"), "0.3pp")

    def test_wordy_units_get_a_space(self) -> None:
        self.assertEqual(fmt_value(Decimal("3500.000"), "AUD m"), "3500 AUD m")
        self.assertEqual(fmt_value(Decimal("51.000"), "index"), "51 index")


class EventAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = get_user_model().objects.create_superuser(
            username="admin", email="admin@example.com", password="test-pass-123"
        )
        cls.indicator = Indicator.objects.create(
            name="Unemployment Rate",
            frequency=Indicator.Frequency.MONTHLY,
            measure=Indicator.Measure.LEVEL,
            unit="%",
            source=Indicator.Source.ABS,
            source_release="Labour Force, Australia",
        )

    def setUp(self) -> None:
        self.client.force_login(self.user)

    def test_changelist_pages_render(self) -> None:
        self.assertEqual(self.client.get("/admin/events/indicator/").status_code, 200)
        self.assertEqual(self.client.get("/admin/events/event/").status_code, 200)

    def test_add_pages_render(self) -> None:
        self.assertEqual(self.client.get("/admin/events/indicator/add/").status_code, 200)
        self.assertEqual(self.client.get("/admin/events/event/add/").status_code, 200)

    def test_previous_autofilled_from_last_actual(self) -> None:
        Event.objects.create(
            indicator=self.indicator,
            reference_period="2026-09-01",
            release_at=timezone.now() - timedelta(days=30),
            actual=Decimal("4.100"),
        )
        response = self.client.post(
            "/admin/events/event/add/",
            {
                "indicator": str(self.indicator.pk),
                "reference_period": "2026-10-01",
                "release_at_0": "2026-11-19",
                "release_at_1": "11:30:00",
                "actual": "4.3",
                "previous": "",
                "consensus": "4.2",
                "source_url": "",
                "notes": "",
                "save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302)
        event = Event.objects.get(indicator=self.indicator, reference_period="2026-10-01")
        self.assertEqual(event.previous, Decimal("4.100"))

    def test_typed_previous_wins(self) -> None:
        Event.objects.create(
            indicator=self.indicator,
            reference_period="2026-09-01",
            release_at=timezone.now() - timedelta(days=30),
            actual=Decimal("4.100"),
        )
        response = self.client.post(
            "/admin/events/event/add/",
            {
                "indicator": str(self.indicator.pk),
                "reference_period": "2026-10-01",
                "release_at_0": "2026-11-19",
                "release_at_1": "11:30:00",
                "actual": "4.3",
                "previous": "4.150",  # source published a revision
                "consensus": "4.2",
                "source_url": "",
                "notes": "",
                "save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302)
        event = Event.objects.get(indicator=self.indicator, reference_period="2026-10-01")
        self.assertEqual(event.previous, Decimal("4.150"))

    def test_previous_autofill_excludes_self_when_period_moved_forward(self) -> None:
        # Regression (Cursor BugBot): editing an event and moving its reference
        # period to a later date while `previous` is blank must not copy the
        # event's own actual into previous — the DB row still carries the old,
        # earlier date and would otherwise match the autofill query.
        event = Event.objects.create(
            indicator=self.indicator,
            reference_period="2026-09-01",
            release_at=timezone.now() - timedelta(days=30),
            actual=Decimal("4.100"),
            previous=Decimal("4.000"),
        )
        response = self.client.post(
            f"/admin/events/event/{event.pk}/change/",
            {
                "indicator": str(self.indicator.pk),
                "reference_period": "2026-10-01",
                "release_at_0": "2026-11-19",
                "release_at_1": "11:30:00",
                "actual": "4.1",
                "previous": "",
                "consensus": "",
                "source_url": "",
                "notes": "",
                "save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertIsNone(event.previous)
