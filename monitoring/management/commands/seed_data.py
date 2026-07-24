from django.core.management.base import BaseCommand

from monitoring.constants import DESKS, TRADER_NAMES
from monitoring.models import Trader


class Command(BaseCommand):
    help = "Seed the database with a fixed set of traders spread across desks."

    def handle(self, *args, **options):
        created_count = 0
        for i, name in enumerate(TRADER_NAMES):
            trader_id = f"TR-{i + 1:03d}"
            desk = DESKS[i % len(DESKS)]
            _, created = Trader.objects.get_or_create(
                trader_id=trader_id,
                defaults={"name": name, "desk": desk},
            )
            if created:
                created_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed complete: {created_count} trader(s) created "
                f"({Trader.objects.count()} total across {len(DESKS)} desks)."
            )
        )
