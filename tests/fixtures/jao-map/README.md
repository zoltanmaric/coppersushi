# Fixtures for `jao_map.py`

A whole synthesised market day of JAO's five tables, laid out exactly as
`data_sources/jao.read_day` expects, over the nine substations of `../elements/network-slice.nc`.
JAO's terms forbid redistributing its data, so **no JAO-derived bytes are here**: the EICs,
limits, margins and prices are invented. Substation names are facts about physical
infrastructure, so they are real, as is the OpenStreetMap data (ODbL) under the network slice.

The elements are `../elements/README.md`'s, one hour of them stretched over the market day's 24
hours. What this fixture adds is the two things the map needs and the matcher did not:

- **A full day.** The slider cycles `network-slice.nc`'s 24 snapshots, so every hour must carry
  rows; margins move hour to hour, tightest around the evening peak, and the set spans all four
  of `jao_map.MARGIN_BINS`.
- **Elements that bound.** `shadow-prices.csv` holds five spells of binding across the day —
  a line, a PST and a tie-line — with prices spanning all four of `jao_map.PRICE_BINS`, so the
  binding palette, the point-marker path and the "did not bind" hover are all exercised.

`external-constraints.csv` carries the two non-physical rows JAO publishes, one of which binds
over the midday hours: they have no location, and the map's annotation has to say so.

The real day these stand for: 106 elements, of which 13 bound in 78 (hour, element) rows;
`ram / fmax` quartiles 0.54 / 0.70 / 0.90 and shadow-price quartiles 41 / 100 / 211 EUR/MWh —
the numbers `jao_map`'s fixed bin edges are rounded from.

```python
import numpy as np
import pandas as pd

from coppersushi import REPO, cnecs
from coppersushi.market_day import MarketDay

OUT = REPO / "tests" / "fixtures" / "jao-map"
ELEMENTS = REPO / "tests" / "fixtures" / "elements"
hours = MarketDay.on("2024-08-29").hours()

SHAPES = {  # each element's baseline margin, as a share of fmax
    "SYN-LINE-380-A": 0.42, "SYN-LINE-220-B": 0.60, "SYN-TIE-BOTHWAYS": 0.75,
    "SYN-TRAFO-HAGENWERDER": 0.50, "SYN-PST-ETZENRICHT": 0.66, "SYN-LINE-ABSENT": 0.80,
    "SYN-UNTYPED-LINE": 0.92, "SYN-LINE-NOBRANCH": 0.85, "SYN-LINE-NEAREST": 0.55,
}
BINDING = [  # (eic, first hour, last hour, price at the first, price at the last)
    ("SYN-LINE-380-A", 6, 12, 18.0, 240.0),
    ("SYN-LINE-380-A", 17, 20, 320.0, 95.0),
    ("SYN-PST-ETZENRICHT", 17, 19, 46.0, 130.0),
    ("SYN-TIE-BOTHWAYS", 9, 10, 8.0, 62.0),
    ("SYN-LINE-NEAREST", 19, 21, 150.0, 410.0),
]

template = pd.read_csv(ELEMENTS / "elements-day.csv", keep_default_na=False, na_values=[""])
one_hour = template[template.hour == template.hour.iloc[0]].drop(columns=["hour"])

rows = []
for index, hour in enumerate(hours):
    daily = 1.0 - 0.35 * np.sin(np.pi * max(index - 6, 0) / 16) ** 2  # tightest around the peak
    for row in one_hour.itertuples(index=False):
        share = min(SHAPES[row.eic] / daily, 1.05)
        fmax = round(row.fmax * (1.0 + 0.05 * np.cos(index / 3.0)), 1)
        ram = round(fmax * (share if row.direction == "DIRECT" else min(share + 0.18, 1.1)), 1)
        rows.append(dict(row._asdict(), hour=hour.isoformat(), fmax=fmax, ram=ram, fref=round(fmax - ram, 1)))
elements = pd.DataFrame(rows)[["hour", *one_hour.columns]]

prices = []
for eic, start, end, first, last in BINDING:
    for index in range(start, end + 1):
        share = 0.0 if end == start else (index - start) / (end - start)
        element = elements[(elements.hour == hours[index].isoformat()) & (elements.eic == eic)].iloc[0]
        prices.append({
            "hour": hours[index].isoformat(), "eic": eic, "name": element["name"], "tso": element.tso,
            "direction": "DIRECT", "cont_name": f"N-1 {element['name']}",
            "shadow_price": round(first + (last - first) * share, 2),
            "ram": element.ram, "fmax": element.fmax,
        })

constraints = []
for index, hour in enumerate(hours):
    for name, fmax in (("External Constraint SYN_AL_export", 1000.0), ("Equality Constraint SYN_zone", 600.0)):
        bound = name.startswith("External") and 8 <= index <= 11
        constraints.append({
            "hour": hour.isoformat(), "name": name, "tso": "", "direction": "NA", "fmax": fmax,
            "ram": 0.0 if bound else round(fmax * 0.4, 1),
            "shadow_price": 74.5 if bound else np.nan,
            "binding_direction": "DIRECT" if bound else np.nan,
        })

ends = elements[cnecs.END_COLUMNS].drop_duplicates(ignore_index=True)  # hour-free: each TSO's own orientation

elements.to_csv(OUT / "elements.csv", index=False)
ends.to_csv(OUT / "element-ends.csv", index=False)
pd.DataFrame(prices).to_csv(OUT / "shadow-prices.csv", index=False)
pd.DataFrame(constraints).to_csv(OUT / "external-constraints.csv", index=False)
pd.read_csv(ELEMENTS / "contingencies-day.csv").to_csv(OUT / "contingencies.csv", index=False)
```
