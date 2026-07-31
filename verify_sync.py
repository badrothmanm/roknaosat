import os
import django
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from listings.models import Property
from listings.services.sheets_sync import _do_sync_property

def verify_sync():
    # Get the last property
    prop = Property.objects.order_by('-created_at').first()
    if not prop:
        print("No properties found to sync.")
        return
    
    print(f"Syncing Property #{prop.pk} ({prop.listing_id}) to Google Sheets...")
    try:
        _do_sync_property(prop.pk)
        print("Sync completed! Please check if it appeared in the 'العقارات المعروضة ' tab.")
    except Exception as e:
        print(f"Sync failed: {e}")

if __name__ == "__main__":
    verify_sync()
