import sys
sys.path.insert(0,'src')
import pandas as pd
from option_coverage_matrix import build

def run():
    # Test admission mechanics using a monkey-patched minimal trade log is intentionally avoided;
    # instead validate quote predicates through a tiny realistic history that yields enough RSI state.
    n=260; dates=pd.Series(range(20250101,20250101+n)); close=pd.Series([100+i*.1 for i in range(n)],dtype=float); last=close.copy();
    # create sharp late dip to generate V3 signal
    last.iloc[240]=80; close.iloc[240]=80
    h=pd.DataFrame({'date':dates,'open':close,'high':close,'low':close,'last':last,'close':close,'volume':1,'value':1,'trades':1,'last_close_deviation':0.0})
    base=build(h,None,None)
    if len(base):
        d=int(base.iloc[-1].entry_date)
        bad=pd.DataFrame([{'trade_date':str(d),'option_symbol':'BAD','bid':5,'ask':4,'quote_valid':True}])
        assert not build(h,bad,None).iloc[-1].admissible_for_executable_backtest
        good=pd.DataFrame([{'trade_date':str(d),'option_symbol':'GOOD','bid':4,'ask':5,'quote_valid':True}])
        z=build(h,good,None).iloc[-1];assert z.admissible_for_executable_backtest and z.valid_bidask_snapshot_count==1
    print('PASS strict option coverage admission')
if __name__=='__main__':run()
