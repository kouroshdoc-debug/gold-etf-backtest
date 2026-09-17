"""Validate Iran-side option snapshots before research ingestion. Fail closed."""
from pathlib import Path
import json, hashlib
import pandas as pd

IN=Path('data/option_snapshots_gated.csv'); OUT=Path('results/option_snapshot_validation.json')
REQ={'captured_at_tehran','trade_date','provider','symbol','bid','ask','relative_spread','quote_valid','source_hash'}

def main():
    OUT.parent.mkdir(parents=True,exist_ok=True)
    if not IN.exists():
        s={'status':'MISSING','admissible':False,'rows':0}; OUT.write_text(json.dumps(s,indent=2)); print(json.dumps(s)); return
    try: d=pd.read_csv(IN)
    except Exception as e:
        s={'status':'UNREADABLE','admissible':False,'error':repr(e)}; OUT.write_text(json.dumps(s,indent=2)); print(json.dumps(s)); return
    miss=REQ-set(d.columns)
    if miss:
        s={'status':'SCHEMA_FAIL','admissible':False,'missing':sorted(miss),'rows':len(d)}; OUT.write_text(json.dumps(s,indent=2)); print(json.dumps(s)); return
    bid=pd.to_numeric(d.bid,errors='coerce'); ask=pd.to_numeric(d.ask,errors='coerce'); sp=pd.to_numeric(d.relative_spread,errors='coerce')
    q=d.quote_valid.astype(str).str.lower().isin(['true','1']) & bid.gt(0)&ask.gt(0)&ask.ge(bid)&sp.ge(0)
    ts=pd.to_datetime(d.captured_at_tehran,errors='coerce')
    valid=q & ts.notna()
    dup=int(d.duplicated(['captured_at_tehran','symbol','bid','ask']).sum())
    s={'status':'PASS' if valid.any() else 'NO_VALID_ROWS','admissible':bool(valid.any()),'rows':int(len(d)),'valid_rows':int(valid.sum()),'symbols':int(d.loc[valid,'symbol'].nunique()),'dates':int(d.loc[valid,'trade_date'].nunique()),'duplicate_states':dup,'median_spread':float(sp[valid].median()) if valid.any() else None,'p95_spread':float(sp[valid].quantile(.95)) if valid.any() else None,'dataset_sha256':hashlib.sha256(IN.read_bytes()).hexdigest(),'rule':'Only timestamped two-sided Bid/Ask rows are admissible.'}
    OUT.write_text(json.dumps(s,indent=2),encoding='utf-8'); print(json.dumps(s,indent=2))
if __name__=='__main__': main()
