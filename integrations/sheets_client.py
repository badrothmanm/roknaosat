from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import logging

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

class SheetsClient:
    def __init__(self, spreadsheet_id: str, service_account_file: str):
        creds = Credentials.from_service_account_file(service_account_file, scopes=SCOPES)
        self.service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        self.spreadsheet_id = spreadsheet_id

    def append_row(self, tab_name: str, row_data: list, range_a1: str = None) -> None:
        try:
            logger.info(f"Appending row to Sheets tab: {tab_name} | Columns: {len(row_data)} | Preview: {row_data[:3]}...")
            
            # Use provided range or default to entire tab to avoid column mismatch errors
            range_name = f"'{tab_name}'!{range_a1}" if range_a1 else f"'{tab_name}'"

            self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": [row_data]},
            ).execute()
            
            logger.info("Successfully appended row to Google Sheets.")
        except Exception as e:
            logger.exception(f"Failed to append row to Google Sheets tab '{tab_name}'")
            raise e
