import argparse, json, subprocess
from pathlib import Path
import pandas as pd

URLS = ["https://cdn.tsetmc.com/api/ClosingPrice/GetClosingPriceDailyList/{inscode}/0", "https://cdn.tsetmc.com/api/ClosingPrice/GetClosingPriceDailyList/{inscode}/1"]
LEGACY_URLS = [
    "https://old.tsetmc.com/tsev2/data/InstTradeHistory.aspx?i={inscode}&Top=999999&A=1",
    "http://www.tsetmc.com/tsev2/data/InstTradeHistory.aspx?i={inscode}&Top=999999&A=1",
    "http://members.tsetmc.com/tsev2/data/InstTradeHistory.aspx?i={inscode}&Top=999999&A=1",
]

def get_text(url):
    p=subprocess.run(["curl","-4","-fsSL","--connect-timeout","8","--max-time","25","-A","Mozilla/5.0 gold-etf-research/1.0",url],capture_output=True,text=True,timeout=30)
    if p.returncode:raise RuntimeError(p.stderr.strip() or f"curl exit {p.returncode}")
    return p.stdout

def fetch(inscode):
    errors=[]
    for url in URLS:
        try:
            payload=json.loads(get_text(url.format(inscode=inscode)));rows=payload.get("closingPriceDaily",payload if isinstance(payload,list) else [])
            if rows:return pd.DataFrame(rows)
            errors.append(f"{url}: empty payload")
        except Exception as exc:errors.append(f"{url}: {type(exc).__name__}: {exc}")
    for legacy in LEGACY_URLS:
        try:
            text=get_text(legacy.format(inscode=inscode));rows=[]
            for item in text.strip(";\n ").split(";"):
                f=item.split("@")
                if len(f)>=10:rows.append({"dEven":f[0],"pClosing":f[1],"pLast":f[2],"zTotTran":f[3],"qTotTran5J":f[4],"qTotCap":f[5],"pMin":f[6],"pMax":f[7],"pFirst":f[9]})
            if rows:return pd.DataFrame(rows)
            errors.append(f"{legacy}: empty payload")
        except Exception as exc:errors.append(f"{legacy}: {type(exc).__name__}: {exc}")
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
