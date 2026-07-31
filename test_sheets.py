import os
import django
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from integrations.sheets_client import SheetsClient
from django.utils import timezone

client = SheetsClient(
    spreadsheet_id=getattr(settings, 'GSHEETS_SPREADSHEET_ID', None),
    service_account_file=getattr(settings, 'GSHEETS_SERVICE_ACCOUNT_FILE', "core/keys/crm-sheets.json"),
)

print(f"Spreadsheet ID: {client.spreadsheet_id}")
print(f"Service Account File: {getattr(settings, 'GSHEETS_SERVICE_ACCOUNT_FILE', 'core/keys/crm-sheets.json')}")

row = [timezone.now().strftime("%d/%m/%Y %H:%M:%S"), 'TEST WEB', '0500000000', 'sale', '', '100', '1', '1', '1', '1', '1000', '', 'sale', 'residential', 'Riyadh', 'Test District', '', 'Note', '', '', '']

try:
    client.append_row("عرض عقار", row)
    print("Test append to 'عرض عقار' successful!")
except Exception as e:
    print(f"Error: {e}")
