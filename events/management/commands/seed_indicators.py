"""Idempotently load the indicator catalogue from events.seed_data."""

from django.core.management.base import BaseCommand

from events.models import Indicator
from events.seed_data import INDICATORS


class Command(BaseCommand):
    help = "Load or refresh the indicator catalogue. Safe to run repeatedly."

    def handle(self, *args, **options) -> None:
        created = 0
        updated = 0
        for row in INDICATORS:
            defaults = {key: value for key, value in row.items() if key != "name"}
            indicator, was_created = Indicator.objects.get_or_create(
                name=row["name"], defaults=defaults
            )
            if was_created:
                created += 1
                continue
            # Refresh metadata for existing rows, but never touch is_active:
            # retiring an indicator is a maintainer decision that reseeding
            # must not undo.
            changed = False
            for field, value in defaults.items():
                if getattr(indicator, field) != value:
                    setattr(indicator, field, value)
                    changed = True
            if changed:
                indicator.save(update_fields=list(defaults))
                updated += 1

        total = Indicator.objects.count()
        self.stdout.write(
            self.style.SUCCESS(f"Indicators: {created} created, {updated} updated, {total} total.")
        )
