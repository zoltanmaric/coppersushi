"""Replay the October 8 compatibility checks from saved public responses."""
import datetime as dt
import json
import math
from pathlib import Path
import zipfile
from zoneinfo import ZoneInfo

root = Path(__file__).resolve().parent
with zipfile.ZipFile(root / 'responses.zip') as archive:
    history = json.loads(archive.read('history.json'))
    future = json.loads(archive.read('future.json'))
with zipfile.ZipFile(root.parent / 'forecast-bounded-evidence-20261007/inputs.zip') as archive:
    previous = json.loads(archive.read('weather/old.json'))
fields = ['temperature_2m_previous_day2', 'wind_speed_120m_previous_day2', 'shortwave_radiation_previous_day2']
names = ['Hamburg', 'Essen', 'Munich', 'Emden', 'Husum', 'Rostock', 'Magdeburg', 'Berlin', 'Leipzig', 'Frankfurt', 'Stuttgart', 'Nuremberg']
zone = ZoneInfo('Europe/Berlin')
def stamp(day):
    return int(dt.datetime.fromisoformat(day).replace(tzinfo=zone).timestamp())
historical_times = list(range(stamp('2025-10-01'), stamp('2026-10-01'), 3600))
future_times = list(range(stamp('2026-10-09'), stamp('2026-10-10'), 3600))
def distance(a, b):
    p, q = math.radians(a['latitude']), math.radians(b['latitude'])
    lon = math.radians(b['longitude'] - a['longitude'])
    return 12742 * math.asin(math.sqrt(math.sin((q-p)/2)**2 + math.cos(p)*math.cos(q)*math.sin(lon/2)**2))
results = []
assert len(history['data']) == len(future['data']) == len(previous) == 12
for i, (h, f, old) in enumerate(zip(history['data'], future['data'], previous)):
    for key in ['latitude', 'longitude', 'elevation', 'hourly_units']:
        assert h[key] == f[key] == old[key], (names[i], key)
    hi = {t: j for j, t in enumerate(h['hourly']['time'])}
    fi = {t: j for j, t in enumerate(f['hourly']['time'])}
    assert len(hi) == len(h['hourly']['time'])
    assert len(fi) == len(f['hourly']['time'])
    assert all(t in hi for t in historical_times)
    nulls = {k: sum(h['hourly'][k][hi[t]] is None for t in historical_times) for k in fields}
    live_nulls = {k: sum(f['hourly'][k][fi[t + (3600 if k.startswith('shortwave') else 0)]] is None for t in future_times) for k in fields}
    compared = changed = 0
    for j, t in enumerate(old['hourly']['time']):
        if t not in hi:
            continue
        for k in fields:
            compared += 1
            changed += old['hourly'][k][j] != h['hourly'][k][hi[t]]
    results.append(dict(name=names[i], latitude=h['latitude'], longitude=h['longitude'],
                        nearest_other_location_km=round(min(distance(h, b) for j, b in enumerate(history['data']) if i != j), 1),
                        history_hours=len(historical_times), history_nulls=nulls,
                        tomorrow_hours=len(future_times), tomorrow_aligned_nulls=live_nulls,
                        prior_snapshot_compared_values=compared, prior_snapshot_changed_values=changed))
assert len({(x['latitude'], x['longitude']) for x in results}) == 12
print(json.dumps({'checked_at_utc': future['retrieved_at_utc'], 'locations': results}, indent=2))
