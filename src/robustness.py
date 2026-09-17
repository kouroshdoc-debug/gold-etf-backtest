import json
from pathlib import Path
import numpy as np
import pandas as pd
from backtest import trade_log, metrics

def bootstrap(returns,trials,seed,ruin):
    r=np.asarray(returns,dtype=float);rng=np.random.default_rng(seed);terminal=[];mdd=[]
    for _ in range(trials):
        sample=rng.choice(r,size=len(r),replace=True);eq=np.cumprod(1+sample);dd=eq/np.maximum.accumulate(eq)-1
        terminal.append(eq[-1]-1);mdd.append(dd.min())
    terminal=np.asarray(terminal);mdd=np.asarray(mdd)
    return {"trials":trials,"terminal_p05":np.quantile(terminal,.05),"terminal_median":np.median(terminal),"terminal_p95":np.quantile(terminal,.95),"probability_loss":np.mean(terminal<0),"mdd_worst_5pct":np.quantile(mdd,.05),"median_mdd":np.median(mdd),"probability_ruin":np.mean(mdd<=ruin)}

def sequence_risk(returns,trials,seed):
    r=np.asarray(returns,dtype=float);rng=np.random.default_rng(seed);mdd=[]
    for _ in range(trials):
        eq=np.cumprod(1+rng.permutation(r));dd=eq/np.maximum.accumulate(eq)-1;mdd.append(dd.min())
    return {"sequence_mdd_worst_5pct":np.quantile(mdd,.05),"sequence_mdd_median":np.median(mdd)}

def load_historical_cash(path,dates):
    rates=pd.read_csv(path)
    required={"date","annual_rate"}
    if not required.issubset(rates.columns):raise ValueError("historical cash file needs date,annual_rate")
    rates=rates[list(required)].copy();rates["date"]=pd.to_numeric(rates["date"],errors="raise").astype(int);rates["annual_rate"]=pd.to_numeric(rates["annual_rate"],errors="raise")
    if rates["date"].duplicated().any() or not rates["date"].is_monotonic_increasing:raise ValueError("historical cash dates must be unique and ascending")
    if ((rates["annual_rate"]<=-1)|(rates["annual_rate"]>2)).any():raise ValueError("annual_rate outside (-1, 2]")
    aligned=pd.DataFrame({"date":pd.Series(dates,dtype=int)}).merge(rates,on="date",how="left")["annual_rate"].ffill()
    if aligned.isna().any():raise ValueError("historical cash rate must start on/before the first market date")
    return aligned

def main():
    cfg=json.load(open("config.json",encoding="utf-8"));b=cfg["backtest"];r=cfg["robustness"];df=pd.read_csv("data/tala_history.csv");years=(len(df)-1)/252;Path("results").mkdir(exist_ok=True)
    defaults={"thr":10,"trend":200,"dev":b["v5_last_close_deviation"]};scenarios=[];boot=[]
    for v in [f"V{i}" for i in range(6)]:
        for cash in r["cash_yields"]:
            for slip in r["one_way_slippage"]:
                cost=b["one_way_cost"]+slip;t=trade_log(df,v,**defaults,cost=cost);m=metrics(t,years,df,cost,cash)
                scenarios.append({"version":v,"cash_yield":cash,"one_way_slippage":slip,"total_one_way_friction":cost,**m})
        t=trade_log(df,v,**defaults,cost=b["one_way_cost"])
        if len(t)>=10:boot.append({"version":v,**bootstrap(t["return"],r["bootstrap_trials"],b["seed"],r["ruin_drawdown"]),**sequence_risk(t["return"],r["bootstrap_trials"],b["seed"]+1)})
    pd.DataFrame(scenarios).to_csv("results/cash_slippage.csv",index=False);pd.DataFrame(boot).to_csv("results/bootstrap_monte_carlo.csv",index=False)
    cash_path=Path(r.get("historical_cash_file","data/cash_annual_rate.csv"))
    status={"available":cash_path.exists(),"path":str(cash_path)}
    if cash_path.exists():
        rates=load_historical_cash(cash_path,df.date);historical=[]
        for v in [f"V{i}" for i in range(6)]:
            t=trade_log(df,v,**defaults,cost=b["one_way_cost"]);m=metrics(t,years,df,b["one_way_cost"],cash_annual_rate=rates)
            historical.append({"version":v,**m})
        pd.DataFrame(historical).to_csv("results/historical_cash.csv",index=False);status["rows"]=len(rates)
    else:status["reason"]="No historical rate file supplied; scenario yields remain sensitivity tests, not historical facts."
    Path("results/historical_cash_status.json").write_text(json.dumps(status,indent=2),encoding="utf-8")
    print(pd.DataFrame(boot).to_string(index=False))

if __name__=="__main__":main()
