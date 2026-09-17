"""Shadow ETF vs Call vs Bull Call Spread competition.
Research only. Never authorizes a live trade. Uses executable Ask for long entry and Bid for exit.
Fail closed when metadata, timestamps or quotes are insufficient.
"""
from __future__ import annotations
from pathlib import Path
import json
import pandas as pd

SNAP=Path('data/option_snapshots_gated.csv'); VAL=Path('results/option_snapshot_validation.json')
OUT=Path('results/shadow_instrument_competition.csv'); SUMMARY=Path('results/shadow_instrument_competition_summary.json')
REQ={'captured_at_tehran','trade_date','symbol','contract_type','strike','expiry','dte','contract_size','bid','ask','bid_size','ask_size','relative_spread','quote_valid'}
MAX_SPREAD=.12; MIN_DTE=7; MAX_DTE=90

def main():
    OUT.parent.mkdir(parents=True,exist_ok=True)
    gate=json.loads(VAL.read_text()) if VAL.exists() else {'admissible':False,'status':'VALIDATION_MISSING'}
    if not gate.get('admissible') or not SNAP.exists():
        pd.DataFrame(columns=['trade_date','symbol','instrument','admissible','reason']).to_csv(OUT,index=False)
        s={'status':'BLOCKED','rows':0,'reason':gate.get('status'),'live_trade_authorized':False}; SUMMARY.write_text(json.dumps(s,indent=2)); print(json.dumps(s)); return
    d=pd.read_csv(SNAP); miss=REQ-set(d.columns)
    if miss:
        s={'status':'SCHEMA_FAIL','missing':sorted(miss),'live_trade_authorized':False}; SUMMARY.write_text(json.dumps(s,indent=2)); print(json.dumps(s)); return
    for c in ['strike','dte','contract_size','bid','ask','bid_size','ask_size','relative_spread']: d[c]=pd.to_numeric(d[c],errors='coerce')
    d['captured_at_tehran']=pd.to_datetime(d.captured_at_tehran,errors='coerce')
    q=d.quote_valid.astype(str).str.lower().isin(['true','1']) & d.bid.gt(0)&d.ask.ge(d.bid)&d.relative_spread.le(MAX_SPREAD)&d.dte.between(MIN_DTE,MAX_DTE)&d.contract_size.gt(0)&d.strike.gt(0)&d.captured_at_tehran.notna()
    a=d.loc[q].copy()
    # Freeze candidate universe only. No performance winner is selected until paired entry/exit executable quotes exist.
    a['instrument']='CALL_CANDIDATE'; a['admissible']=True; a['reason']='two_sided_quote_metadata_spread_dte_pass'
    cols=['trade_date','captured_at_tehran','symbol','instrument','strike','expiry','dte','contract_size','bid','ask','bid_size','ask_size','relative_spread','admissible','reason']
    a[cols].to_csv(OUT,index=False)
    s={'status':'READY_FOR_SHADOW_PAIRING' if len(a) else 'NO_ADMISSIBLE_CANDIDATES','snapshot_rows':int(len(d)),'admissible_call_candidates':int(len(a)),'symbols':int(a.symbol.nunique()) if len(a) else 0,'frozen_gates':{'max_relative_spread':MAX_SPREAD,'min_dte':MIN_DTE,'max_dte':MAX_DTE,'entry':'ASK','exit':'BID'},'bull_call_spread_rule':'Requires two admissible calls same expiry, long lower strike at Ask and short higher strike at Bid; no synthetic quotes.','selection_rule':'No winner until same-risk-budget entry/exit pairing exists.','live_trade_authorized':False}
    SUMMARY.write_text(json.dumps(s,indent=2),encoding='utf-8'); print(json.dumps(s,indent=2))
if __name__=='__main__': main()
