"""Tests: site smoke tests, models, seed command, and admin behaviour."""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import management
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from .models import Event, Indicator


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
