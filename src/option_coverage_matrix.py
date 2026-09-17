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
    # signal is prior trading session to entry, never calendar-day subtraction.
    t['signal_date']=[int(history.date.iloc[int(i)-1]) for i in t.entry_i]
    rows=[]
    for x in t.itertuples():
        active=0;daily=0;valid=0;symbols=[]
        if contracts is not None and not contracts.empty:
            # Optional contract-universe fields: history_start/history_end or start_date/end_date.
            a='history_start' if 'history_start' in contracts else ('start_date' if 'start_date' in contracts else None)
            b='history_end' if 'history_end' in contracts else ('end_date' if 'end_date' in contracts else None)
            if a and b:
                c=contracts[(pd.to_datetime(contracts[a],errors='coerce')<=pd.to_datetime(str(x.entry_date))) & (pd.to_datetime(contracts[b],errors='coerce')>=pd.to_datetime(str(x.entry_date)))]
                active=len(c);daily=len(c)
        if snapshots is not None and not snapshots.empty:
            s=snapshots.copy()
            datecol='entry_date' if 'entry_date' in s else ('trade_date' if 'trade_date' in s else None)
            if datecol:
                ds=s[datecol].astype(str).str.replace('-','',regex=False)
                s=s[ds==str(int(x.entry_date))]
            if 'quote_valid' in s:
                s=s[s.quote_valid.astype(str).str.lower().isin(['true','1'])]
            if {'bid','ask'}.issubset(s.columns):
                s=s[pd.to_numeric(s.bid,errors='coerce').gt(0)&pd.to_numeric(s.ask,errors='coerce').gt(0)&(pd.to_numeric(s.ask,errors='coerce')>=pd.to_numeric(s.bid,errors='coerce'))]
            valid=len(s)
            sym='option_symbol' if 'option_symbol' in s else ('symbol' if 'symbol' in s else None)
            if sym: symbols=sorted(set(s[sym].astype(str)))
        rows.append({'signal_date':int(x.signal_date),'entry_date':int(x.entry_date),'exit_date':int(x.exit_date),'v3_return':float(x.return_),
                     'active_contract_count':active,'daily_history_count':daily,'valid_bidask_snapshot_count':valid,
                     'bidask_snapshot_available':valid>0,'admissible_for_executable_backtest':valid>0,'admissible_symbols':'|'.join(symbols)})
    return pd.DataFrame(rows)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--data',default='data/tala_history.csv');ap.add_argument('--snapshots');ap.add_argument('--contracts');ap.add_argument('--out',default='results/v3_option_coverage_matrix.csv');a=ap.parse_args()
    h=pd.read_csv(a.data);s=pd.read_csv(a.snapshots) if a.snapshots and Path(a.snapshots).exists() else None;c=pd.read_csv(a.contracts) if a.contracts and Path(a.contracts).exists() else None
    out=build(h,s,c);Path(a.out).parent.mkdir(parents=True,exist_ok=True);out.to_csv(a.out,index=False)
    summary={'v3_trades':len(out),'executable_covered_trades':int(out.admissible_for_executable_backtest.sum()),'coverage_rate':float(out.admissible_for_executable_backtest.mean()) if len(out) else 0.0,
             'inadmissible_trades':int((~out.admissible_for_executable_backtest).sum()),'rule':'No valid timestamped Bid/Ask => no executable option backtest.'}
    Path('results/v3_option_coverage_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
