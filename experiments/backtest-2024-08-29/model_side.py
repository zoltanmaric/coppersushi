import json, sys, itertools
import pandas as pd, pypsa

OUT = "/private/tmp/claude-501/-Users-ljube-git-coppersushi/8219e1ac-a793-4c84-b3fb-ba3fccf008a8/scratchpad"
CORE = ["AT","BE","CZ","DE","FR","HR","HU","NL","PL","RO","SI","SK"]

print("loading...", flush=True)
n = pypsa.Network("/Users/ljube/git/coppersushi/networks/opf-2013-07-17.nc")
print(f"loaded: {len(n.buses)} buses, {len(n.lines)} lines, {len(n.snapshots)} snapshots", flush=True)
print("snapshots:", list(map(str, n.snapshots)), flush=True)

cap = (n.lines.s_nom * n.lines.s_max_pu).replace(0, pd.NA)
print("s_max_pu unique:", sorted(n.lines.s_max_pu.unique())[:5], flush=True)
loading = n.lines_t.p0.abs().div(cap, axis=1)

res = {"snapshots": [str(s) for s in n.snapshots], "binding_per_snapshot": {}, "zonal_price": {}, "top_loaded": {}}
for s in n.snapshots:
    row = loading.loc[s].dropna()
    binding = row[row >= 0.99]
    res["binding_per_snapshot"][str(s)] = int(len(binding))
    res["top_loaded"][str(s)] = [[str(i), round(float(v), 4)] for i, v in row.nlargest(5).items()]
print("binding counts:", res["binding_per_snapshot"], flush=True)

country = n.buses.country
load_bus = n.loads.bus.map(country)
loads = n.loads_t.p_set if not n.loads_t.p_set.empty else n.loads_t.p
mp = n.buses_t.marginal_price
zp = {}
for s in n.snapshots:
    w = loads.loc[s].groupby(n.loads.bus).sum()
    w = w[w > 0]
    p = mp.loc[s].reindex(w.index)
    df = pd.DataFrame({"w": w, "p": p, "c": w.index.map(country)}).dropna()
    zp[str(s)] = (df.groupby("c").apply(lambda g: (g.p*g.w).sum()/g.w.sum())).round(2).to_dict()
res["zonal_price"] = zp

nodal = {}
for s in n.snapshots:
    df = pd.DataFrame({"p": mp.loc[s], "c": mp.columns.map(country)}).dropna()
    g = df.groupby("c").p
    nodal[str(s)] = {c: [round(float(g.get_group(c).min()),2), round(float(g.get_group(c).max()),2)] for c in g.groups if c in CORE}
res["nodal_spread_core"] = nodal

pairs = {}
for s in n.snapshots:
    z = zp[str(s)]
    pairs[str(s)] = sorted(
        [[f"{a}-{b}", round(abs(z[a]-z[b]),2)] for a,b in itertools.combinations(CORE,2) if a in z and b in z],
        key=lambda x:-x[1])[:8]
res["top_zone_pair_gaps"] = pairs

json.dump(res, open(f"{OUT}/model_side.json","w"), indent=1)
print("WROTE model_side.json", flush=True)
