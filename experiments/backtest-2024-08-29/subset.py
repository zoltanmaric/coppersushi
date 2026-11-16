import itertools, json, sys
import numpy as np, pandas as pd, pypsa
from scipy.stats import spearmanr
sys.path.insert(0, ".")
from backtest import zonal_prices, settled_prices, to_snapshot_hours, CORE

n = pypsa.Network("/Users/ljube/git/coppersushi/worktrees/solve-2024/networks/candidates/opf-2024-08-29-4ccbeedf.nc")
zp = zonal_prices(n)
settled = settled_prices()
ss = settled.groupby(to_snapshot_hours(settled.index, n.snapshots), observed=False).mean()
ss.index = n.snapshots[:len(ss)]

for label, zones in [("all 12 Core", CORE),
                     ("NW only (AT BE CZ DE FR NL PL)", ["AT","BE","CZ","DE","FR","NL","PL"]),
                     ("SEE only (HR HU RO SI SK)", ["HR","HU","RO","SI","SK"])]:
    zs = [c for c in zones if c in zp.columns and c in ss.columns]
    rhos = []
    for s in zp.index:
        if s not in ss.index: continue
        pairs = list(itertools.combinations(zs, 2))
        if len(pairs) < 4: continue
        pred = [abs(zp.loc[s,a]-zp.loc[s,b]) for a,b in pairs]
        true = [abs(ss.loc[s,a]-ss.loc[s,b]) for a,b in pairs]
        ok = ~(np.isnan(pred)|np.isnan(true))
        if ok.sum() > 3: rhos.append(spearmanr(np.array(pred)[ok], np.array(true)[ok])[0])
    bias = float(np.nanmean((zp[zs]-ss[zs]).values))
    print(f"{label:34s} pairs={len(list(itertools.combinations(zs,2))):3d}  mean rho={np.mean(rhos):+.3f}  bias={bias:+.1f}")
