"""Forward option-chain snapshot collector for TSETMC. Research only.

The collector never substitutes Last/Close for executable Bid/Ask.  A hosted
runner may record source unavailability, but only valid two-sided quotes are
appended to the immutable forward dataset.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

BASE = "https://cdn.tsetmc.com"
UA = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "Chrome/131.0 Safari/537.36 gold-etf-backtest-research"
    ),
    "Accept": "application/json,text/plain,*/*",
}
TEHRAN = ZoneInfo("Asia/Tehran")
FIELDS = [
    "snapshot_ts", "trade_date", "option_symbol", "option_name", "ins_code",
    "bid", "ask", "bid_size", "ask_size", "last", "close", "volume",
    "relative_spread", "quote_valid", "lotus_hint", "source",
]


class SourceUnavailableError(RuntimeError):
    """Raised when TSETMC cannot provide a usable option-chain response."""


def _get(path: str):
    try:
        r = requests.get(BASE + path, headers=UA, timeout=25)
        r.raise_for_status()
    except requests.RequestException as exc:
        raise SourceUnavailableError(f"TSETMC request failed: {type(exc).__name__}") from exc
    text = r.text
    if "General Error Detected" in text or "دسترسی شما" in text or "مسدود" in text:
        raise SourceUnavailableError("TSETMC access blocked")
    try:
        return r.json()
    except requests.JSONDecodeError as exc:
        raise SourceUnavailableError("TSETMC returned non-JSON content") from exc


def _market_watch_options():
    path = (
        "/api/ClosingPrice/GetMarketWatch?market=0&industrialGroup="
        "&paperTypes%5B0%5D=8&showTraded=false&withBestLimits=true"
        "&hEven=0&RefID=0"
    )
    data = _get(path)
    if isinstance(data, dict):
        rows = data.get("marketwatch") or data.get("marketWatch") or data.get("data") or []
    elif isinstance(data, list):
        rows = data
    else:
        rows = []
    if not rows:
        raise SourceUnavailableError("No option rows returned from market watch")
    return rows


def _num(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def _first_level(row: dict, ins_code: str):
    for key in ("bestLimits", "bestLimit", "bestlimits", "bl"):
        book = row.get(key)
        if isinstance(book, list) and book:
            return sorted(book, key=lambda x: x.get("number", 999))[0]
    try:
        data = _get(f"/api/BestLimits/{ins_code}")
        book = data.get("bestLimits", []) if isinstance(data, dict) else []
        return sorted(book, key=lambda x: x.get("number", 999))[0] if book else {}
    except SourceUnavailableError:
        return {}


def _field(row: dict, *names):
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return None


def _lotus_hint(symbol: str, name: str) -> bool:
    txt = f"{symbol} {name}".replace("ي", "ی").replace("ك", "ک")
    return ("لوتوس" in txt) or ("طلا" in txt)


def capture_rows(lotus_only: bool = True):
    now = datetime.now(TEHRAN)
    rows = []
    for row in _market_watch_options():
        symbol = str(_field(row, "lVal18AFC", "symbol", "l18") or "").strip()
        name = str(_field(row, "lVal30", "name", "l30") or "").strip()
        ins = str(_field(row, "insCode", "ins_code", "insCodeInstrument") or "").strip()
        if not ins:
            continue
        hint = _lotus_hint(symbol, name)
        if lotus_only and not hint:
            continue

        best = _first_level(row, ins)
        bid = _num(_field(best, "pMeDem", "pd", "bid"))
        ask = _num(_field(best, "pMeOf", "po", "ask"))
        bid_size = _num(_field(best, "qTitMeDem", "qd", "bid_size"))
        ask_size = _num(_field(best, "qTitMeOf", "qo", "ask_size"))
        last = _num(_field(row, "pDrCotVal", "pl", "last"))
        close = _num(_field(row, "pClosing", "pc", "close"))
        volume = _num(_field(row, "qTotTran5J", "tvol", "volume"))
        valid = bool(bid and ask and bid > 0 and ask > 0 and ask >= bid)
        spread = (ask - bid) / ((ask + bid) / 2.0) if valid else None
        rows.append({
            "snapshot_ts": now.isoformat(timespec="seconds"),
            "trade_date": now.date().isoformat(),
            "option_symbol": symbol,
            "option_name": name,
            "ins_code": ins,
            "bid": bid,
            "ask": ask,
            "bid_size": bid_size,
            "ask_size": ask_size,
            "last": last,
            "close": close,
            "volume": volume,
            "relative_spread": spread,
            "quote_valid": valid,
            "lotus_hint": hint,
            "source": "TSETMC",
        })
    return rows


def executable_rows(rows):
    """Return only genuine, crossed-book-safe two-sided quotes."""
    return [
        row
        for row in rows
        if row.get("quote_valid") is True or str(row.get("quote_valid")).lower() == "true"
    ]


def append_rows(rows, path: str):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    exists = p.exists() and p.stat().st_size > 0
    with p.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in FIELDS})


def write_status(path: str, payload: dict):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all-options", action="store_true")
    parser.add_argument("--out", default="data/option_snapshots_gated.csv")
    parser.add_argument("--status-out", default="results/option_snapshot_status.json")
    parser.add_argument(
        "--allow-source-unavailable",
        action="store_true",
        help="write a diagnostic status and exit zero; never writes fake quote rows",
    )
    args = parser.parse_args()
    timestamp = datetime.now(TEHRAN).isoformat(timespec="seconds")

    try:
        discovered = capture_rows(lotus_only=not args.all_options)
        valid = executable_rows(discovered)
        if not discovered:
            raise SourceUnavailableError("No Lotus/gold option contracts discovered")
        if not valid:
            raise SourceUnavailableError("Contracts discovered but no valid executable Bid/Ask")
    except SourceUnavailableError as exc:
        status = {
            "timestamp_tehran": timestamp,
            "status": "SOURCE_UNAVAILABLE",
            "source": "TSETMC",
            "reason": str(exc),
            "rows_appended": 0,
            "research_only": True,
        }
        write_status(args.status_out, status)
        print(json.dumps(status, ensure_ascii=False, indent=2))
        if args.allow_source_unavailable:
            return
        raise SystemExit(str(exc))

    append_rows(valid, args.out)
    status = {
        "timestamp_tehran": timestamp,
        "status": "CAPTURED",
        "source": "TSETMC",
        "contracts_discovered": len(discovered),
        "rows_appended": len(valid),
        "rejected_non_executable": len(discovered) - len(valid),
        "output": args.out,
        "rule": "Last/Close never substitute for Bid/Ask",
        "research_only": True,
    }
    write_status(args.status_out, status)
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
