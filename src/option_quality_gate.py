"""Quality gate for forward Lotus option snapshots. Research only."""
import argparse, csv, json, math
from pathlib import Path

def f(x):
    try: return float(x)
    except: return None

def assess(r, max_spread=.10, min_volume=1):
    reasons=[]; b=f(r.get('bid')); a=f(r.get('ask')); v=f(r.get('volume'))
    if b is None or a is None: reasons.append('MISSING_BID_ASK')
    elif b<0 or a<=0 or a<b: reasons.append('INVALID_BOOK')
    else:
        mid=(a+b)/2; spr=(a-b)/mid if mid>0 else math.inf
        if spr>max_spread: reasons.append('SPREAD_TOO_WIDE')
    if v is None or v<min_volume: reasons.append('LOW_OR_MISSING_VOLUME')
    return len(reasons)==0, reasons

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('input'); ap.add_argument('--out',default='results/option_quality.csv'); ap.add_argument('--max-spread',type=float,default=.10); a=ap.parse_args()
    rows=list(csv.DictReader(open(a.input,encoding='utf-8'))); out=[]
    for r in rows:
        ok,reasons=assess(r,a.max_spread); q=dict(r); q['quality_pass']=ok; q['quality_reasons']='|'.join(reasons); out.append(q)
    p=Path(a.out); p.parent.mkdir(parents=True,exist_ok=True)
    fields=list(out[0].keys()) if out else ['quality_pass','quality_reasons']
    with p.open('w',newline='',encoding='utf-8') as fh:
        w=csv.DictWriter(fh,fieldnames=fields); w.writeheader(); w.writerows(out)
    print(json.dumps({'rows':len(out),'passed':sum(str(x['quality_pass'])=='True' for x in out),'output':str(p)}))
if __name__=='__main__': main()
