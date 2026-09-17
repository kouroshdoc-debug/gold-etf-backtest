"""Empirical scenario calibration for V3. Research only.
Uses only completed V3 trades available before an as-of date; designed to prevent lookahead.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd
from backtest import trade_log

BUCKETS=("down","flat","base","up")

def calibrate(trades, asof=None, min_trades=20, shrink_n=20):
    t=trades.copy()
    if asof is not None: t=t[t.exit_date < int(asof)]
    r=t["return"].dropna().astype(float).to_numpy()
    if len(r)<min_trades: raise ValueError(f"insufficient completed trades: {len(r)} < {min_trades}")
    q=np.quantile(r,[.25,.50,.85])
    cuts=[-np.inf,q[0],q[1],q[2],np.inf]
    labels=list(BUCKETS)
    raw=[]
    for i,name in enumerate(labels):
        x=r[(r>cuts[i]) & (r<=cuts[i+1])]
        raw.append({"name":name,"n":len(x),"probability":len(x)/len(r),"underlying_return":float(np.median(x)) if len(x) else 0.0})
    # Dirichlet-style shrinkage toward equal probabilities reduces small-sample overconfidence.
    alpha=shrink_n/len(labels)
    for z in raw: z["probability_shrunk"]=(z["n"]+alpha)/(len(r)+shrink_n)
    return {"n_completed":len(r),"asof":asof,"quantile_cuts":{"q25":float(q[0]),"q50":float(q[1]),"q85":float(q[2])},"scenarios":raw,
            "rules":{"anti_lookahead":"exit_date < asof","probability_shrink_n":shrink_n,"iv_multiplier":"not calibrated from ETF returns; must come from option snapshots"}}

def rolling_calibration(trades,min_train=30):
    rows=[]
    for i in range(min_train,len(trades)):
        asof=int(trades.iloc[i].entry_date)
        try:
            c=calibrate(trades,asof,min_trades=min_train)
            rows.append({"entry_date":asof,"n_train":c["n_completed"],**c["quantile_cuts"]})
        except ValueError: pass
    return pd.DataFrame(rows)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--data',default='data/tala_history.csv'); ap.add_argument('--out',default='results/v3_scenario_calibration.json'); ap.add_argument('--asof',type=int)
    a=ap.parse_args(); df=pd.read_csv(a.data); t=trade_log(df,'V3',thr=10,trend=200,dev=-.002,cost=.00125)
    c=calibrate(t,a.asof); Path(a.out).parent.mkdir(parents=True,exist_ok=True); Path(a.out).write_text(json.dumps(c,indent=2),encoding='utf-8')
    rolling_calibration(t).to_csv('results/v3_scenario_walkforward.csv',index=False)
    print(json.dumps(c,indent=2))
if __name__=='__main__': main()
