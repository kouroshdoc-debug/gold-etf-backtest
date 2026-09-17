import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from backtest import rsi, signals

def state(df,version,thr=10,trend=200,dev=-.002):
    x,e=signals(df,version,thr,trend,dev)
    if version=="V0":return True,"HOLD"
    pos=False
    for i in range(1,len(df)):
        if not pos and bool(x.iloc[i-1]):pos=True
        elif pos and bool(e.iloc[i-1]):pos=False
    if not pos and bool(x.iloc[-1]):action="BUY_NEXT_OPEN"
    elif pos and bool(e.iloc[-1]):action="SELL_NEXT_OPEN"
    else:action="HOLD" if pos else "CASH"
    return pos,action

def main():
    cfg=json.load(open("config.json",encoding="utf-8"));b=cfg["backtest"];df=pd.read_csv("data/tala_history.csv");c=df.close;l=df["last"]
    as_of=int(df.date.iloc[-1]);data_date=datetime.strptime(str(as_of),"%Y%m%d").replace(tzinfo=timezone.utc);age=(datetime.now(timezone.utc)-data_date).days;fresh=age<=5
    common={"as_of_date":as_of,"data_age_days":age,"data_fresh":fresh,"close":float(c.iloc[-1]),"last":float(l.iloc[-1]),"rsi2_close":float(rsi(c,2).iloc[-1]),"rsi2_last":float(rsi(l,2).iloc[-1]),"sma5_close":float(c.rolling(5).mean().iloc[-1]),"sma200_close":float(c.rolling(200).mean().iloc[-1]),"last_close_deviation":float(df.last_close_deviation.iloc[-1])}
    rows=[]
    for v in [f"V{i}" for i in range(6)]:
        invested,action=state(df,v,10,200,b["v5_last_close_deviation"]);rows.append({**common,"version":v,"invested_before_next_open":invested,"next_open_action":action if fresh else "STALE_DATA"})
    Path("results").mkdir(exist_ok=True);pd.DataFrame(rows).to_csv("results/forward_signal.csv",index=False);Path("results/forward_signal.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8");print(pd.DataFrame(rows)[["version","invested_before_next_open","next_open_action"]].to_string(index=False))

if __name__=="__main__":main()
