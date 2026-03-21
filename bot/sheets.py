# bot/sheets.py
from __future__ import annotations

import json
import logging

import gspread

logger = logging.getLogger(__name__)

BALANCE_ID_ROW = 1
BALANCE_TRANSACTIONS_START_ROW = 7


class SheetsClient:
    def __init__(self, service_account_info: dict, sheet_id: str):
        gc = gspread.service_account_from_dict(service_account_info)
        spreadsheet = gc.open_by_key(sheet_id)
        self._pending = spreadsheet.worksheet("PENDING")
        self._main = spreadsheet.worksheet("PARIURI")
        self._flagged = spreadsheet.worksheet("FLAGGED")
        self._balance = spreadsheet.worksheet("BALANCE")

    def write_pending(
        self, date: str, ora: str, parior: str, meci: str, pariu: str, cota: str, miza: str
    ) -> None:
        self._pending.append_row(
            [date, ora, parior, meci, pariu, cota, miza],
            value_input_option="USER_ENTERED",
        )

    def write_flagged(
        self, date: str, ora: str, parior: str, meci: str, pariu: str, cota: str, miza: str, motiv: str
    ) -> None:
        self._flagged.append_row(
            [date, ora, parior, meci, pariu, cota, miza, motiv],
            value_input_option="USER_ENTERED",
        )

    def write_main(self, row: list[str]) -> None:
        self._main.append_row(row, value_input_option="USER_ENTERED")

    def get_all_pending(self) -> list[list[str]]:
        all_rows = self._pending.get_all_values()
        if len(all_rows) <= 1:
            return []
        return all_rows[1:]

    def clear_pending(self) -> None:
        all_rows = self._pending.get_all_values()
        if len(all_rows) <= 1:
            return
        self._pending.delete_rows(2, len(all_rows))

    def find_user_column(self, user_id: int) -> int | None:
        id_row = self._balance.row_values(BALANCE_ID_ROW)
        user_id_str = str(user_id)
        for i, cell_val in enumerate(id_row):
            if cell_val.strip() == user_id_str:
                return i + 1
        return None

    def append_balance_transaction(self, col: int, amount: float) -> None:
        col_values = self._balance.col_values(col)
        row = BALANCE_TRANSACTIONS_START_ROW
        for i in range(BALANCE_TRANSACTIONS_START_ROW - 1, len(col_values)):
            if col_values[i].strip() == "":
                row = i + 1
                break
        else:
            row = len(col_values) + 1
        self._balance.update_cell(row, col, amount)

    def find_column_by_name(self, parior_name: str) -> int | None:
        """Find a user's column by display name in BALANCE row 3."""
        name_row = self._balance.row_values(3)
        for i, name in enumerate(name_row):
            if name.strip().lower() == parior_name.strip().lower():
                return i + 1
        return None

    def get_recent_bets_for_duplicate_check(self) -> list[dict]:
        """Read recent PENDING + MAIN rows for duplicate detection."""
        rows = []
        for sheet in [self._pending, self._main]:
            all_rows = sheet.get_all_values()
            if len(all_rows) <= 1:
                continue
            for row in all_rows[1:]:
                if len(row) >= 7:
                    rows.append({
                        "date": row[0],
                        "parior": row[2],
                        "meci": row[3],
                        "pariu": row[4],
                        "total_odds": row[5],
                    })
        return rows

    def get_parior_name_for_user(self, user_id: int) -> str | None:
        """Get the display name from BALANCE row 3 for a user ID."""
        col = self.find_user_column(user_id)
        if col is None:
            return None
        name_row = self._balance.row_values(3)
        if col - 1 < len(name_row):
            return name_row[col - 1]
        return None
