"""Build a forward-only shadow ledger from validated option snapshots and V3 signals.
No capital, no order routing, no promotion without predeclared evidence gates.
"""
from __future__ import annotations
from pathlib import Path
import json
import pandas as pd

TRADES=Path('results/trades_V3.csv')
SNAP=Path('data/option_snapshots_gated.csv')
VAL=Path('results/option_snapshot_validation.json')
CAND=Path('results/shadow_instrument_competition.csv')
OUT=Path('results/shadow_forward_ledger.csv')
SUM=Path('results/shadow_forward_ledger_summary.json')

MIN_EVENTS_FOR_REVIEW=20
MIN_DISTINCT_DATES=10
MIN_EXITS=10


def main():
    OUT.parent.mkdir(parents=True,exist_ok=True)
    gate=json.loads(VAL.read_text()) if VAL.exists() else {'admissible':False,'status':'VALIDATION_MISSING'}
    if not gate.get('admissible'):
        pd.DataFrame(columns=['event_id','signal_date','entry_date','instrument','status','reason']).to_csv(OUT,index=False)
        s={'status':'BLOCKED','reason':gate.get('status'),'promotion_status':'NOT_ELIGIBLE','live_trade_authorized':False}
        SUM.write_text(json.dumps(s,indent=2)); print(json.dumps(s)); return
    if not (TRADES.exists() and SNAP.exists() and CAND.exists()):
        s={'status':'INPUT_MISSING','promotion_status':'NOT_ELIGIBLE','live_trade_authorized':False}; SUM.write_text(json.dumps(s,indent=2)); print(json.dumps(s)); return
    t=pd.read_csv(TRADES); s=pd.read_csv(SNAP); c=pd.read_csv(CAND)
    if c.empty:
        pd.DataFrame(columns=['event_id','signal_date','entry_date','instrument','status','reason']).to_csv(OUT,index=False)
        x={'status':'NO_SHADOW_CANDIDATES','promotion_status':'NOT_ELIGIBLE','live_trade_authorized':False}; SUM.write_text(json.dumps(x,indent=2)); print(json.dumps(x)); return
    for df,col in [(t,'entry_date'),(s,'trade_date'),(c,'trade_date')]: df[col]=pd.to_numeric(df[col],errors='coerce').astype('Int64')
    rows=[]
    for _,tr in t.iterrows():
        ed=int(tr.entry_date) if pd.notna(tr.entry_date) else None
        sd=ed-1 if ed else None
        cc=c[c.trade_date.eq(ed)]
        if cc.empty: continue
        for _,r in cc.iterrows():
            eid=f"{ed}:{r.symbol}"
            rows.append({'event_id':eid,'signal_date':sd,'entry_date':ed,'exit_date':int(tr.exit_date),'v3_realized_return':float(tr['return']),'instrument':'CALL_CANDIDATE','symbol':r.symbol,'entry_ask':float(r.ask),'entry_bid':float(r.bid),'entry_spread':float(r.relative_spread),'status':'OPEN_SHADOW_EVENT','reason':'entry_quote_valid_exit_pair_pending'})
    out=pd.DataFrame(rows)
    if out.empty: out=pd.DataFrame(columns=['event_id','signal_date','entry_date','exit_date','instrument','status','reason'])
    out.to_csv(OUT,index=False)
    events=len(out); dates=out.entry_date.nunique() if events else 0; exits=int((out.status=='CLOSED_SHADOW_EVENT').sum()) if 'status' in out else 0
    eligible=events>=MIN_EVENTS_FOR_REVIEW and dates>=MIN_DISTINCT_DATES and exits>=MIN_EXITS
    x={'status':'COLLECTING' if events else 'NO_EVENTS','shadow_events':int(events),'distinct_entry_dates':int(dates),'closed_shadow_events':int(exits),'promotion_review_gates':{'min_events':MIN_EVENTS_FOR_REVIEW,'min_distinct_entry_dates':MIN_DISTINCT_DATES,'min_closed_events':MIN_EXITS},'promotion_status':'REVIEW_ELIGIBLE' if eligible else 'NOT_ELIGIBLE','rule':'Promotion requires forward shadow evidence and separate OOS/WF review; no automatic live transfer.','live_trade_authorized':False}
    SUM.write_text(json.dumps(x,indent=2),encoding='utf-8'); print(json.dumps(x,indent=2))
if __name__=='__main__': main()
