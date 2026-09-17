"""Build exact V3-to-option coverage matrix. Research only.
Daily option history may establish DISCOVERY_ONLY coverage; executable admission requires timestamped valid bid/ask at/before entry.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
import pandas as pd
from backtest import trade_log

def build(history,snapshots=None,contracts=None):
    t=trade_log(history,'V3',thr=10,trend=200,dev=-.002,cost=.00125).copy()
    t['signal_date']=[int(history.date.iloc[int(i)-1]) for i in t.entry_i]
    rows=[]
    for _,x in t.iterrows():
        active=0;daily=0;valid=0;symbols=[]
        entry_date=int(x['entry_date'])
        if contracts is not None and not contracts.empty:
            a='history_start' if 'history_start' in contracts else ('start_date' if 'start_date' in contracts else None)
            b='history_end' if 'history_end' in contracts else ('end_date' if 'end_date' in contracts else None)
            if a and b:
                d=pd.to_datetime(str(entry_date),format='%Y%m%d',errors='coerce')
                ca=pd.to_datetime(contracts[a],errors='coerce'); cb=pd.to_datetime(contracts[b],errors='coerce')
                c=contracts[(ca<=d)&(cb>=d)]; active=len(c);daily=len(c)
        if snapshots is not None and not snapshots.empty:
            s=snapshots.copy()
            datecol='entry_date' if 'entry_date' in s else ('trade_date' if 'trade_date' in s else None)
            if datecol:
                ds=s[datecol].astype(str).str.replace('-','',regex=False).str.replace('.0','',regex=False)
                s=s[ds==str(entry_date)]
            else:
                s=s.iloc[0:0]
            if 'quote_valid' in s:
                s=s[s.quote_valid.astype(str).str.lower().isin(['true','1'])]
            else:
                s=s.iloc[0:0]
            if {'bid','ask'}.issubset(s.columns):
                bid=pd.to_numeric(s.bid,errors='coerce'); ask=pd.to_numeric(s.ask,errors='coerce')
                s=s[bid.gt(0)&ask.gt(0)&ask.ge(bid)]
            else:
                s=s.iloc[0:0]
            valid=len(s)
            sym='option_symbol' if 'option_symbol' in s else ('symbol' if 'symbol' in s else None)
            if sym: symbols=sorted(set(s[sym].astype(str)))
        rows.append({'signal_date':int(x['signal_date']),'entry_date':entry_date,'exit_date':int(x['exit_date']),'v3_return':float(x['return']),
                     'active_contract_count':active,'daily_history_count':daily,'valid_bidask_snapshot_count':valid,
                     'bidask_snapshot_available':valid>0,'admissible_for_executable_backtest':valid>0,'admissible_symbols':'|'.join(symbols)})
    return pd.DataFrame(rows)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--data',default='data/tala_history.csv');ap.add_argument('--snapshots');ap.add_argument('--contracts');ap.add_argument('--out',default='results/v3_option_coverage_matrix.csv');a=ap.parse_args()
    h=pd.read_csv(a.data);s=pd.read_csv(a.snapshots) if a.snapshots and Path(a.snapshots).exists() else None;c=pd.read_csv(a.contracts) if a.contracts and Path(a.contracts).exists() else None
    out=build(h,s,c);Path(a.out).parent.mkdir(parents=True,exist_ok=True);out.to_csv(a.out,index=False)
    covered=int(out.admissible_for_executable_backtest.sum()) if len(out) else 0
    summary={'v3_trades':len(out),'executable_covered_trades':covered,'coverage_rate':covered/len(out) if len(out) else 0.0,
             'inadmissible_trades':len(out)-covered,'rule':'No valid timestamped Bid/Ask => no executable option backtest.'}
    Path('results/v3_option_coverage_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
