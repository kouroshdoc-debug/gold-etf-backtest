import argparse,json
from pathlib import Path
import numpy as np
import pandas as pd

def rsi(s,n=2):
    d=s.diff();up=d.clip(lower=0);dn=-d.clip(upper=0);au=up.ewm(alpha=1/n,adjust=False,min_periods=n).mean();ad=dn.ewm(alpha=1/n,adjust=False,min_periods=n).mean();out=100-100/(1+au/ad.replace(0,np.nan));return out.mask((ad==0)&(au>0),100).mask((ad==0)&(au==0),50)
def signals(df,v,thr=10,trend=200,dev=-.002):
    c=df.close;last=df["last"];x=pd.Series(False,index=df.index);e=pd.Series(False,index=df.index);s5=c.rolling(5).mean();st=c.rolling(trend).mean()
    if v=="V0":x.iloc[0]=True
    elif v=="V1":x=c>st;e=c<st
    elif v=="V2":x=rsi(c)<thr;e=c>s5
    elif v=="V3":x=rsi(last)<thr;e=last>last.rolling(5).mean()
    elif v=="V4":x=(rsi(c)<thr)&(c>st);e=c>s5
    elif v=="V5":x=(rsi(c)<thr)&(c>st)&(df.last_close_deviation<=dev);e=c>s5
    return x.fillna(False),e.fillna(False)
def trade_log(df,v,thr=10,trend=200,dev=-.002,cost=.00125,start=0,end=None):
    end=len(df) if end is None else end
    if v=="V0":
        i=max(start,0);j=end-1
        if j<=i:return pd.DataFrame()
        ret=(float(df.open.iloc[j])*(1-cost))/(float(df.open.iloc[i])*(1+cost))-1
        return pd.DataFrame([{"entry_i":i,"exit_i":j,"entry_date":int(df.date.iloc[i]),"exit_date":int(df.date.iloc[j]),"entry":float(df.open.iloc[i]),"exit":float(df.open.iloc[j]),"holding_days":j-i,"return":ret}])
    x,e=signals(df,v,thr,trend,dev);pos=False;ent=None;rows=[]
    for i in range(max(start,1),end):
        if not pos and bool(x.iloc[i-1]):ent=(i,float(df.open.iloc[i]));pos=True
        elif pos and (bool(e.iloc[i-1]) or i==end-1):
            ret=(float(df.open.iloc[i])*(1-cost))/(ent[1]*(1+cost))-1;rows.append({"entry_i":ent[0],"exit_i":i,"entry_date":int(df.date.iloc[ent[0]]),"exit_date":int(df.date.iloc[i]),"entry":ent[1],"exit":float(df.open.iloc[i]),"holding_days":i-ent[0],"return":ret});pos=False
    return pd.DataFrame(rows)
def equity_curve(df,t,cost,cash_rate=0.0,cash_annual_rate=None):
    curve=pd.Series(1.0,index=df.index,dtype=float);capital=1.0;cursor=0
    if cash_annual_rate is None:cash_growth=pd.Series((1+cash_rate)**(1/252),index=df.index,dtype=float)
    else:
        cash_growth=(1+pd.Series(cash_annual_rate,index=df.index,dtype=float))**(1/252)
        if cash_growth.isna().any():raise ValueError("cash annual-rate series has missing aligned dates")
    for row in t.itertuples():
        gap=row.entry_i-cursor
        if gap>0:
            curve.iloc[cursor:row.entry_i]=capital*cash_growth.iloc[cursor:row.entry_i].cumprod();capital=float(curve.iloc[row.entry_i-1])
        basis=row.entry*(1+cost)
        curve.iloc[row.entry_i:row.exit_i]=capital*df.close.iloc[row.entry_i:row.exit_i]/basis
        capital*=row.exit*(1-cost)/basis;curve.iloc[row.exit_i]=capital;cursor=row.exit_i+1
    gap=len(df)-cursor
    if gap>0:curve.iloc[cursor:]=capital*cash_growth.iloc[cursor:].cumprod()
    return curve
def metrics(t,years,df=None,cost=.00125,cash_rate=0.0,cash_annual_rate=None):
    if t.empty:return {"trades":0,"total_return":0,"cagr":0,"max_drawdown":0,"win_rate":0,"profit_factor":0,"exposure":0}
    eq=equity_curve(df,t,cost,cash_rate,cash_annual_rate) if df is not None else (1+t["return"]).cumprod();dd=eq/eq.cummax()-1;g=t.loc[t["return"]>0,"return"].sum();l=-t.loc[t["return"]<0,"return"].sum()
    return {"trades":len(t),"total_return":eq.iloc[-1]-1,"cagr":eq.iloc[-1]**(1/max(years,1/252))-1,"max_drawdown":dd.min(),"win_rate":(t["return"]>0).mean(),"profit_factor":g/l if l else np.inf,"exposure":t.holding_days.sum()/max(round(years*252),1)}
def random_benchmark(df,t,n,seed,cost):
    if t.empty:return {}
    rng=np.random.default_rng(seed);vals=[]
    for _ in range(n):
        rr=[]
        for h in t.holding_days.to_numpy():
            if h<len(df)-1:
                i=int(rng.integers(0,len(df)-h));rr.append((df.open.iloc[i+h]*(1-cost))/(df.open.iloc[i]*(1+cost))-1)
        if rr:vals.append(np.prod(1+np.array(rr))-1)
    if not vals:return {"random_median":np.nan,"random_p95":np.nan,"random_percentile":np.nan}
    actual=np.prod(1+t["return"])-1;return {"random_median":float(np.median(vals)),"random_p95":float(np.quantile(vals,.95)),"random_percentile":float(np.mean(np.array(vals)<=actual))}
def run(df,cfg):
    b=cfg["backtest"];years=max((len(df)-1)/252,1/252);summary=[];defaults={"thr":10,"trend":200,"dev":b["v5_last_close_deviation"]}
    for v in [f"V{i}" for i in range(6)]:
        t=trade_log(df,v,**defaults,cost=b["one_way_cost"]);m=metrics(t,years,df,b["one_way_cost"]);m.update(random_benchmark(df,t,b["random_trials"],b["seed"],b["one_way_cost"]));m.update({"version":v,"rsi_threshold":10,"trend_window":200});summary.append(m)
        if not t.empty:t.assign(version=v).to_csv(f"results/trades_{v}.csv",index=False)
    sens=[]
    for v in ["V2","V3","V4","V5"]:
        for th in b["rsi_thresholds"]:
            for tw in b["trend_windows"]:
                t=trade_log(df,v,th,tw,b["v5_last_close_deviation"],b["one_way_cost"]);sens.append({"version":v,"rsi_threshold":th,"trend_window":tw,**metrics(t,years,df,b["one_way_cost"])})
    cut=int(len(df)*(1-b["oos_fraction"]));oos=[]
    for v in [f"V{i}" for i in range(6)]:oos.append({"version":v,**metrics(trade_log(df,v,**defaults,cost=b["one_way_cost"],start=cut),(len(df)-cut)/252,df,b["one_way_cost"])})
    wf=[];train=756;test=252
    for end in range(train,len(df),test):
        stop=min(end+test,len(df))
        for v in ["V2","V3","V4","V5"]:
            cand=[]
            for th in b["rsi_thresholds"]:
                for tw in b["trend_windows"]:cand.append((metrics(trade_log(df,v,th,tw,b["v5_last_close_deviation"],b["one_way_cost"],0,end),end/252,df,b["one_way_cost"])["cagr"],th,tw))
            _,th,tw=max(cand,key=lambda z:z[0]);wf.append({"version":v,"test_start":int(df.date.iloc[end]),"test_end":int(df.date.iloc[stop-1]),"chosen_rsi":th,"chosen_sma":tw,**metrics(trade_log(df,v,th,tw,b["v5_last_close_deviation"],b["one_way_cost"],end,stop),(stop-end)/252,df,b["one_way_cost"])})
    return pd.DataFrame(summary),pd.DataFrame(sens),pd.DataFrame(oos),pd.DataFrame(wf)
def main():
    p=argparse.ArgumentParser();p.add_argument("--config",default="config.json");p.add_argument("--data",default="data/tala_history.csv");a=p.parse_args();cfg=json.load(open(a.config,encoding="utf-8"));df=pd.read_csv(a.data);Path("results").mkdir(exist_ok=True);s,se,o,w=run(df,cfg);s.to_csv("results/summary.csv",index=False);se.to_csv("results/sensitivity.csv",index=False);o.to_csv("results/oos.csv",index=False);w.to_csv("results/walk_forward.csv",index=False);Path("results/report.md").write_text("# Gold ETF backtest — V0 to V5\n\n```csv\n"+s.to_csv(index=False)+"```\n",encoding="utf-8");print(s.to_string(index=False))
if __name__=="__main__":main()
