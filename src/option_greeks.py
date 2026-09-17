"""Implied-volatility and Greeks engine for option research.
Research only. Contract multiplier/style/settlement are intentionally NOT hard-coded
until authoritative exchange specifications are verified.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from statistics import NormalDist

N=NormalDist()

@dataclass(frozen=True)
class Greeks:
    iv: float
    delta: float
    gamma: float
    theta_per_day: float
    vega_per_1pct: float

def _d1d2(s,k,t,r,q,sigma):
    if min(s,k,t,sigma)<=0: raise ValueError('positive s,k,t,sigma required')
    d1=(math.log(s/k)+(r-q+0.5*sigma*sigma)*t)/(sigma*math.sqrt(t))
    return d1,d1-sigma*math.sqrt(t)

def bs_call(s,k,t,r,q,sigma):
    d1,d2=_d1d2(s,k,t,r,q,sigma)
    return s*math.exp(-q*t)*N.cdf(d1)-k*math.exp(-r*t)*N.cdf(d2)

def call_greeks(s,k,t,r,q,sigma):
    d1,d2=_d1d2(s,k,t,r,q,sigma)
    pdf=math.exp(-0.5*d1*d1)/math.sqrt(2*math.pi)
    delta=math.exp(-q*t)*N.cdf(d1)
    gamma=math.exp(-q*t)*pdf/(s*sigma*math.sqrt(t))
    theta_year=(-s*math.exp(-q*t)*pdf*sigma/(2*math.sqrt(t))
                -r*k*math.exp(-r*t)*N.cdf(d2)
                +q*s*math.exp(-q*t)*N.cdf(d1))
    vega=s*math.exp(-q*t)*pdf*math.sqrt(t)
    return delta,gamma,theta_year/365.0,vega*0.01

def implied_vol_call(price,s,k,t,r=0.0,q=0.0,lo=1e-4,hi=5.0,tol=1e-8,max_iter=200):
    intrinsic=max(0.0,s*math.exp(-q*t)-k*math.exp(-r*t))
    upper=s*math.exp(-q*t)
    if not (intrinsic <= price <= upper): raise ValueError('call price violates no-arbitrage bounds')
    flo=bs_call(s,k,t,r,q,lo)-price; fhi=bs_call(s,k,t,r,q,hi)-price
    if flo*fhi>0: raise ValueError('IV not bracketed')
    for _ in range(max_iter):
        mid=(lo+hi)/2; f=bs_call(s,k,t,r,q,mid)-price
        if abs(f)<tol: return mid
        if flo*f<=0: hi=mid; fhi=f
        else: lo=mid; flo=f
    return (lo+hi)/2

def estimate_call_from_executable_quote(*,bid,ask,underlying,strike,dte_days,r=0.0,q=0.0):
    if bid is None or ask is None or float(ask)<=0 or float(bid)<0 or float(ask)<float(bid):
        raise ValueError('invalid executable quote')
    if dte_days<=0: raise ValueError('positive DTE required')
    mid=(float(bid)+float(ask))/2
    t=dte_days/365.0
    iv=implied_vol_call(mid,float(underlying),float(strike),t,r,q)
    d,g,th,v=call_greeks(float(underlying),float(strike),t,r,q,iv)
    return Greeks(iv,d,g,th,v)
