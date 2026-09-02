import pandas as pd, numpy as np
from scipy import stats as st
m=pd.read_parquet('m1.parquet'); m['hr']=m.index.hour; m['tm']=m.index.hour*60+m.index.minute
D=pd.read_parquet('daily.parquet'); D.index=pd.to_datetime(D.index)
m=m[m['tday'].isin(set(D.index.date))].sort_index()
atr=(D['high']-D['low']).rolling(14).mean().shift()

days={}
for d,g in m.groupby('tday'):
    days[pd.Timestamp(d)]=(g['tm'].values,g['open'].values,g['high'].values,g['low'].values,g['close'].values)

SESS={'ASIA 18:05-02:00':(18*60+5,26*60),      # wraps midnight -> handled below
      'LONDON 02:00-08:00':(2*60,8*60),
      'NY AM 08:00-12:00':(8*60,12*60),
      'NY PM 12:00-17:00':(12*60,17*60)}

def window_mask(tm,a,b):
    if b<=24*60: return (tm>=a)&(tm<b)
    return (tm>=a)|(tm<(b-24*60))

def run_breakout(a,b,lookback=30,rr=1.5,stop_atr=0.35,spread=0.35,max_hold=180):
    """Honest intraday volatility breakout: break the prior `lookback`-minute range,
    ATR stop, fixed R target, flat at session end. Both directions."""
    tr=[]
    for d in D.index:
        if d not in days: continue
        A=atr.get(d,np.nan)
        if not np.isfinite(A) or A<=0: continue
        tm,o,h,l,c=days[d]
        w=np.where(window_mask(tm,a,b))[0]
        if len(w)<lookback+30: continue
        end=w[-1]
        i0=w[lookback]
        for i in w[lookback:]:
            lo=l[i-lookback:i].min(); hi=h[i-lookback:i].max()
            side=None
            if c[i]>hi: side='long'
            elif c[i]<lo: side='short'
            if side is None: continue
            entry=c[i]; risk=stop_atr*A
            stop=entry-risk if side=='long' else entry+risk
            tgt=entry+rr*risk if side=='long' else entry-rr*risk
            out=None
            horizon=[j for j in w if j>i][:max_hold]
            for j in horizon:
                if side=='long':
                    if l[j]<=stop: out=-1.0;break
                    if h[j]>=tgt: out=rr;break
                else:
                    if h[j]>=stop: out=-1.0;break
                    if l[j]<=tgt: out=rr;break
            if out is None and horizon:
                px=c[horizon[-1]]
                out=((px-entry) if side=='long' else (entry-px))/risk
            if out is None: break
            tr.append({'d':d,'side':side,'R':out-spread/risk,'risk':risk})
            break   # one trade per session per day
    return pd.DataFrame(tr)

print("===== 40. INTRADAY TRADE QUALITY BY SESSION (not holding drift) =====")
print("Volatility breakout, 0.35 ATR stop, 1.5R target, $0.35 cost, one trade/session/day\n")
rows=[]
for name,(a,b) in SESS.items():
    t=run_breakout(a,b)
    if len(t)<50: continue
    R=t['R']; yr=t['d'].dt.year
    rows.append({'session':name,'n':len(R),'win%':round((R>0).mean()*100,1),
        'exp_R':round(R.mean(),4),'total_R':round(R.sum(),1),
        'PF':round(R[R>0].sum()/abs(R[R<0].sum()),2),
        'median_stop_$':round(t['risk'].median(),2),
        'cost_as_R':round((0.35/t['risk']).mean(),3),
        'IS_exp':round(R[yr<=2021].mean(),3),'OOS_exp':round(R[yr>=2022].mean(),3)})
print(pd.DataFrame(rows).to_string(index=False))

print("\n===== 41. HOW FAR DOES PRICE ACTUALLY TRAVEL PER SESSION? (MFE potential) =====")
out=[]
for name,(a,b) in SESS.items():
    hh=[];ll=[];rr_=[]
    for d in D.index:
        if d not in days: continue
        A=atr.get(d,np.nan)
        if not np.isfinite(A) or A<=0: continue
        tm,o,h,l,c=days[d]
        w=np.where(window_mask(tm,a,b))[0]
        if len(w)<60: continue
        rng=h[w].max()-l[w].min()
        rr_.append(rng/A)
    out.append({'session':name,'n':len(rr_),'median_range_ATR':round(float(np.median(rr_)),3),
                'p90_range_ATR':round(float(np.percentile(rr_,90)),3)})
print(pd.DataFrame(out).to_string(index=False))
