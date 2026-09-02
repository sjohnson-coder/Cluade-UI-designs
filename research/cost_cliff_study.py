import pandas as pd, numpy as np
m=pd.read_parquet('m1.parquet'); m['tm']=m.index.hour*60+m.index.minute
D=pd.read_parquet('daily.parquet'); D.index=pd.to_datetime(D.index)
m=m[m['tday'].isin(set(D.index.date))].sort_index()
atr=(D['high']-D['low']).rolling(14).mean().shift()
days={pd.Timestamp(d):(g['tm'].values,g['high'].values,g['low'].values,g['close'].values)
      for d,g in m.groupby('tday')}
SESS={'ASIA':(18*60+5,26*60),'LONDON':(2*60,8*60),'NY AM':(8*60,12*60),'NY PM':(12*60,17*60)}
def wm(tm,a,b): return (tm>=a)&(tm<b) if b<=24*60 else (tm>=a)|(tm<(b-24*60))

def run(a,b,mode,lookback=30,rr=1.5,stop_atr=0.35,spread=0.35,max_hold=180):
    tr=[]
    for d in D.index:
        if d not in days: continue
        A=atr.get(d,np.nan)
        if not np.isfinite(A) or A<=0: continue
        tm,h,l,c=days[d]
        w=np.where(wm(tm,a,b))[0]
        if len(w)<lookback+30: continue
        for i in w[lookback:]:
            lo=l[i-lookback:i].min(); hi=h[i-lookback:i].max()
            side=None
            if c[i]>hi: side='long' if mode=='breakout' else 'short'
            elif c[i]<lo: side='short' if mode=='breakout' else 'long'
            if side is None: continue
            entry=c[i]; risk=stop_atr*A
            stop=entry-risk if side=='long' else entry+risk
            tgt=entry+rr*risk if side=='long' else entry-rr*risk
            out=None; horizon=[j for j in w if j>i][:max_hold]
            for j in horizon:
                if side=='long':
                    if l[j]<=stop: out=-1.0;break
                    if h[j]>=tgt: out=rr;break
                else:
                    if h[j]>=stop: out=-1.0;break
                    if l[j]<=tgt: out=rr;break
            if out is None and horizon:
                px=c[horizon[-1]]; out=((px-entry) if side=='long' else (entry-px))/risk
            if out is None: break
            tr.append({'d':d,'R':out-spread/risk,'risk':risk}); break
    return pd.DataFrame(tr)

print("===== 42. FADE THE BREAK (mean reversion) vs FOLLOW IT, by session =====")
rows=[]
for name,(a,b) in SESS.items():
    for mode in ('breakout','fade'):
        t=run(a,b,mode)
        if len(t)<50: continue
        R=t['R']; yr=t['d'].dt.year
        rows.append({'session':name,'mode':mode,'n':len(R),'win%':round((R>0).mean()*100,1),
            'exp_R':round(R.mean(),4),'PF':round(R[R>0].sum()/abs(R[R<0].sum()),2),
            'IS':round(R[yr<=2021].mean(),3),'OOS':round(R[yr>=2022].mean(),3)})
df=pd.DataFrame(rows).sort_values('exp_R',ascending=False)
print(df.to_string(index=False))

print("\n===== 43. THE STOP-SIZE COST CLIFF (this is a bot setting, not a theory) =====")
print("Same entry model, ASIA session, only the stop distance changes:\n")
out=[]
for s_atr in [0.08,0.12,0.18,0.25,0.35,0.50,0.75,1.00]:
    t=run(18*60+5,26*60,'fade',stop_atr=s_atr)
    if len(t)<50: continue
    R=t['R']
    gross=run(18*60+5,26*60,'fade',stop_atr=s_atr,spread=0.0)['R']
    out.append({'stop_ATR':s_atr,'median_stop_$':round(t['risk'].median(),2),
                'cost_as_%_of_risk':round((0.35/t['risk']).mean()*100,1),
                'gross_exp_R':round(gross.mean(),4),'net_exp_R':round(R.mean(),4),
                'edge_lost_to_cost':round(gross.mean()-R.mean(),4)})
print(pd.DataFrame(out).to_string(index=False))
print("\n>> Cost is a FIXED dollar amount. Expressed in R it is inversely proportional to stop size.")
print(">> A tight stop does not 'improve R:R' — it multiplies the toll the spread takes from every trade.")
