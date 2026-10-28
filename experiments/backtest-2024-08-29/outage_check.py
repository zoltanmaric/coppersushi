"""Does the model dispatch plant that was not actually running on 2024-08-29?

Outage hypothesis: the model has 100 % availability for every unit, so in a region with heavy
late-August maintenance it would over-produce from cheap thermal/nuclear and under-price the zone.
Discriminator: per-carrier daily energy, model vs actual (energy-charts `public_power`).
"""
import json
import sys

import pandas as pd
import pypsa

SCRATCH = "/private/tmp/claude-501/-Users-ljube-git-coppersushi/8219e1ac-a793-4c84-b3fb-ba3fccf008a8/scratchpad"
NET = "/Users/ljube/git/coppersushi/worktrees/solve-2024/networks/candidates/opf-2024-08-29-4ccbeedf.nc"

# energy-charts production types -> the model's carrier vocabulary
BUCKET = {
    "Nuclear": "nuclear", "Fossil brown coal / lignite": "lignite", "Fossil hard coal": "coal",
    "Fossil coal-derived gas": "coal", "Fossil gas": "gas", "Fossil oil": "oil",
    "Hydro Run-of-River": "hydro", "Hydro water reservoir": "hydro",
    "Hydro Pumped Storage": "hydro", "Hydro pumped storage": "hydro",
    "Wind onshore": "wind", "Wind offshore": "wind", "Solar": "solar",
    "Biomass": "biomass", "Waste": "biomass", "Geothermal": "other", "Others": "other",
}
MODEL_BUCKET = {
    "nuclear": "nuclear", "lignite": "lignite", "coal": "coal", "CCGT": "gas", "OCGT": "gas",
    "oil": "oil", "ror": "hydro", "hydro": "hydro", "PHS": "hydro",
    "onwind": "wind", "offwind-ac": "wind", "offwind-dc": "wind", "offwind-float": "wind",
    "solar": "solar", "solar-hsat": "solar", "biomass": "biomass", "load": "shed",
}


def actual(country: str) -> pd.Series | None:
    try:
        d = json.load(open(f"{SCRATCH}/gen/{country}.json"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if "production_types" not in d:
        return None
    idx = pd.to_datetime(d["unix_seconds"], unit="s", utc=True)
    keep = (idx >= "2024-08-28T22:00Z") & (idx < "2024-08-29T22:00Z")
    hours = 24 / max(keep.sum(), 1) * keep.sum() / max(keep.sum(), 1)  # step length in hours
    step = (idx[1] - idx[0]).total_seconds() / 3600 if len(idx) > 1 else 1.0
    out: dict[str, float] = {}
    for pt in d["production_types"]:
        b = BUCKET.get(pt["name"])
        if b is None:
            continue
        vals = pd.Series(pt["data"], index=idx)[keep].clip(lower=0).fillna(0)
        out[b] = out.get(b, 0.0) + float(vals.sum()) * step
    return pd.Series(out)


def model(n: pypsa.Network, country: str) -> pd.Series:
    w = n.snapshot_weightings.generators
    buses = n.buses.index[n.buses.country == country]
    gens = n.generators[n.generators.bus.isin(buses)]
    e = n.generators_t.p[gens.index].mul(w, axis=0).sum()
    by = e.groupby(gens.carrier.map(lambda c: MODEL_BUCKET.get(c, "other"))).sum()
    if len(n.storage_units):
        su = n.storage_units[n.storage_units.bus.isin(buses)]
        if len(su):
            se = n.storage_units_t.p[su.index].clip(lower=0).mul(w, axis=0).sum()
            by = by.add(pd.Series({"hydro": float(se.sum())}), fill_value=0)
    return by


if __name__ == "__main__":
    n = pypsa.Network(NET)
    print(f"model: {NET.split('/')[-1]}\n")
    for c in ["RO", "SI", "HR", "HU", "SK", "DE", "FR"]:
        a = actual(c)
        if a is None:
            print(f"{c}: no actual generation data\n")
            continue
        m = model(n, c)
        df = pd.DataFrame({"model_GWh": m / 1000, "actual_GWh": a / 1000}).fillna(0)
        df = df[(df.model_GWh.abs() > 0.05) | (df.actual_GWh.abs() > 0.05)]
        df["diff"] = df.model_GWh - df.actual_GWh
        df = df.sort_values("diff", key=abs, ascending=False).round(2)
        print(f"--- {c} ---")
        print(df.to_string())
        print(f"    total model {df.model_GWh.sum():.1f} GWh vs actual {df.actual_GWh.sum():.1f} GWh\n")
