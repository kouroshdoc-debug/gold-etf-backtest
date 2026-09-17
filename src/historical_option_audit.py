"""Audit reconstructed historical option Bid/Ask before any executable backtest.

Research safeguards:
- never infer option execution from Last/Close
- do not assume an entry clock time
- quantify quote quality, spread, depth and time coverage
- keep historical reconstruction DISCOVERY_ONLY until an explicit execution-time rule is frozen
"""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import numpy as np

INFILE='results/historical_option_bidask.csv'
MANIFEST='results/historical_option_contract_manifest.csv'
OUT_CSV='results/historical_option_quality_by_date.csv'
OUT_JSON='results/historical_option_quality_summary.json'


def _pct(s, q):
    s=pd.to_numeric(s,errors='coerce').dropna()
    return None if s.empty else float(s.quantile(q))


def main():
    p=Path(INFILE)
    if not p.exists():
        raise SystemExit(f'missing {INFILE}')
    df=pd.read_csv(p)
    required={'trade_date','hEven','option_symbol','ins_code','bid','ask','relative_spread','quote_valid'}
    missing=required-set(df.columns)
    if missing:
        raise SystemExit(f'missing columns: {sorted(missing)}')
    if df.empty:
        summary={'status':'NO_RECONSTRUCTED_QUOTES','rows':0,'rule':'No historical option execution may be inferred.'}
        Path(OUT_JSON).write_text(json.dumps(summary,indent=2),encoding='utf-8')
        pd.DataFrame().to_csv(OUT_CSV,index=False)
        print(json.dumps(summary,indent=2)); return

    for c in ('trade_date','hEven','bid','ask','bid_size','ask_size','relative_spread'):
        if c in df: df[c]=pd.to_numeric(df[c],errors='coerce')
    valid=df['quote_valid'].astype(str).str.lower().isin(['true','1'])
    valid &= df.bid.gt(0)&df.ask.gt(0)&df.ask.ge(df.bid)
    v=df[valid].copy()
    v['crossed_or_locked']=v.ask.le(v.bid)
    if {'bid_size','ask_size'}.issubset(v.columns):
        v['two_sided_depth']=v.bid_size.gt(0)&v.ask_size.gt(0)
    else:
        v['two_sided_depth']=False

    rows=[]
    for d,g in v.groupby('trade_date',sort=True):
        rows.append({
            'trade_date':int(d),
            'symbols_with_valid_quote':int(g.option_symbol.nunique()),
            'valid_quote_states':int(len(g)),
            'earliest_hEven':int(g.hEven.min()),
            'latest_hEven':int(g.hEven.max()),
            'median_relative_spread':float(g.relative_spread.median()) if g.relative_spread.notna().any() else None,
            'p90_relative_spread':float(g.relative_spread.quantile(.90)) if g.relative_spread.notna().any() else None,
            'two_sided_depth_rate':float(g.two_sided_depth.mean()),
        })
    bydate=pd.DataFrame(rows)
    bydate.to_csv(OUT_CSV,index=False)

    manifest=pd.read_csv(MANIFEST) if Path(MANIFEST).exists() else pd.DataFrame()
    summary={
        'status':'DISCOVERY_ONLY',
        'reconstructed_rows':int(len(df)),
        'valid_quote_states':int(len(v)),
        'dates_with_any_valid_quote':int(v.trade_date.nunique()),
        'contracts_with_any_valid_quote':int(v.option_symbol.nunique()),
        'manifest_contracts':int(len(manifest)),
        'median_relative_spread':_pct(v.relative_spread,.50),
        'p90_relative_spread':_pct(v.relative_spread,.90),
        'p95_relative_spread':_pct(v.relative_spread,.95),
        'two_sided_depth_rate':float(v.two_sided_depth.mean()) if len(v) else None,
        'first_quote_time_median':_pct(bydate.earliest_hEven,.50) if len(bydate) else None,
        'last_quote_time_median':_pct(bydate.latest_hEven,.50) if len(bydate) else None,
        'execution_time_gate':'UNRESOLVED',
        'admissible_for_executable_option_backtest':False,
        'rule':'Freeze a defensible option-market execution clock and contract metadata gate before pricing ETF vs Call vs Bull Call Spread.',
    }
    Path(OUT_JSON).write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))

if __name__=='__main__': main()
