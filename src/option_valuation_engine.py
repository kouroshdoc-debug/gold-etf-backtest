"""Black-Scholes research valuation for admitted option snapshots.
Computes executable-mid diagnostics, IV and Greeks; never creates a fill price.
For ETF-linked calls, carry/dividend yield is explicit and configurable.
"""
from __future__ import annotations
import math
from statistics import NormalDist
ND=NormalDist()

def _d1(S,K,T,r,q,sigma): return (math.log(S/K)+(r-q+.5*sigma*sigma)*T)/(sigma*math.sqrt(T))
def bs_call(S,K,T,r,sigma,q=0.0):
    if min(S,K,T,sigma)<=0:return float('nan')
    d1=_d1(S,K,T,r,q,sigma); d2=d1-sigma*math.sqrt(T)
    return S*math.exp(-q*T)*ND.cdf(d1)-K*math.exp(-r*T)*ND.cdf(d2)
def implied_vol_call(price,S,K,T,r,q=0.0,lo=1e-4,hi=5.0,iters=120):
    intrinsic=max(0.0,S*math.exp(-q*T)-K*math.exp(-r*T))
    if price<intrinsic or price<=0:return float('nan')
    if bs_call(S,K,T,r,hi,q)<price:return float('nan')
    for _ in range(iters):
        mid=(lo+hi)/2
        if bs_call(S,K,T,r,mid,q)>price:hi=mid
        else:lo=mid
    return (lo+hi)/2
def call_greeks(S,K,T,r,sigma,q=0.0):
    d1=_d1(S,K,T,r,q,sigma); d2=d1-sigma*math.sqrt(T)
    pdf=math.exp(-.5*d1*d1)/math.sqrt(2*math.pi)
    delta=math.exp(-q*T)*ND.cdf(d1)
    gamma=math.exp(-q*T)*pdf/(S*sigma*math.sqrt(T))
    vega=S*math.exp(-q*T)*pdf*math.sqrt(T)/100
    theta=(-S*math.exp(-q*T)*pdf*sigma/(2*math.sqrt(T))-r*K*math.exp(-r*T)*ND.cdf(d2)+q*S*math.exp(-q*T)*ND.cdf(d1))/365
    return {'delta':delta,'gamma':gamma,'vega_per_vol_point':vega,'theta_per_day':theta}
