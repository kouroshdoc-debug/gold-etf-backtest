import sys
sys.path.insert(0,'src')
from instrument_selection_engine import *

def run():
    sc=_validate_scenarios(DEFAULT_SCENARIOS)
    etf=etf_candidate(100,sc)
    assert etf.accepted and len(etf.scenario_pnl)==4
    # synthetic option inputs only: architecture test, not a performance result
    call=call_candidate('CALL100',100,100,30/365,.35,4.0,.55,sc,rel_spread=.04)
    spread=bull_call_spread_candidate('100-110',100,100,110,30/365,.35,.34,4.0,1.2,.55,.25,sc,long_rel_spread=.04,short_rel_spread=.06)
    assert call.accepted and spread.accepted
    for mode in ('capital','delta','risk_budget'):
        out=select([etf,call,spread],mode=mode)
        assert out['selection'] in ('ETF','CALL100','100-110','NO_TRADE')
    # No-trade gate must work when hurdle is impossible.
    out=select([etf,call,spread],mode='risk_budget',min_ev=1e9)
    assert out['selection']=='NO_TRADE'
    print('PASS instrument selection engine')

if __name__=='__main__': run()
