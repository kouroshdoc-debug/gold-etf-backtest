from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from option_snapshot_capture import executable_rows


def test_executable_rows_rejects_non_bidask_rows():
    rows = [
        {"option_symbol": "valid", "bid": 100.0, "ask": 110.0, "quote_valid": True},
        {"option_symbol": "last-only", "last": 105.0, "quote_valid": False},
        {"option_symbol": "crossed", "bid": 120.0, "ask": 110.0, "quote_valid": False},
    ]
    assert [row["option_symbol"] for row in executable_rows(rows)] == ["valid"]


def test_executable_rows_does_not_trust_truthy_strings():
    rows = [{"option_symbol": "bad", "quote_valid": "False"}]
    assert executable_rows(rows) == []
