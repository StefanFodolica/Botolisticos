# tests/test_sheets.py
from unittest.mock import MagicMock, patch, call
from datetime import datetime
from bot.sheets import SheetsClient


def _make_mock_client():
    """Create a SheetsClient with mocked gspread."""
    with patch("bot.sheets.gspread.service_account_from_dict") as mock_sa:
        mock_gc = MagicMock()
        mock_sa.return_value = mock_gc
        mock_spreadsheet = MagicMock()
        mock_gc.open_by_key.return_value = mock_spreadsheet

        mock_pending = MagicMock()
        mock_main = MagicMock()
        mock_flagged = MagicMock()
        mock_balance = MagicMock()

        def get_worksheet(name):
            return {
                "PENDING": mock_pending,
                "MAIN": mock_main,
                "FLAGGED": mock_flagged,
                "BALANCE": mock_balance,
            }[name]

        mock_spreadsheet.worksheet = get_worksheet

        client = SheetsClient(
            service_account_info={"type": "service_account"},
            sheet_id="test-sheet-id",
        )
        return client, mock_pending, mock_main, mock_flagged, mock_balance


def test_write_to_pending():
    client, mock_pending, _, _, _ = _make_mock_client()
    client.write_pending(
        date="20.03.2026",
        ora="14:32",
        parior="Georo",
        meci="Dinamo - FC Arges",
        pariu="Karamoko 3+",
        cota="4.10",
        miza="50.00 RON",
    )
    mock_pending.append_row.assert_called_once_with(
        ["20.03.2026", "14:32", "Georo", "Dinamo - FC Arges", "Karamoko 3+", "4.10", "50.00 RON"],
        value_input_option="USER_ENTERED",
    )


def test_write_to_flagged():
    client, _, _, mock_flagged, _ = _make_mock_client()
    client.write_flagged(
        date="20.03.2026",
        ora="14:32",
        parior="Georo",
        meci="Dinamo - FC Arges",
        pariu="Karamoko 3+",
        cota="4.10",
        miza="50.00 RON",
        motiv="odds mismatch",
    )
    mock_flagged.append_row.assert_called_once_with(
        ["20.03.2026", "14:32", "Georo", "Dinamo - FC Arges", "Karamoko 3+", "4.10", "50.00 RON", "odds mismatch"],
        value_input_option="USER_ENTERED",
    )


def test_get_all_pending():
    client, mock_pending, _, _, _ = _make_mock_client()
    mock_pending.get_all_values.return_value = [
        ["DATA", "ORA", "PARIOR", "Meci", "PARIU", "COTA", "MIZA"],
        ["20.03.2026", "14:32", "Georo", "Dinamo - FC Arges", "Karamoko 3+", "4.10", "50.00 RON"],
    ]
    rows = client.get_all_pending()
    assert len(rows) == 1
    assert rows[0] == ["20.03.2026", "14:32", "Georo", "Dinamo - FC Arges", "Karamoko 3+", "4.10", "50.00 RON"]


def test_approve_moves_to_main_and_clears():
    client, mock_pending, mock_main, _, _ = _make_mock_client()
    mock_pending.get_all_values.return_value = [
        ["DATA", "ORA", "PARIOR", "Meci", "PARIU", "COTA", "MIZA"],
        ["20.03.2026", "14:32", "Georo", "Match", "Bet", "4.10", "50.00 RON"],
        ["20.03.2026", "15:00", "Daris", "Match2", "Bet2", "2.00", "25.00 RON"],
    ]

    rows = client.get_all_pending()
    for row in rows:
        client.write_main(row)

    assert mock_main.append_row.call_count == 2


def test_clear_pending():
    client, mock_pending, _, _, _ = _make_mock_client()
    mock_pending.get_all_values.return_value = [
        ["DATA", "ORA", "PARIOR", "Meci", "PARIU", "COTA", "MIZA"],
        ["20.03.2026", "14:32", "Georo", "Match", "Bet", "4.10", "50.00 RON"],
    ]
    client.clear_pending()
    mock_pending.delete_rows.assert_called_once_with(2, 2)


def test_find_user_column_in_balance():
    client, _, _, _, mock_balance = _make_mock_client()
    mock_balance.row_values.return_value = ["", "111", "222", "333"]
    col = client.find_user_column(user_id=222)
    assert col == 3


def test_find_user_column_not_found():
    client, _, _, _, mock_balance = _make_mock_client()
    mock_balance.row_values.return_value = ["", "111", "222"]
    col = client.find_user_column(user_id=999)
    assert col is None


def test_append_balance_transaction():
    client, _, _, _, mock_balance = _make_mock_client()
    mock_balance.row_values.return_value = ["", "111", "222"]
    mock_balance.col_values.return_value = ["111", "", "Daris", "-928", "0", "TRANZACTII", "-50", "-100", ""]
    client.append_balance_transaction(col=2, amount=-25.0)
    mock_balance.update_cell.assert_called_once_with(9, 2, -25.0)
