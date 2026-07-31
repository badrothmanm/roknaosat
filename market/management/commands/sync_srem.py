"""
مزامنة بورصة وزارة العدل — للجدولة اليومية (cron / Celery).

  python manage.py sync_srem
"""
from django.core.management.base import BaseCommand

from market.tasks import run_fetch_and_store_srem_indices


class Command(BaseCommand):
    help = "جلب AreaStat من API البورصة ثم تحديث RealEstateIndex"

    def handle(self, *args, **options):
        n, m, err = run_fetch_and_store_srem_indices()
        if err:
            self.stderr.write(self.style.ERROR(f"SREM failed: {err}"))
            return
        if n == 0:
            self.stderr.write(self.style.WARNING("SREM: no AreaStat rows saved (check API / settings)."))
            return
        self.stdout.write(self.style.SUCCESS(f"SREM OK: AreaStat={n}, RealEstateIndex={m}"))
