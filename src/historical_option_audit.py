"""Audit reconstructed historical option Bid/Ask before any executable backtest.
Fail closed, but never confuse provider outage with absence of option contracts.
"""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

INFILE='results/historical_option_bidask.csv'
MANIFEST='results/historical_option_contract_manifest.csv'
RECON='results/historical_option_reconstruction_summary.json'
OUT_CSV='results/historical_option_quality_by_date.csv'
OUT_JSON='results/historical_option_quality_summary.json'
BYDATE_COLUMNS=['trade_date','symbols_with_valid_quote','valid_quote_states','earliest_hEven','latest_hEven','median_relative_spread','p90_relative_spread','two_sided_depth_rate']

def _pct(s,q):
    s=pd.to_numeric(s,errors='coerce').dropna(); return None if s.empty else float(s.quantile(q))

def _write_empty(recon, reason):
    pd.DataFrame(columns=BYDATE_COLUMNS).to_csv(OUT_CSV,index=False)
    summary={'status':reason,'reconstructed_rows':0,'valid_quote_states':0,'dates_with_any_valid_quote':0,'contracts_with_any_valid_quote':0,'source_status':recon.get('source_status'),'execution_time_gate':'UNRESOLVED','admissible_for_executable_option_backtest':False,'rule':'No executable option performance may be inferred without timestamped reconstructed Bid/Ask.'}
    Path(OUT_JSON).write_text(json.dumps(summary,indent=2),encoding='utf-8'); print(json.dumps(summary,indent=2)); return

def main():
    recon=json.loads(Path(RECON).read_text(encoding='utf-8')) if Path(RECON).exists() else {}
    p=Path(INFILE)
    if not p.exists() or p.stat().st_size==0: return _write_empty(recon,'NO_RECONSTRUCTED_QUOTES')
    try: df=pd.read_csv(p)
    except pd.errors.EmptyDataError: return _write_empty(recon,'NO_RECONSTRUCTED_QUOTES')
    if df.empty: return _write_empty(recon,'SOURCE_UNAVAILABLE' if recon.get('source_status')=='SOURCE_UNAVAILABLE' else 'NO_RECONSTRUCTED_QUOTES')
    required={'trade_date','hEven','option_symbol','ins_code','bid','ask','relative_spread','quote_valid'}
    missing=required-set(df.columns)
    if missing: raise SystemExit(f'missing columns: {sorted(missing)}')
    for c in ('trade_date','hEven','bid','ask','bid_size','ask_size','relative_spread'):
        if c in df: df[c]=pd.to_numeric(df[c],errors='coerce')
    valid=df.quote_valid.astype(str).str.lower().isin(['true','1']) & df.bid.gt(0)&df.ask.gt(0)&df.ask.ge(df.bid)
    v=df[valid].copy(); v['two_sided_depth']=(v.bid_size.gt(0)&v.ask_size.gt(0)) if {'bid_size','ask_size'}.issubset(v.columns) else False
    rows=[]
    for d,g in v.groupby('trade_date',sort=True):
        rows.append({'trade_date':int(d),'symbols_with_valid_quote':int(g.option_symbol.nunique()),'valid_quote_states':int(len(g)),'earliest_hEven':int(g.hEven.min()),'latest_hEven':int(g.hEven.max()),'median_relative_spread':float(g.relative_spread.median()) if g.relative_spread.notna().any() else None,'p90_relative_spread':float(g.relative_spread.quantile(.90)) if g.relative_spread.notna().any() else None,'two_sided_depth_rate':float(g.two_sided_depth.mean())})
    bydate=pd.DataFrame(rows,columns=BYDATE_COLUMNS); bydate.to_csv(OUT_CSV,index=False)
    manifest=pd.read_csv(MANIFEST) if Path(MANIFEST).exists() and Path(MANIFEST).stat().st_size else pd.DataFrame()
    summary={'status':'DISCOVERY_ONLY','source_status':recon.get('source_status'),'reconstructed_rows':int(len(df)),'valid_quote_states':int(len(v)),'dates_with_any_valid_quote':int(v.trade_date.nunique()),'contracts_with_any_valid_quote':int(v.option_symbol.nunique()),'manifest_contracts':int(len(manifest)),'median_relative_spread':_pct(v.relative_spread,.50),'p90_relative_spread':_pct(v.relative_spread,.90),'p95_relative_spread':_pct(v.relative_spread,.95),'two_sided_depth_rate':float(v.two_sided_depth.mean()) if len(v) else None,'first_quote_time_median':_pct(bydate.earliest_hEven,.50) if len(bydate) else None,'last_quote_time_median':_pct(bydate.latest_hEven,.50) if len(bydate) else None,'execution_time_gate':'UNRESOLVED','admissible_for_executable_option_backtest':False,'rule':'Freeze a defensible option-market execution clock and contract metadata gate before pricing ETF vs Call vs Bull Call Spread.'}
    Path(OUT_JSON).write_text(json.dumps(summary,indent=2),encoding='utf-8'); print(json.dumps(summary,indent=2))
if __name__=='__main__': main()
