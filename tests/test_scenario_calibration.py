import sys
sys.path.insert(0,'src')
import pandas as pd
from scenario_calibration import calibrate

def run():
    t=pd.DataFrame({'entry_date':range(100,140),'exit_date':range(101,141),'return':[(-.04+i*.003) for i in range(40)]})
    c=calibrate(t,asof=130,min_trades=20,shrink_n=20)
    assert c['n_completed']==29
    assert abs(sum(x['probability_shrunk'] for x in c['scenarios'])-1)<1e-12
    cuts=c['quantile_cuts']; assert cuts['q25']<=cuts['q50']<=cuts['q85']
    # Future returns must not change calibration at an earlier as-of date.
    t2=t.copy(); t2.loc[t2.exit_date>=130,'return']=99
    c2=calibrate(t2,asof=130,min_trades=20,shrink_n=20)
    assert c['quantile_cuts']==c2['quantile_cuts']
    print('PASS scenario calibration anti-lookahead')
if __name__=='__main__': run()
