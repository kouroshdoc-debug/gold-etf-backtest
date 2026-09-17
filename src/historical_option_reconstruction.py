"""Reconstruct historical Lotus call Bid/Ask from TSETMC BestLimits delta history.
Research only: no Last/Close substitution. Output is discovery evidence until timing/contract metadata gates pass.
"""
from __future__ import annotations
import argparse, json, re, time
from pathlib import Path
import pandas as pd
import requests

BASES=("https://cdn.tsetmc.com","https://cdn10.tsetmc.com")
UA={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36","Accept":"application/json,text/plain,*/*"}
BOOTSTRAP=("TLDY05C110","TLDY05C190","TLTR05C70","TLTR05C110","TLTR05C170","TLTR05C190")

def get(path, timeout=18):
    errors=[]
    for base in BASES:
        for k in range(2):
            try:
                r=requests.get(base+path,headers=UA,timeout=timeout); r.raise_for_status(); return r.json()
            except Exception as e:
                errors.append(f"{base}:{type(e).__name__}"); time.sleep(.6*(k+1))
    raise RuntimeError("TSETMC unavailable: "+",".join(errors[-4:]))

def search(q):
    d=get(f"/api/Instrument/GetInstrumentSearch/{q}")
    return d.get("instrumentSearch",[]) if isinstance(d,dict) else []

def discover():
    found={}
    for s in BOOTSTRAP:
        try:
            rows=search(s); exact=[x for x in rows if str(x.get('lVal18AFC','')).strip().upper()==s]
            if exact: found[s]=str(exact[0].get('insCode') or exact[0].get('insCodeInstrument'))
        except Exception: pass
    for q in ("TL","TLDY","TLTR","TLME"):
        try:
            for x in search(q):
                s=str(x.get('lVal18AFC','')).strip().upper(); ins=str(x.get('insCode') or x.get('insCodeInstrument') or '')
                if ins and re.match(r'^TL[A-Z0-9]*C[0-9]+$',s): found[s]=ins
        except Exception: pass
    return found

def active_range(ins):
    d=get(f"/api/ClosingPrice/GetClosingPriceDailyList/{ins}/0")
    rows=d.get('closingPriceDaily',[]) if isinstance(d,dict) else []
    ds=sorted(int(x['dEven']) for x in rows if x.get('dEven'))
    return (ds[0],ds[-1]) if ds else (None,None)

def reconstruct(ins, deven):
    d=get(f"/api/BestLimits/{ins}/{deven}")
    rows=(d.get('bestLimitsHistory') or d.get('bestLimits') or []) if isinstance(d,dict) else []
    def n(v):
        try:return float(v)
        except:return None
    rows=sorted(rows,key=lambda x:(int(x.get('hEven') or 0),int(x.get('number') or 99)))
    state={}; out=[]; i=0
    while i<len(rows):
        h=int(rows[i].get('hEven') or 0); batch=[]
        while i<len(rows) and int(rows[i].get('hEven') or 0)==h:
            batch.append(rows[i]); i+=1
        for x in batch:
            level=int(x.get('number') or 0)
            if not level: continue
            prev=state.get(level,{})
            for k in ('pMeDem','pMeOf','qTitMeDem','qTitMeOf','zOrdMeDem','zOrdMeOf'):
                if x.get(k) is not None: prev[k]=x.get(k)
            state[level]=prev
        b=state.get(1,{})
        bid=n(b.get('pMeDem')); ask=n(b.get('pMeOf'))
        valid=bool(bid and ask and bid>0 and ask>0 and ask>=bid)
        if valid:
            mid=(bid+ask)/2
            out.append({'trade_date':deven,'hEven':h,'ins_code':ins,'bid':bid,'ask':ask,
                        'bid_size':n(b.get('qTitMeDem')),'ask_size':n(b.get('qTitMeOf')),
                        'bid_orders':n(b.get('zOrdMeDem')),'ask_orders':n(b.get('zOrdMeOf')),
                        'relative_spread':(ask-bid)/mid if mid else None,'quote_valid':True})
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--trades',default='results/trades_V3.csv'); ap.add_argument('--out',default='results/historical_option_bidask.csv'); ap.add_argument('--max-contracts',type=int,default=60); a=ap.parse_args()
    t=pd.read_csv(a.trades); dates=sorted(set(pd.to_numeric(t.entry_date,errors='coerce').dropna().astype(int)))
    contracts=discover(); print('contracts_discovered=',len(contracts))
    allrows=[]; manifest=[]
    for symbol,ins in list(sorted(contracts.items()))[:a.max_contracts]:
        try:
            lo,hi=active_range(ins); eligible=[d for d in dates if lo and lo<=d<=hi]
            count=0
            for d in eligible:
                try:
                    rr=reconstruct(ins,d)
                    for r in rr: r['option_symbol']=symbol
                    allrows.extend(rr); count+=len(rr); time.sleep(.12)
                except Exception: pass
            manifest.append({'option_symbol':symbol,'ins_code':ins,'history_start':lo,'history_end':hi,'v3_entry_dates_in_life':len(eligible),'reconstructed_quotes':count})
        except Exception as e:
            manifest.append({'option_symbol':symbol,'ins_code':ins,'error':str(e)[:160]})
    out=pd.DataFrame(allrows); Path(a.out).parent.mkdir(parents=True,exist_ok=True); out.to_csv(a.out,index=False)
    pd.DataFrame(manifest).to_csv('results/historical_option_contract_manifest.csv',index=False)
    covered=out[out.quote_valid==True].trade_date.nunique() if len(out) else 0
    summary={'v3_entry_dates':len(dates),'contracts_discovered':len(contracts),'reconstructed_rows':len(out),'entry_dates_with_any_valid_quote':int(covered),
             'status':'DISCOVERY_ONLY','rule':'Historical BestLimits is reconstructed statefully; no Last/Close substitution.'}
    Path('results/historical_option_reconstruction_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8'); print(json.dumps(summary,indent=2))
if __name__=='__main__': main()
