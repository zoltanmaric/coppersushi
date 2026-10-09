import urllib.request,urllib.parse,urllib.error,json,pathlib,datetime,time,concurrent.futures
R=pathlib.Path(__file__).resolve().parent;(R/'weather').mkdir(exist_ok=True);(R/'prices').mkdir(exist_ok=True)
def get(url,path):
 if path.exists():return json.loads(path.read_text())
 for a in range(3):
  try:
   with urllib.request.urlopen(url,timeout=35) as r:d=json.load(r)
   path.write_text(json.dumps(d));return d
  except urllib.error.HTTPError as e:
   if e.code==429:time.sleep(15*(a+1))
   elif a==2:raise
   else:time.sleep(2)
  except Exception:
   if a==2:raise
   time.sleep(2)
 raise RuntimeError('request failed')
base={'latitude':'53.55,51.45,48.14,53.37,54.48,54.09,52.13,52.52,51.34,50.11,48.78,49.45','longitude':'9.99,7.01,11.58,7.21,9.05,12.14,11.63,13.41,12.37,8.68,9.18,11.08','models':'icon_eu','hourly':'temperature_2m,wind_speed_120m,shortwave_radiation','timezone':'UTC','timeformat':'unixtime'}
# Same model, locations and variables in both arms. Test period fixed before fitting.
start=datetime.date(2026,4,3);end=datetime.date(2026,10,5)
dates=[start+datetime.timedelta(days=i) for i in range((end-start).days+1)]
def run(day):
 issue=day-datetime.timedelta(days=1);p={**base,'run':str(issue)+'T00:00','forecast_days':3}
 try:
  d=get('https://single-runs-api.open-meteo.com/v1/forecast?'+urllib.parse.urlencode(p),R/'weather'/('fresh-'+str(day)+'.json'))
  if not isinstance(d,list):raise ValueError('unexpected weather shape')
  return str(day),True
 except Exception as e:return str(day),type(e).__name__
with concurrent.futures.ThreadPoolExecutor(2) as pool:
 for i,result in enumerate(pool.map(run,dates)):
  if i%15==0 or result[1] is not True:print('fresh',i+1,len(dates),result,flush=True)
p={**base,'hourly':','.join(x+'_previous_day2' for x in base['hourly'].split(',')),'start_date':'2026-04-02','end_date':'2026-10-06'}
get('https://previous-runs-api.open-meteo.com/v1/forecast?'+urllib.parse.urlencode(p),R/'weather'/'old.json');print('old weather saved',flush=True)
idx=get('https://www.smard.de/app/chart_data/4169/DE/index_quarterhour.json',R/'prices'/'index.json')['timestamps']
# Whole year also permits measuring lost within-hour price detail.
a=int(datetime.datetime(2025,9,20,tzinfo=datetime.timezone.utc).timestamp()*1000);b=int(datetime.datetime(2026,10,6,tzinfo=datetime.timezone.utc).timestamp()*1000)
weeks=[x for i,x in enumerate(idx) if x<b and (i==len(idx)-1 or idx[i+1]>a)]
def week(x):
 get(f'https://www.smard.de/app/chart_data/4169/DE/4169_DE_quarterhour_{x}.json',R/'prices'/f'{x}.json')
 return x
with concurrent.futures.ThreadPoolExecutor(2) as pool:list(pool.map(week,weeks))
print('price weeks saved',len(weeks),flush=True)
