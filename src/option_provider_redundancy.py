"""Redundant option-data provider probe and metadata collector.
Research only. This module never upgrades OHLC/Last into executable Bid/Ask.

Providers:
1) cdn.tsetmc.com / cdn10.tsetmc.com for InsCode-centric discovery and books.
2) webgw.tse.ir official gateway for option inventories/metadata and live level-1 when reachable.

Outputs are diagnostic/metadata only unless explicit Bid/Ask quality gates pass.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

TEHRAN = ZoneInfo("Asia/Tehran")
UA = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36 option-research",
    "Accept": "application/json,text/plain,*/*",
}
CDN_BASES = ("https://cdn.tsetmc.com", "https://cdn10.tsetmc.com")
WEBGW = "https://webgw.tse.ir"


def _request_json(url: str, timeout: int = 12):
    r = requests.get(url, headers=UA, timeout=timeout)
    r.raise_for_status()
    if not r.content:
        return None
    return r.json()


def _probe(name: str, url: str):
    t0 = time.perf_counter()
    try:
        d = _request_json(url)
        return {
            "provider": name,
            "ok": True,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            "http": 200,
            "shape": type(d).__name__,
            "error": None,
        }, d
    except Exception as e:
        return {
            "provider": name,
            "ok": False,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            "http": None,
            "shape": None,
            "error": f"{type(e).__name__}: {e}"[:240],
        }, None


def probe_all():
    probes = []
    payloads = {}
    for base in CDN_BASES:
        name = base.split("//", 1)[1]
        h, d = _probe(name, base + "/api/Instrument/GetInstrumentSearch/TL")
        probes.append(h); payloads[name] = d

    endpoints = {
        "webgw_option": "/InstrumentProvider/api/v1/MarketWatch/MarketWatchOption/fa",
        "webgw_tradeoption": "/InstrumentProvider/api/v1/MarketWatch/MarketWatchTradeOption/fa",
    }
    for name, path in endpoints.items():
        h, d = _probe(name, WEBGW + path)
        probes.append(h); payloads[name] = d
    return pd.DataFrame(probes), payloads


def _num(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def _items(payload):
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ("Items", "items", "data", "marketwatch", "marketWatch"):
            v = payload.get(k)
            if isinstance(v, list):
                return v
    return []


def build_webgw_inventory(payloads):
    rows = []
    now = datetime.now(TEHRAN).isoformat(timespec="seconds")
    for source in ("webgw_option", "webgw_tradeoption"):
        for x in _items(payloads.get(source)):
            # Preserve raw names because the official gateway naming is not fully stable.
            isin = x.get("instrumentId") or x.get("instrumentid") or x.get("buyInstrumentId") or x.get("buyinstrumentid")
            symbol = x.get("instrumentName") or x.get("instrument_Name") or x.get("buyInstrumentName") or x.get("buyinstrumentname")
            strike = x.get("qeymateEmal") or x.get("buyQeymateEmal")
            expiry = x.get("tarixSarresid") or x.get("buyTarixSarresid")
            dte = x.get("baghimandetasarresid") or x.get("buyBaqimandeTaSarresId")
            contract_size = x.get("andazeyeQarardad") or x.get("buyAndazeyeQarardad")
            buy = x.get("buyPrice") or x.get("buyprice")
            sell = x.get("sellPrice") or x.get("sellprice")
            rows.append({
                "snapshot_ts": now,
                "source": source,
                "instrument_id": isin,
                "symbol": symbol,
                "strike": strike,
                "expiry": expiry,
                "dte": dte,
                "contract_size": contract_size,
                "buy_price": _num(buy),
                "sell_price": _num(sell),
                "last_price": _num(x.get("lastPrice") or x.get("lastprice")),
                "closing_price": _num(x.get("closingPrice") or x.get("closingprice")),
                "trade_volume": _num(x.get("tradeVolume") or x.get("tradevolume")),
                "trade_count": _num(x.get("tradeCount") or x.get("tradecount")),
            })
    return pd.DataFrame(rows).drop_duplicates(subset=["source", "instrument_id", "symbol"], keep="last") if rows else pd.DataFrame()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="results")
    a = ap.parse_args()
    out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)

    health, payloads = probe_all()
    health.to_csv(out / "option_provider_health.csv", index=False)
    inv = build_webgw_inventory(payloads)
    inv.to_csv(out / "option_provider_inventory.csv", index=False)

    summary = {
        "timestamp_tehran": datetime.now(TEHRAN).isoformat(timespec="seconds"),
        "providers_ok": int(health.ok.sum()) if len(health) else 0,
        "providers_total": int(len(health)),
        "cdn_any_ok": bool(health.loc[health.provider.str.contains("tsetmc"), "ok"].any()) if len(health) else False,
        "webgw_any_ok": bool(health.loc[health.provider.str.contains("webgw"), "ok"].any()) if len(health) else False,
        "webgw_inventory_rows": int(len(inv)),
        "status": "METADATA_ONLY",
        "rule": "Provider fallback may recover contract discovery/metadata; executable option backtests still require timestamped valid Bid/Ask at entry/exit.",
    }
    (out / "option_provider_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(health.to_string(index=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
