"""Forward option-chain snapshot capture scaffold.
Research only: captures executable quote fields; never substitutes last/close for bid/ask.

TSETMC public JSON references used by this project:
- instrument search -> resolve InsCode
- /api/BestLimits/{InsCode} -> current order book
- /api/ClosingPrice/GetClosingPriceInfo/{InsCode} -> quote metadata

Run this during market sessions after contract discovery. Append snapshots to a dated CSV/JSONL artifact.
"""
from __future__ import annotations
import csv, json, os
from datetime import datetime, timezone
from pathlib import Path
import requests

BASE = "https://cdn.tsetmc.com"
UA = {"User-Agent": "Mozilla/5.0 gold-etf-backtest research"}
FIELDS = ["snapshot_ts","trade_date","option_symbol","ins_code","bid","ask","bid_size","ask_size","last","close","volume","source"]

def _get(path: str):
    r=requests.get(BASE+path,headers=UA,timeout=20)
    r.raise_for_status()
    return r.json()

def resolve(symbol: str):
    data=_get(f"/api/Instrument/GetInstrumentSearch/{symbol}")
    rows=data.get("instrumentSearch", data.get("instrument", []))
    exact=[x for x in rows if str(x.get("lVal18AFC","")).strip()==symbol]
    row=(exact or rows)[0] if rows else None
    if not row: raise RuntimeError(f"symbol not found: {symbol}")
    return str(row.get("insCode") or row.get("insCodeInstrument"))

def snapshot(symbol: str):
    ins=resolve(symbol)
    book=_get(f"/api/BestLimits/{ins}").get("bestLimits",[])
    info=_get(f"/api/ClosingPrice/GetClosingPriceInfo/{ins}").get("closingPriceInfo",{})
    best=sorted(book,key=lambda x:x.get("number",999))[0] if book else {}
    now=datetime.now(timezone.utc).astimezone()
    # TSETMC BestLimits field names: pMeDem/qTitMeDem = best demand price/qty;
    # pMeOf/qTitMeOf = best offer price/qty.
    return {
      "snapshot_ts":now.isoformat(), "trade_date":now.date().isoformat(),
      "option_symbol":symbol,"ins_code":ins,
      "bid":best.get("pMeDem"),"ask":best.get("pMeOf"),
      "bid_size":best.get("qTitMeDem"),"ask_size":best.get("qTitMeOf"),
      "last":info.get("pDrCotVal"),"close":info.get("pClosing"),
      "volume":info.get("qTotTran5J"),"source":"TSETMC"
    }

def append_csv(row, path="data/option_snapshots.csv"):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    exists=p.exists()
    with p.open("a",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS)
        if not exists: w.writeheader()
        w.writerow({k:row.get(k) for k in FIELDS})

if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("symbols",nargs="+")
    ap.add_argument("--out",default="data/option_snapshots.csv")
    a=ap.parse_args()
    for s in a.symbols:
        row=snapshot(s); append_csv(row,a.out); print(json.dumps(row,ensure_ascii=False))
