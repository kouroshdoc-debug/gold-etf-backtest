"""Forward Lotus-option snapshot collector. Research only.
Never substitutes Last/Close for executable Bid/Ask.
"""
from __future__ import annotations
import csv, json, re
from datetime import datetime, timezone
from pathlib import Path
import requests

BASE="https://cdn.tsetmc.com"
UA={"User-Agent":"Mozilla/5.0 gold-etf-backtest research"}
FIELDS=["snapshot_ts","trade_date","option_symbol","ins_code","bid","ask","bid_size","ask_size","last","close","volume","relative_spread","quote_valid","source"]

def _get(path):
    r=requests.get(BASE+path,headers=UA,timeout=20); r.raise_for_status(); return r.json()

def search(q):
    d=_get(f"/api/Instrument/GetInstrumentSearch/{q}")
    return d.get("instrumentSearch",d.get("instrument",[])) or []

def resolve(symbol):
    rows=search(symbol)
    exact=[x for x in rows if str(x.get("lVal18AFC","")).strip()==symbol]
    row=(exact or rows)[0] if rows else None
    if not row: raise RuntimeError(f"symbol not found: {symbol}")
    return str(row.get("insCode") or row.get("insCodeInstrument"))

def discover_lotus_calls():
    # Query several known Lotus option prefixes/families, then retain call-like codes.
    rows=[]
    for q in ("TL","TLME","TLDY","TLTR"):
        try: rows.extend(search(q))
        except Exception: pass
    found={}
    for x in rows:
        s=str(x.get("lVal18AFC","")).strip().upper()
        ins=str(x.get("insCode") or x.get("insCodeInstrument") or "")
        if ins and re.match(r"^TL[A-Z0-9]*C[0-9]+$",s): found[s]=ins
    return sorted(found)

def snapshot(symbol):
    ins=resolve(symbol)
    book=_get(f"/api/BestLimits/{ins}").get("bestLimits",[])
    info=_get(f"/api/ClosingPrice/GetClosingPriceInfo/{ins}").get("closingPriceInfo",{})
    best=sorted(book,key=lambda x:x.get("number",999))[0] if book else {}
    bid=best.get("pMeDem"); ask=best.get("pMeOf")
    spread=None; valid=False
    try:
        b=float(bid); a=float(ask); mid=(a+b)/2
        valid=(b>=0 and a>0 and a>=b and mid>0)
        spread=(a-b)/mid if valid else None
    except Exception: pass
    now=datetime.now(timezone.utc).astimezone()
    return {"snapshot_ts":now.isoformat(),"trade_date":now.date().isoformat(),"option_symbol":symbol,"ins_code":ins,
      "bid":bid,"ask":ask,"bid_size":best.get("qTitMeDem"),"ask_size":best.get("qTitMeOf"),
      "last":info.get("pDrCotVal"),"close":info.get("pClosing"),"volume":info.get("qTotTran5J"),
      "relative_spread":spread,"quote_valid":valid,"source":"TSETMC"}

def write_rows(rows,path):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS); w.writeheader()
        for r in rows: w.writerow({k:r.get(k) for k in FIELDS})

def main():
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument("symbols",nargs="*"); ap.add_argument("--auto",action="store_true"); ap.add_argument("--out",default="data/option_snapshots.csv")
    a=ap.parse_args(); symbols=discover_lotus_calls() if a.auto else a.symbols
    if not symbols: raise SystemExit("No Lotus call contracts discovered")
    rows=[]
    for s in symbols:
        try:
            r=snapshot(s); rows.append(r); print(json.dumps(r,ensure_ascii=False))
        except Exception as e: print(json.dumps({"option_symbol":s,"error":str(e)},ensure_ascii=False))
    write_rows(rows,a.out)
    print(f"captured={len(rows)} discovered={len(symbols)}")
if __name__=="__main__": main()
