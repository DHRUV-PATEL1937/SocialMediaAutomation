from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from googleapiclient.discovery import build


REQUIRED_COLUMNS = ["filename", "caption", "status", "posted_at", "platform_ids"]
OPTIONAL_COLUMNS = ["title"]
SHEET_RANGE = "A:Z"


@dataclass
class SheetRow:
    row_number: int
    values: dict[str, str]

    @property
    def filename(self) -> str:
        return self.values.get("filename", "").strip()

    @property
    def caption(self) -> str:
        return self.values.get("caption", "").strip()

    @property
    def status(self) -> str:
        return self.values.get("status", "pending").strip().lower() or "pending"

    @property
    def title(self) -> str:
        return self.values.get("title", "").strip()

    @property
    def posted_at(self) -> str:
        return self.values.get("posted_at", "").strip()

    @property
    def platform_ids(self) -> str:
        return self.values.get("platform_ids", "").strip()


class SheetsClient:
    def __init__(self, credentials: Any, spreadsheet_id: str) -> None:
        self.spreadsheet_id = spreadsheet_id
        self.service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
        self._headers: list[str] | None = None

    def read_rows(self) -> list[SheetRow]:
        result = (
            self.service.spreadsheets()
            .values()
            .get(spreadsheetId=self.spreadsheet_id, range=SHEET_RANGE)
            .execute()
        )
        values = result.get("values", [])
        if not values:
            raise RuntimeError("The Google Sheet is empty. Add the required header row first.")

        headers = [str(header).strip() for header in values[0]]
        missing = [column for column in REQUIRED_COLUMNS if column not in headers]
        if missing:
            raise RuntimeError(f"Google Sheet is missing required columns: {', '.join(missing)}")

        self._headers = headers
        rows: list[SheetRow] = []
        for index, row_values in enumerate(values[1:], start=2):
            row = {
                header: str(row_values[i]).strip() if i < len(row_values) else ""
                for i, header in enumerate(headers)
            }
            if row.get("filename"):
                rows.append(SheetRow(row_number=index, values=row))
        return rows

    def update_post_result(
        self,
        row: SheetRow,
        status: str,
        posted_at: datetime | None,
        platform_ids: str,
    ) -> None:
        updates: dict[str, str] = {
            "status": status,
            "platform_ids": platform_ids,
        }
        if posted_at:
            updates["posted_at"] = posted_at.isoformat()
        self.update_cells(row.row_number, updates)

    def update_cells(self, row_number: int, updates: dict[str, str]) -> None:
        headers = self._headers
        if headers is None:
            self.read_rows()
            headers = self._headers
        assert headers is not None

        data = []
        for column_name, value in updates.items():
            if column_name not in headers:
                raise RuntimeError(f"Cannot update unknown sheet column: {column_name}")
            column_letter = _column_letter(headers.index(column_name) + 1)
            data.append({"range": f"{column_letter}{row_number}", "values": [[value]]})

        (
            self.service.spreadsheets()
            .values()
            .batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"valueInputOption": "USER_ENTERED", "data": data},
            )
            .execute()
        )


def _column_letter(index: int) -> str:
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters
