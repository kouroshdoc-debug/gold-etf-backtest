import argparse, json, time
from pathlib import Path
import pandas as pd
from urllib.request import Request, urlopen

URLS = ["https://cdn.tsetmc.com/api/ClosingPrice/GetClosingPriceDailyList/{inscode}/0", "https://cdn.tsetmc.com/api/ClosingPrice/GetClosingPriceDailyList/{inscode}/1"]

def fetch(inscode):
    headers={"User-Agent":"Mozilla/5.0 gold-etf-research/1.0","Accept":"application/json"}; errors=[]
    for url in URLS:
        for attempt in range(4):
            try:
                req=Request(url.format(inscode=inscode),headers=headers)
                with urlopen(req,timeout=45) as response:payload=json.loads(response.read().decode("utf-8"))
                rows=payload.get("closingPriceDaily",payload if isinstance(payload,list) else [])
                if rows:return pd.DataFrame(rows)
                errors.append(f"{url}: empty payload")
            except Exception as exc:
                errors.append(f"{url}: {type(exc).__name__}: {exc}"); time.sleep(2**attempt)
    raise RuntimeError("TSETMC download failed\n"+"\n".join(errors))

def clean(df):
    aliases={"dEven":"date","pFirst":"open","pMax":"high","pMin":"low","pLast":"last","pClosing":"close","qTotTran5J":"volume","qTotCap":"value","zTotTran":"trades"}
    missing=[x for x in aliases if x not in df.columns]
    if missing:raise ValueError(f"missing TSETMC fields: {missing}")
    out=df.rename(columns=aliases)[list(aliases.values())].copy()
    for c in out.columns:out[c]=pd.to_numeric(out[c],errors="coerce")
    out=out.dropna(subset=["date","open","last","close"]).drop_duplicates("date").sort_values("date").reset_index(drop=True)
    price_cols=["open","high","low","last","close"]; out=out[(out[price_cols]>0).all(axis=1)]
    out["last_close_deviation"]=out["last"]/out["close"]-1
    if len(out)<500:raise ValueError(f"history too short: {len(out)} rows")
    return out

def main():
    p=argparse.ArgumentParser();p.add_argument("--config",default="config.json");p.add_argument("--out",default="data/tala_history.csv");a=p.parse_args()
    cfg=json.load(open(a.config,encoding="utf-8"));data=clean(fetch(cfg["instrument"]["inscode"]));Path(a.out).parent.mkdir(parents=True,exist_ok=True);data.to_csv(a.out,index=False)
    print(json.dumps({"rows":len(data),"first":int(data.date.iloc[0]),"last":int(data.date.iloc[-1])},ensure_ascii=False))
if __name__=="__main__":main()
