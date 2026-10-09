import json,pathlib,datetime
import numpy as np,pandas as pd
from catboost import CatBoostRegressor
R=pathlib.Path(__file__).resolve().parent
rows=[]
for p in (R/'prices').glob('*.json'):
 if p.name!='index.json':rows.extend(json.loads(p.read_text())['series'])
prices=pd.DataFrame(rows,columns=['ms','price']).drop_duplicates('ms').set_index('ms')['price'].sort_index()
prices.index=pd.to_datetime(prices.index,unit='ms',utc=True)
assert prices.index.is_unique
local=prices.index.tz_convert('Europe/Berlin');year=prices[(local>=pd.Timestamp('2025-10-01',tz='Europe/Berlin'))&(local<pd.Timestamp('2026-10-01',tz='Europe/Berlin'))]
# This is the deviation around the known hourly average, not an MAE-optimal lower bound.
hour_average=year.groupby(year.index.floor('h')).transform('mean')
hour_median=year.groupby(year.index.floor('h')).transform('median')
resolution={'quarter_hours':len(year),'mean_absolute_deviation_from_hour_mean':float(abs(year-hour_average).mean()),'mae_floor_for_one_constant_per_hour':float(abs(year-hour_median).mean()),'p95_absolute_deviation_from_hour_mean':float(abs(year-hour_average).quantile(.95))}
def weather_frame(payload,old=False):
 frames=[]
 for n,loc in enumerate(payload):
  h=loc['hourly'];t=pd.to_datetime(h['time'],unit='s',utc=True);f=pd.DataFrame(index=t)
  for v in ['temperature_2m','wind_speed_120m','shortwave_radiation']:
   z=pd.Series(h[v+('_previous_day2' if old else '')],index=t,dtype=float)
   # Radiation timestamp describes the preceding hour: align with delivery-hour start.
   if v=='shortwave_radiation':z.index=z.index-pd.Timedelta(hours=1)
   f[f'{v}_{n}']=z.reindex(t)
  frames.append(f)
 return pd.concat(frames,axis=1)
old=weather_frame(json.loads((R/'weather'/'old.json').read_text()),True)
fresh=[]
for p in sorted((R/'weather').glob('fresh-*.json')):
 day=p.stem.removeprefix('fresh-');f=weather_frame(json.loads(p.read_text()));d=f.index.tz_convert('Europe/Berlin').strftime('%Y-%m-%d');fresh.append(f[d==day])
fresh=pd.concat(fresh).sort_index();assert fresh.index.is_unique
idx=pd.date_range('2026-04-03', '2026-10-06', freq='15min', inclusive='left', tz='Europe/Berlin').tz_convert('UTC')
X=pd.DataFrame(index=idx);loc=idx.tz_convert('Europe/Berlin')
X['hour']=loc.hour;X['quarter']=loc.minute//15;X['weekday']=loc.dayofweek;X['month']=loc.month;X['weekend']=(loc.dayofweek>=5).astype(int)
for d in [1,2,7,14]:
 lag=(loc.tz_localize(None)-pd.Timedelta(days=d)).tz_localize('Europe/Berlin',nonexistent='NaT',ambiguous='NaT').tz_convert('UTC')
 X[f'price_lag_{d}']=prices.reindex(lag).to_numpy()
# Local-clock lags; nonexistent spring-clock slots are missing, never shifted silently.
byday=prices.groupby(prices.index.tz_convert('Europe/Berlin').strftime('%Y-%m-%d')).agg(['mean','min','max'])
for d in [1,7]:
 days=(loc.tz_localize(None)-pd.Timedelta(days=d)).strftime('%Y-%m-%d')
 for stat in ['mean','min','max']:X[f'price_day_{d}_{stat}']=byday[stat].reindex(days).to_numpy()
y=prices.reindex(idx)
wx={k:w.reindex(idx.floor('h')).set_axis(idx) for k,w in [('old',old),('fresh',fresh)]}
valid=X.notna().all(axis=1)&y.notna()&wx['old'].notna().all(axis=1)&wx['fresh'].notna().all(axis=1)
rowvalid=valid.copy()
valid=valid.groupby(valid.index.tz_convert('Europe/Berlin').strftime('%Y-%m-%d')).transform('all')
coverage={'candidate_rows':len(X),'row_complete':int(rowvalid.sum()),'retained_rows':int(valid.sum()),'excluded_days':sorted(set(valid.index[~valid].tz_convert('Europe/Berlin').strftime('%Y-%m-%d')))}
assert all((valid.groupby(valid.index.tz_convert('Europe/Berlin').strftime('%Y-%m-%d')).sum()).isin([0,96]))
print('coverage',{'candidate_rows':len(X),'matched_rows':int(valid.sum()),'excluded_rows':int((~valid).sum())},flush=True)
X=X[valid];y=y[valid];wx={k:v[valid] for k,v in wx.items()}
params=dict(iterations=400,depth=6,learning_rate=.05,loss_function='MAE',thread_count=4,verbose=False,allow_writing_files=False)
months=['2026-06-01','2026-07-01','2026-08-01','2026-09-01','2026-10-01','2026-10-06']
pieces=[];folds=[]
for begin,end in zip(months,months[1:]):
 cutoff=pd.Timestamp(begin,tz='Europe/Berlin');stop=pd.Timestamp(end,tz='Europe/Berlin')
 train=X.index<cutoff;test=(X.index>=cutoff)&(X.index<stop)
 assert X.index[train].max()<X.index[test].min()
 out=pd.DataFrame({'actual':y[test],'week_ago':X.loc[test,'price_lag_7']})
 folds.append({'start':begin,'end_exclusive':end,'train_days':int(train.sum()/96),'test_days':int(test.sum()/96),'train_max':str(X.index[train].max())})
 for arm,seed,nloc in [('no_weather',42,0)]+[(a,z,12) for z in [42,7,2026] for a in ['old','fresh']]+[(a,42,3) for a in ['old','fresh']]:
  cols=[c for c in wx['old'] if int(c.rsplit('_',1)[1])<nloc]
  feat=X if arm=='no_weather' else pd.concat([X,wx[arm][cols]],axis=1)
  name=f'{arm}_{nloc}_{seed}'
  model=CatBoostRegressor(**params,random_seed=seed);model.fit(feat[train],y[train]);out[name]=model.predict(feat[test])
  print('fit',begin,name,flush=True)
 pieces.append(out)
pred=pd.concat(pieces);assert pred.notna().all().all() and pred.index.is_unique
errors=pred.drop(columns='actual').sub(pred.actual,axis=0).abs()
daily=errors.groupby(errors.index.tz_convert('Europe/Berlin').strftime('%Y-%m-%d')).mean()
monthly=errors.groupby(errors.index.tz_convert('Europe/Berlin').strftime('%Y-%m')).mean()
def comparison(old,fresh):
 diff=(daily[old]-daily[fresh]).to_numpy();rng=np.random.default_rng(42);boot=[]
 for _ in range(5000):
  starts=rng.integers(0,len(diff),size=int(np.ceil(len(diff)/7)));ii=np.concatenate([(a+np.arange(7))%len(diff) for a in starts])[:len(diff)];boot.append(diff[ii].mean())
 return {'old':float(daily[old].mean()),'fresh':float(daily[fresh].mean()),'improvement':float(diff.mean()),'percent':float(100*diff.mean()/daily[old].mean()),'interval_95':list(np.quantile(boot,[.025,.975])),'fresh_wins_days':int((diff>0).sum())}
result={'design':json.loads((R/'design.json').read_text()),'coverage':coverage,'folds':folds,'test_days':len(daily),'test_rows':len(pred),'model_settings':params,'scores':errors.mean().to_dict(),'monthly':monthly.to_dict(orient='index'),'primary':comparison('old_12_42','fresh_12_42'),'seeds':{str(z):comparison(f'old_12_{z}',f'fresh_12_{z}') for z in [42,7,2026]},'three_location_control':comparison('old_3_42','fresh_3_42'),'libraries':{'numpy':np.__version__,'pandas':pd.__version__,'catboost':__import__('catboost').__version__}}
(R/'measurement.json').write_text(json.dumps(result,indent=2));pred.to_csv(R/'predictions.csv');daily.to_csv(R/'daily-errors.csv');monthly.to_csv(R/'monthly-errors.csv')
print(json.dumps(result,indent=2),flush=True)
