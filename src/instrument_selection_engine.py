"""Research-only instrument selection engine.
Compares ETF, long call, bull-call spread and NO_TRADE under scenario EV.
No live trading. No Last/Close substitution for option execution.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from math import exp
from typing import Iterable

from option_greeks import bs_call

@dataclass(frozen=True)
class Scenario:
    name: str
    probability: float
    underlying_return: float
    iv_multiplier: float = 1.0

@dataclass
class Candidate:
    name: str
    kind: str
    entry_cost: float
    max_loss: float
    delta_notional: float
    scenario_pnl: dict
    ev: float
    downside_ev: float
    risk_score: float
    ev_per_risk: float
    accepted: bool
    reason: str = ""


def _validate_scenarios(xs: Iterable[Scenario]):
    xs=list(xs)
    if not xs: raise ValueError("scenarios required")
    p=sum(x.probability for x in xs)
    if abs(p-1)>1e-6: raise ValueError("scenario probabilities must sum to 1")
    if any(x.probability<0 for x in xs): raise ValueError("negative probability")
    return xs


def _stats(pnls, scenarios, max_loss):
    ev=sum(s.probability*pnls[s.name] for s in scenarios)
    downside=sum(s.probability*min(pnls[s.name],0) for s in scenarios)
    # risk denominator combines hard capital-at-risk with expected downside magnitude.
    risk=max(1e-12, 0.5*max_loss + 0.5*abs(downside))
    return ev,downside,risk,ev/risk


def etf_candidate(S, scenarios, roundtrip_cost=0.0045):
    pnls={s.name:S*s.underlying_return-S*roundtrip_cost for s in scenarios}
    ev,dn,r,ratio=_stats(pnls,scenarios,S)
    return Candidate("ETF","ETF",S,S,S,pnls,ev,dn,r,ratio,True)


def call_candidate(symbol,S,K,T,iv,ask,delta,scenarios,r=0.0,fee_rt=0.002,exit_spread_fraction=0.5,rel_spread=0.0):
    if ask<=0 or iv<=0 or not (0<delta<1) or T<=0:
        return Candidate(symbol,"LONG_CALL",0,0,0,{},float('-inf'),0,1,float('-inf'),False,"invalid inputs")
    entry=ask*(1+fee_rt/2)
    pnls={}
    for s in scenarios:
        S1=S*(1+s.underlying_return); T1=max(T-5/365,1/365); iv1=max(.01,iv*s.iv_multiplier)
        exit_mid=bs_call(S1,K,T1,r,iv1)
        exit_exec=max(0,exit_mid*(1-exit_spread_fraction*rel_spread))*(1-fee_rt/2)
        pnls[s.name]=exit_exec-entry
    ev,dn,risk,ratio=_stats(pnls,scenarios,entry)
    return Candidate(symbol,"LONG_CALL",entry,entry,delta*S,pnls,ev,dn,risk,ratio,True)


def bull_call_spread_candidate(name,S,K_long,K_short,T,iv_long,iv_short,ask_long,bid_short,delta_long,delta_short,scenarios,r=0.0,fee_rt=0.002,long_rel_spread=0.0,short_rel_spread=0.0):
    debit=ask_long-bid_short
    if debit<=0 or K_short<=K_long or T<=0 or not (0<delta_short<delta_long<1):
        return Candidate(name,"BULL_CALL_SPREAD",0,0,0,{},float('-inf'),0,1,float('-inf'),False,"invalid spread")
    entry=debit*(1+fee_rt)
    pnls={}
    for s in scenarios:
        S1=S*(1+s.underlying_return); T1=max(T-5/365,1/365)
        long_mid=bs_call(S1,K_long,T1,r,max(.01,iv_long*s.iv_multiplier))
        short_mid=bs_call(S1,K_short,T1,r,max(.01,iv_short*s.iv_multiplier))
        long_exit=max(0,long_mid*(1-.5*long_rel_spread))
        short_cover=max(0,short_mid*(1+.5*short_rel_spread))
        exit_value=max(0,long_exit-short_cover)*(1-fee_rt)
        pnls[s.name]=exit_value-entry
    ev,dn,risk,ratio=_stats(pnls,scenarios,entry)
    return Candidate(name,"BULL_CALL_SPREAD",entry,entry,(delta_long-delta_short)*S,pnls,ev,dn,risk,ratio,True)


def normalize(c: Candidate, mode="risk_budget", target=1.0):
    if not c.accepted: return c,0.0
    if mode=="capital": denom=c.entry_cost
    elif mode=="delta": denom=abs(c.delta_notional)
    elif mode=="risk_budget": denom=c.risk_score
    else: raise ValueError("mode must be capital, delta or risk_budget")
    scale=target/max(denom,1e-12)
    return c,scale


def select(candidates, mode="risk_budget", min_ev=0.0, min_ev_per_risk=0.0):
    eligible=[]
    for c in candidates:
        if c.accepted and c.ev>min_ev and c.ev_per_risk>min_ev_per_risk:
            _,scale=normalize(c,mode,1.0)
            score=c.ev*scale
            eligible.append((score,c,scale))
    if not eligible:
        return {"selection":"NO_TRADE","normalization":mode,"score":0.0,"scale":0.0,"candidate":None}
    score,c,scale=max(eligible,key=lambda z:z[0])
    return {"selection":c.name,"kind":c.kind,"normalization":mode,"score":score,"scale":scale,"candidate":asdict(c)}

DEFAULT_SCENARIOS=[
    Scenario("down",.25,-.03,.90),
    Scenario("flat",.25,0.00,.85),
    Scenario("base",.35,.025,.90),
    Scenario("up",.15,.07,1.00),
]
