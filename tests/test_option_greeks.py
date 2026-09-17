import math
from src.option_greeks import bs_call, implied_vol_call, estimate_call_from_executable_quote

def test_iv_roundtrip():
    s=100.0; k=100.0; t=30/365; r=.30; q=0.0; sigma=.40
    p=bs_call(s,k,t,r,q,sigma)
    iv=implied_vol_call(p,s,k,t,r,q)
    assert abs(iv-sigma)<1e-5

def test_executable_mid_greeks():
    s=100.0; k=100.0; dte=30; r=.30; sigma=.40
    mid=bs_call(s,k,dte/365,r,0.0,sigma)
    g=estimate_call_from_executable_quote(bid=mid-.05,ask=mid+.05,underlying=s,strike=k,dte_days=dte,r=r)
    assert 0 < g.delta < 1
    assert g.gamma > 0
    assert g.vega_per_1pct > 0

def test_reject_crossed_quote():
    try:
        estimate_call_from_executable_quote(bid=12,ask=11,underlying=100,strike=100,dte_days=30)
    except ValueError:
        return
    raise AssertionError('crossed quote must be rejected')
