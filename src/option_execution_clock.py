"""Freeze a defensible option execution-time gate without fabricating fills.

V3 signal is formed at prior session close and ETF baseline enters next session open.
Options may not be executable at the exact ETF open. This module therefore admits
an option quote only if it is the first valid two-sided quote at/after a frozen
clock and within a maximum delay. It never uses Last/Close as execution.

Research-only. Default clock is deliberately conservative and versioned.
"""
from __future__ import annotations
from dataclasses import dataclass
import json
from pathlib import Path
import pandas as pd

QUOTES='results/historical_option_bidask.csv'
TRADES='results/trades_V3.csv'
OUT='results/option_execution_clock_matches.csv'
SUMMARY='results/option_execution_clock_summary.json'

@dataclass(frozen=True)
class ClockRule:
    version: str='CLOCK_V1'
    earliest_hhmmss: int=90000
    latest_hhmmss: int=93000
    require_two_sided_depth: bool=True

RULE=ClockRule()

def main():
    t=pd.read_csv(TRADES)
    t['entry_date']=pd.to_numeric(t.entry_date,errors='coerce').astype('Int64')
    q=pd.DataFrame()
    p=Path(QUOTES)
    if p.exists() and p.stat().st_size:
        try:q=pd.read_csv(p)
        except pd.errors.EmptyDataError:q=pd.DataFrame()
    rows=[]
    if not q.empty:
        for c in ['trade_date','hEven','bid','ask','bid_size','ask_size']:
            if c in q:q[c]=pd.to_numeric(q[c],errors='coerce')
        valid=q.quote_valid.astype(str).str.lower().isin(['true','1']) if 'quote_valid' in q else pd.Series(False,index=q.index)
        valid &= q.bid.gt(0)&q.ask.gt(0)&q.ask.ge(q.bid)
        valid &= q.hEven.ge(RULE.earliest_hhmmss)&q.hEven.le(RULE.latest_hhmmss)
        if RULE.require_two_sided_depth and {'bid_size','ask_size'}.issubset(q.columns):
            valid &= q.bid_size.gt(0)&q.ask_size.gt(0)
        q=q[valid].sort_values(['trade_date','option_symbol','hEven'])
        first=q.groupby(['trade_date','option_symbol'],as_index=False).first()
        for d,g in first.groupby('trade_date'):
            rows.append({'entry_date':int(d),'admissible_symbols':int(g.option_symbol.nunique()),'first_quote_hEven':int(g.hEven.min()),'last_first_quote_hEven':int(g.hEven.max())})
    m=pd.DataFrame(rows,columns=['entry_date','admissible_symbols','first_quote_hEven','last_first_quote_hEven'])
    base=t[['entry_date','exit_date']].merge(m,on='entry_date',how='left')
    base['admissible_symbols']=base.admissible_symbols.fillna(0).astype(int)
    base['execution_clock_pass']=base.admissible_symbols.gt(0)
    base.to_csv(OUT,index=False)
    n=int(base.execution_clock_pass.sum())
    summary={'rule_version':RULE.version,'earliest_hhmmss':RULE.earliest_hhmmss,'latest_hhmmss':RULE.latest_hhmmss,'require_two_sided_depth':RULE.require_two_sided_depth,'v3_trades':int(len(base)),'trades_passing_clock_gate':n,'coverage_rate':float(n/len(base)) if len(base) else 0.0,'status':'READY_FOR_EXECUTABLE_COMPARISON' if n else 'NO_EXECUTABLE_COVERAGE','rule':'Only first valid two-sided quote inside the frozen clock window is eligible; no Last/Close substitution.'}
    Path(SUMMARY).write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
