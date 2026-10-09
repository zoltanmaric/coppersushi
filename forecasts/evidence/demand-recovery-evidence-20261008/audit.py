"""Audit public monthly demand extracts; no late values are treated as earlier versions."""
import argparse, json, zipfile
from pathlib import Path
from datetime import timedelta
import pandas as pd

p=argparse.ArgumentParser()
p.add_argument('inputs', nargs='+')
p.add_argument('--start', default='2025-10-01')
p.add_argument('--end', default='2026-10-01')
p.add_argument('--output', default='/tmp/demand-check-20261008')
a=p.parse_args()
areas={'10Y1001A1001A83F':'Germany country','10Y1001A1001A82H':'Germany–Luxembourg zone','10YDE-VE-------2':'50Hertz','10YDE-RWENET---I':'Amprion','10YDE-EON------1':'TenneT Germany','10YDE-ENBW-----N':'TransnetBW'}
frames=[]; sources=[]
def read(f, name):
    d=pd.read_csv(f, sep='\t')
    d=d[d.AreaCode.isin(areas)]
    d['source_file']=name
    frames.append(d)
for name in a.inputs:
    path=Path(name)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                if n.endswith('.csv') and 'DayAheadTotalLoadForecast' in n:
                    with z.open(n) as f: read(f,n)
                    sources.append(n)
    else: read(path,path.name); sources.append(path.name)
d=pd.concat(frames,ignore_index=True)
d['delivery']=pd.to_datetime(d['DateTime(UTC)'],utc=True)
d['updated']=pd.to_datetime(d['UpdateTime(UTC)'],utc=True)
start=pd.Timestamp(a.start,tz='Europe/Berlin'); end=pd.Timestamp(a.end,tz='Europe/Berlin')
d=d[(d.delivery>=start)&(d.delivery<end)].copy()
d['local_date']=d.delivery.dt.tz_convert('Europe/Berlin').dt.date
d['cutoff']=pd.to_datetime([pd.Timestamp(str(x-timedelta(days=1))+' 11:00').tz_localize('Europe/Berlin') for x in d.local_date],utc=True)
d['passes']=(d.updated<=d.cutoff)&d['TotalLoad[MW]'].notna()
d['month']=d.delivery.dt.tz_convert('Europe/Berlin').dt.strftime('%Y-%m')
expected=pd.date_range(start,end,freq='15min',inclusive='left').tz_convert('UTC')
summary=[]
for code,label in areas.items():
    s=d[d.AreaCode==code]
    summary.append(dict(area=label,rows=len(s),unique_times=s.delivery.nunique(),duplicate_rows=int(s.delivery.duplicated().sum()),expected=len(expected),missing_times=len(expected.difference(s.delivery)),pre_cutoff=int(s.passes.sum()),late_or_missing_update=int((~s.passes).sum()),pct_expected_pre_cutoff=round(100*s.passes.sum()/len(expected),3),resolutions=s.ResolutionCode.value_counts().to_dict()))
out=Path(a.output); out.mkdir(parents=True,exist_ok=True)
d.to_csv(out/'german-demand-rows.csv',index=False)
monthly=d.groupby(['AreaCode','month']).agg(rows=('passes','size'),pre_cutoff=('passes','sum')).reset_index()
monthly['area']=monthly.AreaCode.map(areas)
monthly.to_csv(out/'monthly-coverage.csv',index=False)
daily=d.groupby(['AreaCode','local_date']).agg(rows=('passes','size'),pre_cutoff=('passes','sum')).reset_index()
daily['area']=daily.AreaCode.map(areas)
daily.to_csv(out/'daily-coverage.csv',index=False)
result=dict(start=str(start),end_exclusive=str(end),sources=sources,summary=summary)
(out/'summary.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
