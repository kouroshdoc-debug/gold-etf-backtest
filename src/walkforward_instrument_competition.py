"""Walk-forward instrument competition harness. Research only.
Historical option rows are admitted only when timestamped executable bid/ask existed at/before entry.
Missing option quotes => ETF remains benchmark; option P&L is never fabricated.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import pandas as pd
from backtest import trade_log
from scenario_calibration import calibrate
from instrument_selection_engine import Scenario, etf_candidate, call_candidate, bull_call_spread_candidate, select

REQUIRED_OPTION={"entry_date","snapshot_ts","symbol","kind","S","K","T","iv","bid","ask","delta","relative_spread","quote_valid"}

def empirical_scenarios(cal):
    return [Scenario(x['name'],x['probability_shrunk'],x['underlying_return'],1.0) for x in cal['scenarios']]

def eligible_quotes(q,entry_date):
    if q is None or q.empty:return pd.DataFrame()
    miss=REQUIRED_OPTION-set(q.columns)
    if miss: raise ValueError('missing option columns: '+','.join(sorted(miss)))
    z=q[(q.entry_date.astype(int)==int(entry_date)) & (q.quote_valid.astype(str).str.lower().isin(['true','1']))].copy()
    # timestamp is retained for audit; producer must guarantee at/before-entry capture.
    return z

def compete(history,quotes=None,min_train=30):
    trades=trade_log(history,'V3',thr=10,trend=200,dev=-.002,cost=.00125).reset_index(drop=True)
    rows=[]
    for i,t in trades.iterrows():
        if i<min_train: continue
        cal=calibrate(trades.iloc[:i],asof=int(t.entry_date),min_trades=min_train)
        sc=empirical_scenarios(cal); candidates=[etf_candidate(float(t.entry),sc)]
        q=eligible_quotes(quotes,int(t.entry_date))
        option_admissible=0
        for _,x in q.iterrows():
            if x.kind=='CALL':
                candidates.append(call_candidate(x.symbol,float(x.S),float(x.K),float(x.T),float(x.iv),float(x.ask),float(x.delta),sc,rel_spread=float(x.relative_spread))); option_admissible+=1
        # spreads only from explicitly preconstructed, same-timestamp rows to avoid retrospective strike pairing.
        # Future schema may add BULL_CALL_SPREAD rows with both legs audited.
        decision=select(candidates,mode='risk_budget')
        rows.append({'entry_date':int(t.entry_date),'exit_date':int(t.exit_date),'v3_realized_return':float(t['return']),
                     'option_quotes_admissible':option_admissible,'selection':decision['selection'],'kind':decision.get('kind','NO_TRADE'),
                     'selection_score':decision['score'],'calibration_n':cal['n_completed']})
    return pd.DataFrame(rows)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--data',default='data/tala_history.csv');ap.add_argument('--quotes');ap.add_argument('--out',default='results/walkforward_instrument_competition.csv');a=ap.parse_args()
    h=pd.read_csv(a.data);q=pd.read_csv(a.quotes) if a.quotes and Path(a.quotes).exists() else None
    out=compete(h,q);Path(a.out).parent.mkdir(parents=True,exist_ok=True);out.to_csv(a.out,index=False)
    summary={'rows':len(out),'option_admissible_events':int((out.option_quotes_admissible>0).sum()) if len(out) else 0,'option_selections':int(out.selection.ne('ETF').sum()) if len(out) else 0,
             'warning':'No historical option result is valid unless executable timestamped bid/ask passed admission.'}
    Path('results/instrument_competition_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
