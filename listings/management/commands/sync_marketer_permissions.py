"""
مزامنة صلاحيات مجموعة «المسوقين» مع القائمة المعرفة في listings.marketer_permissions.

تشغيل على السيرفر بعد النشر:
    python manage.py sync_marketer_permissions
"""
from django.core.management.base import BaseCommand

from listings.marketer_permissions import sync_marketer_group_permissions


class Command(BaseCommand):
    help = "مزامنة صلاحيات مجموعة المسوقين (الروابط السريعة من لوحة إحصائياتي)"

    def handle(self, *args, **options):
        result = sync_marketer_group_permissions()
        self.stdout.write(
            self.style.SUCCESS(
                f"تم ضبط مجموعة «{result['group']}» — {result['count']} صلاحية على listings."
            )
        )
        if result["missing"]:
            self.stdout.write(
                self.style.WARNING(
                    "تحذير: الصلاحيات التالية غير موجودة في قاعدة البيانات (تحقق من migrations): "
                    + ", ".join(result["missing"])
                )
            )
