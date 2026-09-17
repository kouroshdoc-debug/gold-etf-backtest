"""Forward option-chain snapshot collector for TSETMC. Research only.

Design goals:
- bulk-discover active option contracts from market watch (paper type 8)
- keep executable Bid/Ask only; never substitute Last/Close for quotes
- timestamp in Asia/Tehran
- append snapshots so forward evidence is immutable/auditable
- fail closed when TSETMC is blocked or quote fields are invalid
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


def _get(path: str):
    r = requests.get(BASE + path, headers=UA, timeout=25)
    r.raise_for_status()
    text = r.text
    if "General Error Detected" in text or "دسترسی شما" in text or "مسدود" in text:
        raise RuntimeError("TSETMC access blocked")
    return r.json()


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
        raise RuntimeError("No option rows returned from market watch")
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
    # Some market-watch responses omit nested depth despite withBestLimits=true.
    # Fetch only the target contract's current book as a controlled fallback.
    try:
        data = _get(f"/api/BestLimits/{ins_code}")
        book = data.get("bestLimits", []) if isinstance(data, dict) else []
        return sorted(book, key=lambda x: x.get("number", 999))[0] if book else {}
    except Exception:
        return {}


def _field(row: dict, *names):
    for n in names:
        if n in row and row[n] not in (None, ""):
            return row[n]
    return None


def _lotus_hint(symbol: str, name: str) -> bool:
    txt = f"{symbol} {name}".replace("ي", "ی").replace("ك", "ک")
    # Keep this deliberately broad: false positives are safer than missing Lotus contracts.
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
        spread = None
        if valid:
            mid = (ask + bid) / 2.0
            spread = (ask - bid) / mid if mid > 0 else None

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


def append_rows(rows, path: str):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    exists = p.exists() and p.stat().st_size > 0
    with p.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if not exists:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in FIELDS})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all-options", action="store_true", help="capture all paper-type-8 options")
    ap.add_argument("--out", default="data/option_snapshots_gated.csv")
    args = ap.parse_args()

    rows = capture_rows(lotus_only=not args.all_options)
    if not rows:
        raise SystemExit("No Lotus/gold option contracts discovered; fail closed")
    append_rows(rows, args.out)
    valid = sum(bool(r["quote_valid"]) for r in rows)
    summary = {
        "captured": len(rows),
        "valid_bidask": valid,
        "valid_rate": valid / len(rows),
        "output": args.out,
        "rule": "Last/Close never substitute for Bid/Ask",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
