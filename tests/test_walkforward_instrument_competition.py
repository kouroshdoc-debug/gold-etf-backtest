import sys
sys.path.insert(0,'src')
import pandas as pd
from walkforward_instrument_competition import eligible_quotes

def run():
    assert eligible_quotes(None,20260101).empty
    q=pd.DataFrame([{'entry_date':20260101,'snapshot_ts':'2026-01-01T09:00:00+03:30','symbol':'X','kind':'CALL','S':100,'K':100,'T':.1,'iv':.3,'bid':3,'ask':4,'delta':.5,'relative_spread':.28,'quote_valid':True},
                    {'entry_date':20260102,'snapshot_ts':'2026-01-02T09:00:00+03:30','symbol':'Y','kind':'CALL','S':100,'K':100,'T':.1,'iv':.3,'bid':3,'ask':4,'delta':.5,'relative_spread':.28,'quote_valid':False}])
    z=eligible_quotes(q,20260101);assert len(z)==1 and z.iloc[0].symbol=='X'
    assert eligible_quotes(q,20260102).empty
    print('PASS walk-forward admission gate')
if __name__=='__main__':run()
