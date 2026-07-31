import os
import django
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from integrations.sheets_client import SheetsClient

def check_tabs():
    spreadsheet_id = getattr(settings, 'GSHEETS_SPREADSHEET_ID', None)
    service_account_file = getattr(settings, 'GSHEETS_SERVICE_ACCOUNT_FILE', "core/keys/crm-sheets.json")
    
    print(f"Checking Spreadsheet: {spreadsheet_id}")
    
    client = SheetsClient(spreadsheet_id, service_account_file)
    spreadsheet = client.service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    
    sheets = spreadsheet.get('sheets', [])
    print("\nAvailable Tabs:")
    for sheet in sheets:
        properties = sheet.get('properties', {})
        print(f"- {repr(properties.get('title'))} (ID: {properties.get('sheetId')})")

if __name__ == "__main__":
    try:
        check_tabs()
    except Exception as e:
        print(f"Error: {e}")
