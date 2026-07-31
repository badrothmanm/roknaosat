"""
تشغيل من جذر المشروع (بعد تفعيل البيئة الافتراضية):

    python manage.py shell < scripts/setup_permissions.py

أو مباشرة:

    python manage.py sync_marketer_permissions
"""
import os
import sys
import django

# السماح بالتشغيل كسكربت مستقل
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
    django.setup()

from listings.marketer_permissions import sync_marketer_group_permissions


def setup_marketer_group():
    result = sync_marketer_group_permissions()
    print(f"SUCCESS: Group «{result['group']}» — {result['count']} listings permissions set.")
    if result["missing"]:
        print(f"WARNING: Missing codenames (run migrations?): {', '.join(result['missing'])}")


if __name__ == "__main__":
    setup_marketer_group()
