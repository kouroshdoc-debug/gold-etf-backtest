"""Iran-side Lotus option collector. Research/shadow only.
Collects executable Level-1 Bid/Ask with Tehran timestamps; never substitutes Last/Close.
Designed to run from an Iran-reachable machine and append durable CSV snapshots.
"""
from __future__ import annotations
import csv, json, os, time, hashlib
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

TZ=ZoneInfo('Asia/Tehran')
OUT=Path(os.getenv('OPTION_SNAPSHOT_OUT','data/option_snapshots_gated.csv'))
HEALTH=Path(os.getenv('OPTION_HEALTH_OUT','data/option_collector_health.json'))
INTERVAL=max(20,int(os.getenv('OPTION_INTERVAL_SECONDS','60')))
ROUNDS=max(1,int(os.getenv('OPTION_ROUNDS','1')))
TIMEOUT=float(os.getenv('OPTION_HTTP_TIMEOUT','12'))
WEBGW='https://webgw.tse.ir'
FIELDS=['captured_at_tehran','trade_date','provider','symbol','isin','contract_type','strike','expiry','dte','contract_size','bid','ask','bid_size','ask_size','relative_spread','quote_valid','source_hash']

def get_json(url):
    r=requests.get(url,timeout=TIMEOUT,headers={'User-Agent':'gold-etf-research/1.0'}); r.raise_for_status(); return r.json()

def walk(x):
    if isinstance(x,dict):
        yield x
        for v in x.values(): yield from walk(v)
    elif isinstance(x,list):
        for v in x: yield from walk(v)

def pick(d,*keys):
    low={str(k).lower():v for k,v in d.items()}
    for k in keys:
        if k.lower() in low and low[k.lower()] not in (None,''): return low[k.lower()]
    return None

def num(v):
    try: return float(str(v).replace(',',''))
    except: return None

def discover():
    # WebGW endpoint shapes can evolve; parse defensively and fail closed.
    payload=get_json(WEBGW+'/api/MarketData/GetMarketWatchOption')
    found=[]
    for d in walk(payload):
        sym=pick(d,'symbol','lVal18AFC','instrumentSymbol','tradeSymbol')
        if not sym: continue
        sym=str(sym).strip()
        # Lotus gold options historically use TL* families; broad enough for discovery, metadata gate follows.
        if not (sym.upper().startswith('TL') or 'طلا' in str(d) or 'لوتوس' in str(d)): continue
        isin=pick(d,'isin','cIsin','instrumentId')
        strike=num(pick(d,'strike','strikePrice','priceStrike'))
        expiry=pick(d,'expiry','expirationDate','endDate','lastTradeDate')
        dte=num(pick(d,'dte','daysToExpiration','remainedDays'))
        csize=num(pick(d,'contractSize','contractUnit','size'))
        typ=pick(d,'optionType','contractType','type')
        bid=num(pick(d,'bid','bestBuyPrice','buyPrice','pMeDem'))
        ask=num(pick(d,'ask','bestSellPrice','sellPrice','pMeOf'))
        bsz=num(pick(d,'bidSize','buyVolume','qTitMeDem'))
        asz=num(pick(d,'askSize','sellVolume','qTitMeOf'))
        # only rows with explicit two-sided executable book survive.
        valid=bool(bid and ask and bid>0 and ask>=bid)
        if not valid: continue
        found.append(dict(symbol=sym,isin=isin,contract_type=typ,strike=strike,expiry=expiry,dte=dte,contract_size=csize,bid=bid,ask=ask,bid_size=bsz,ask_size=asz))
    # de-duplicate identical symbol/book states
    uniq={}
    for r in found: uniq[(r['symbol'],r['bid'],r['ask'],r.get('bid_size'),r.get('ask_size'))]=r
    return list(uniq.values()),payload

def append_rows(rows,payload):
    OUT.parent.mkdir(parents=True,exist_ok=True)
    new=not OUT.exists()
    now=datetime.now(TZ); raw=json.dumps(payload,ensure_ascii=False,sort_keys=True,default=str)
    sh=hashlib.sha256(raw.encode()).hexdigest()
    with OUT.open('a',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS)
        if new: w.writeheader()
        for r in rows:
            spread=(r['ask']-r['bid'])/((r['ask']+r['bid'])/2) if r['ask']+r['bid'] else None
            w.writerow({'captured_at_tehran':now.isoformat(timespec='seconds'),'trade_date':now.strftime('%Y%m%d'),'provider':'webgw','symbol':r['symbol'],'isin':r.get('isin'),'contract_type':r.get('contract_type'),'strike':r.get('strike'),'expiry':r.get('expiry'),'dte':r.get('dte'),'contract_size':r.get('contract_size'),'bid':r['bid'],'ask':r['ask'],'bid_size':r.get('bid_size'),'ask_size':r.get('ask_size'),'relative_spread':spread,'quote_valid':True,'source_hash':sh})
    return sh

def main():
    HEALTH.parent.mkdir(parents=True,exist_ok=True)
    for i in range(ROUNDS):
        t0=time.time()
        try:
            rows,payload=discover(); sh=append_rows(rows,payload)
            status={'captured_at_tehran':datetime.now(TZ).isoformat(timespec='seconds'),'status':'OK' if rows else 'NO_EXECUTABLE_QUOTES','valid_rows':len(rows),'latency_s':round(time.time()-t0,3),'source_hash':sh,'rule':'Bid/Ask only; no Last/Close substitution.'}
        except Exception as e:
            status={'captured_at_tehran':datetime.now(TZ).isoformat(timespec='seconds'),'status':'SOURCE_UNAVAILABLE','valid_rows':0,'latency_s':round(time.time()-t0,3),'error':repr(e),'rule':'Fail closed.'}
        HEALTH.write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(status,ensure_ascii=False))
        if i+1<ROUNDS: time.sleep(INTERVAL)
if __name__=='__main__': main()
