import time

from django.core.management.base import BaseCommand

from monitoring import rules
from monitoring.models import AnomalyFlag


class Command(BaseCommand):
    help = "Scan orders/fills against the anomaly rules and persist AnomalyFlag rows (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--loop", action="store_true", help="Keep re-running every --interval seconds."
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=10,
            help="Seconds between scans in --loop mode (default 10).",
        )

    def handle(self, *args, **options):
        if not options["loop"]:
            self._run_once()
            return

        interval = options["interval"]
        self.stdout.write(
            self.style.SUCCESS(f"Running detect_anomalies every {interval}s. Ctrl+C to stop.")
        )
        try:
            while True:
                self._run_once()
                time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Stopped."))

    def _run_once(self):
        created = 0
        for finder in rules.ALL_RULES:
            for candidate in finder():
                if self._already_flagged(candidate):
                    continue
                AnomalyFlag.objects.create(
                    flag_type=candidate.flag_type,
                    order=candidate.order,
                    desk=candidate.desk,
                    detail=candidate.detail,
                    severity=candidate.severity,
                )
                created += 1
        self.stdout.write(self.style.SUCCESS(f"detect_anomalies: {created} new flag(s) created."))

    @staticmethod
    def _already_flagged(candidate):
        qs = AnomalyFlag.objects.filter(flag_type=candidate.flag_type)
        if candidate.order is not None:
            return qs.filter(order=candidate.order).exists()
        # Desk-level flags (REJECT_SPIKE) have no order FK to key off, so
        # dedupe on the rendered detail text instead — it names the exact
        # triggering orders, so a genuinely new breach still gets flagged.
        return qs.filter(desk=candidate.desk, detail=candidate.detail).exists()
