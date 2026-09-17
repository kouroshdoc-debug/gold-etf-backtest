"""Classify each V3 trade into option-data coverage classes.
A = executable-grade candidate (valid reconstructed Bid/Ask + execution-time gate resolved)
B = discovery-grade (valid reconstructed Bid/Ask but execution-time gate unresolved)
C = no usable executable quote evidence.
Research only.
"""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

TRADES='results/trades_V3.csv'
QUOTES='results/historical_option_bidask.csv'
AUDIT='results/historical_option_quality_summary.json'
OUT='results/v3_option_coverage_classes.csv'
SUMMARY='results/v3_option_coverage_classes_summary.json'

def main():
    t=pd.read_csv(TRADES).copy()
    t['entry_date']=pd.to_numeric(t.entry_date,errors='coerce').astype('Int64')
    audit=json.loads(Path(AUDIT).read_text(encoding='utf-8')) if Path(AUDIT).exists() else {}
    q=pd.DataFrame()
    if Path(QUOTES).exists() and Path(QUOTES).stat().st_size:
        try: q=pd.read_csv(QUOTES)
        except pd.errors.EmptyDataError: q=pd.DataFrame()
    valid_dates=set()
    if not q.empty and {'trade_date','bid','ask','quote_valid'}.issubset(q.columns):
        q['trade_date']=pd.to_numeric(q.trade_date,errors='coerce').astype('Int64')
        bid=pd.to_numeric(q.bid,errors='coerce'); ask=pd.to_numeric(q.ask,errors='coerce')
        valid=q.quote_valid.astype(str).str.lower().isin(['true','1']) & bid.gt(0)&ask.gt(0)&ask.ge(bid)
        valid_dates=set(q.loc[valid,'trade_date'].dropna().astype(int))
    time_resolved=audit.get('execution_time_gate') not in (None,'UNRESOLVED')
    rows=[]
    source_status=audit.get('source_status')
    for _,r in t.iterrows():
        d=int(r.entry_date) if pd.notna(r.entry_date) else None
        if d in valid_dates:
            cls='A' if time_resolved else 'B'
            reason='valid_bidask_and_time_gate' if cls=='A' else 'valid_bidask_but_time_gate_unresolved'
        else:
            cls='C'
            reason='provider_unavailable' if source_status=='SOURCE_UNAVAILABLE' else 'no_valid_reconstructed_bidask'
        rows.append({'entry_date':d,'exit_date':int(r.exit_date),'v3_return':float(r['return']),'coverage_class':cls,'reason':reason})
    out=pd.DataFrame(rows); out.to_csv(OUT,index=False)
    counts=out.coverage_class.value_counts().to_dict()
    summary={'v3_trades':int(len(out)),'class_A_executable_candidate':int(counts.get('A',0)),'class_B_discovery_only':int(counts.get('B',0)),'class_C_no_usable_quote':int(counts.get('C',0)),'source_status':source_status,'execution_time_gate':audit.get('execution_time_gate','UNRESOLVED'),'instrument_competition_allowed':bool(counts.get('A',0)>0),'rule':'Only class A may enter ETF-vs-Call-vs-Bull-Call-Spread executable comparison.'}
    Path(SUMMARY).write_text(json.dumps(summary,indent=2),encoding='utf-8'); print(json.dumps(summary,indent=2))
if __name__=='__main__': main()
