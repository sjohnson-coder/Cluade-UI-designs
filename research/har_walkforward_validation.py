import sys, numpy as np, pandas as pd
sys.path.insert(0,'/home/user/Cluade-UI-designs/godmode_patches')
from forecast_intelligence import HARVolatilityForecaster
D=pd.read_parquet('daily.parquet'); D.index=pd.to_datetime(D.index)
pc=D['close'].shift()
tr=np.maximum(D['high']-D['low'], np.maximum((D['high']-pc).abs(), (D['low']-pc).abs()))
tr=tr.dropna()
vals=tr.values.tolist(); idx=tr.index

f=HARVolatilityForecaster(lookback=500)
START=400
har_pred=[]; atr14=[]; atr20=[]; actual=[]; dates=[]
for t in range(START, len(vals)-1):
    hist=vals[:t+1]                      # only completed bars up to t
    har_pred.append(f.forecast(hist).expected_range)
    atr14.append(np.mean(hist[-14:]))
    atr20.append(np.mean(hist[-20:]))
    actual.append(vals[t+1])             # the next day, never seen
    dates.append(idx[t+1])
a=np.array(actual); h=np.array(har_pred); a14=np.array(atr14); a20=np.array(atr20)
def r2(p):
    return 1 - ((a-p)**2).sum()/((a-a.mean())**2).sum()
def mae(p): return np.abs(a-p).mean()
def qlike(p):  # volatility-appropriate loss; penalises under-forecasting
    p=np.maximum(p,1e-9); return np.mean(a/p - np.log(a/p) - 1)
print(f"WALK-FORWARD, {len(a)} out-of-sample days ({dates[0].date()} -> {dates[-1].date()})\n")
print(f"{'model':<16}{'R2':>9}{'MAE $':>10}{'QLIKE':>9}")
print("-"*44)
for name,p in (("HAR-RV",h),("ATR14 baseline",a14),("ATR20 baseline",a20)):
    print(f"{name:<16}{r2(p):>9.4f}{mae(p):>10.2f}{qlike(p):>9.4f}")
imp=(mae(a14)-mae(h))/mae(a14)*100
print(f"\nHAR vs ATR14: MAE {imp:+.1f}%   R2 {r2(h)-r2(a14):+.4f}")
yr=pd.Series(np.abs(a-h),index=dates).groupby(pd.Series(dates).dt.year.values).mean()
yb=pd.Series(np.abs(a-a14),index=dates).groupby(pd.Series(dates).dt.year.values).mean()
print("\nMAE by year (HAR vs ATR14):")
for y in yr.index:
    w = "HAR" if yr[y]<yb[y] else "ATR"
    print(f"   {y}: {yr[y]:>7.2f} vs {yb[y]:>7.2f}   {w} better")
