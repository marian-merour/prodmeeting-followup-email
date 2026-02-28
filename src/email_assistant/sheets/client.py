"""Google Sheets client for reading artist contract data."""

from datetime import datetime
from typing import Optional

from googleapiclient.discovery import build


class SheetsClient:
    """Read artist contract data from a Google Sheet."""

    def __init__(self, credentials):
        self.service = build("sheets", "v4", credentials=credentials)

    def _format_date(self, date_str: str) -> str:
        """Reformat a date string to 'Mon D' (e.g. 'Feb 23')."""
        if not date_str:
            return date_str
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y"):
            try:
                dt = datetime.strptime(date_str, fmt)
                return f"{dt.strftime('%b')} {dt.day}"
            except ValueError:
                continue
        return date_str

    def _get_sheet_name(self, spreadsheet_id: str, gid: int) -> Optional[str]:
        """Find the tab name for a given gid."""
        meta = self.service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        for sheet in meta.get("sheets", []):
            if sheet["properties"]["sheetId"] == gid:
                return sheet["properties"]["title"]
        return None

    def get_contract_timeline(
        self,
        spreadsheet_id: str,
        gid: int,
        artist_name: str,
        name_row: int = 3,
        start_row: int = 10,
        end_row: int = 11,
    ) -> Optional[str]:
        """
        Find the artist's column (by name_row), read rows start_row and end_row.

        Returns "start – end" string, or just the start date if end is empty,
        or None if the artist isn't found / cells are empty.
        """
        sheet_name = self._get_sheet_name(spreadsheet_id, gid)
        if not sheet_name:
            return None

        result = self.service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=sheet_name,
        ).execute()
        rows = result.get("values", [])

        if len(rows) < max(name_row, start_row, end_row):
            return None

        # Find artist column (0-indexed, row 3 is index 2)
        header_row = rows[name_row - 1]
        col_idx = None
        for i, cell in enumerate(header_row):
            if artist_name.lower() in str(cell).lower():
                col_idx = i
                break
        if col_idx is None:
            return None

        def get_cell(row_idx: int) -> str:
            row = rows[row_idx - 1] if len(rows) >= row_idx else []
            return str(row[col_idx]).strip() if len(row) > col_idx else ""

        start = get_cell(start_row)
        end = get_cell(end_row)

        if start and end:
            return f"{self._format_date(start)} - {self._format_date(end)}"
        return self._format_date(start) or self._format_date(end) or None
