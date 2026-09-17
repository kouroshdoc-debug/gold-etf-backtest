import argparse, io, json, subprocess
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
    candidates={"date":["dEven"],"open":["pFirst","priceFirst"],"high":["pMax","priceMax"],"low":["pMin","priceMin"],"last":["pLast","pDrCotVal"],"close":["pClosing"],"volume":["qTotTran5J"],"value":["qTotCap"],"trades":["zTotTran"]}
    chosen={dst:next((src for src in sources if src in df.columns),None) for dst,sources in candidates.items()}
    missing=[dst for dst,src in chosen.items() if src is None]
    if missing:raise ValueError(f"missing TSETMC fields: {missing}")
    out=pd.DataFrame({dst:df[src] for dst,src in chosen.items()})
    for c in out.columns:out[c]=pd.to_numeric(out[c],errors="coerce")
    out=out.dropna(subset=["date","open","last","close"]).drop_duplicates("date").sort_values("date").reset_index(drop=True)
    price_cols=["open","high","low","last","close"]; out=out[(out[price_cols]>0).all(axis=1)]
    out["last_close_deviation"]=out["last"]/out["close"]-1
    if len(out)<500:raise ValueError(f"history too short: {len(out)} rows")
    return out

def snapshot():
    parts=sorted(Path("data/snapshot").glob("tala.csv.part-*"))
    if not parts:raise FileNotFoundError("no repository snapshot parts")
    out=pd.read_csv(io.StringIO("".join(p.read_text(encoding="utf-8") for p in parts)))
    required={"date","open","high","low","last","close","volume","value","trades","last_close_deviation"}
    if not required.issubset(out.columns) or len(out)<500:raise ValueError("invalid repository snapshot")
    return out.sort_values("date").drop_duplicates("date").reset_index(drop=True)

def main():
    p=argparse.ArgumentParser();p.add_argument("--config",default="config.json");p.add_argument("--out",default="data/tala_history.csv");a=p.parse_args()
    cfg=json.load(open(a.config,encoding="utf-8"));source="TSETMC-live"
    try:data=clean(fetch(cfg["instrument"]["inscode"]))
    except Exception as exc:
        print(f"live download unavailable: {exc}");data=snapshot();source="repository-snapshot"
    Path(a.out).parent.mkdir(parents=True,exist_ok=True);data.to_csv(a.out,index=False)
    print(json.dumps({"source":source,"rows":len(data),"first":int(data.date.iloc[0]),"last":int(data.date.iloc[-1])},ensure_ascii=False))
if __name__=="__main__":main()
