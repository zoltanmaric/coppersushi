"""One-day backtest: the 2024-08-29 solve against JAO's binding CNECs and settled day-ahead prices.

Model side  : networks/candidates/opf-2024-08-29-*.nc (2 h snapshots, naive = UTC)
Truth side  : JAO shadowPrices (binding CNECs, hourly UTC), energy-charts settled prices (hourly UTC)
"""
import glob
import pathlib
import itertools
import json
import sys

import numpy as np
import pandas as pd
import pypsa
from scipy.stats import spearmanr

SCRATCH = "/private/tmp/claude-501/-Users-ljube-git-coppersushi/8219e1ac-a793-4c84-b3fb-ba3fccf008a8/scratchpad"
CORE = ["AT", "BE", "CZ", "DE", "FR", "HR", "HU", "NL", "PL", "RO", "SI", "SK"]
BZN = {"DE": "DE-LU", **{c: c for c in CORE if c != "DE"}}
# JAO names the owning TSO, not the country; this is the mapping for the TSOs that appear.
TSO_COUNTRY = {"Apg": "AT", "Amprion": "DE", "TennetGmbh": "DE", "TransnetBw": "DE", "50Hertz": "DE",
               "Elia": "BE", "TennetBv": "NL", "Ceps": "CZ", "Seps": "SK", "Pse": "PL",
               "Transelectrica": "RO", "Mavir": "HU", "Hops": "HR", "Rte": "FR", "Eles": "SI"}


def load_model(path):
    n = pypsa.Network(path)
    print(f"model: {path.split('/')[-1]} — {len(n.buses)} buses, {len(n.lines)} lines, "
          f"{len(n.snapshots)} snapshots {n.snapshots[0]}..{n.snapshots[-1]}", flush=True)
    return n


def zonal_prices(n):
    """Load-weighted nodal price per country and snapshot (the zone price a copper-plate market prints)."""
    loads = n.loads_t.p_set if not n.loads_t.p_set.empty else n.loads_t.p
    country = n.buses.country
    out = {}
    for s in n.snapshots:
        w = loads.loc[s].groupby(n.loads.bus).sum()
        w = w[w > 0]
        df = pd.DataFrame({"w": w, "p": n.buses_t.marginal_price.loc[s].reindex(w.index)}).dropna()
        df["c"] = df.index.map(country)
        out[s] = df.groupby("c").apply(lambda g: (g.p * g.w).sum() / g.w.sum())
    return pd.DataFrame(out).T


def binding_lines(n, tol=0.99):
    """Lines at the 70 % cap — the model's analogue of a CNEC with no margin left."""
    cap = (n.lines.s_nom * n.lines.s_max_pu).replace(0, np.nan)
    loading = n.lines_t.p0.abs().div(cap, axis=1)
    country = n.buses.country
    c0, c1 = n.lines.bus0.map(country), n.lines.bus1.map(country)
    out = {}
    for s in n.snapshots:
        row = loading.loc[s].dropna()
        hit = row[row >= tol].index
        out[s] = pd.Series([c0[i] if c0[i] == c1[i] else f"{c0[i]}-{c1[i]}" for i in hit], index=hit)
    return loading, out


def line_duals(n):
    """Shadow price of the line limit, EUR/MW — directly comparable to JAO's shadowPrice."""
    for attr in ("mu_upper", "mu_lower"):
        if attr in n.lines_t and not n.lines_t[attr].empty:
            return n.lines_t["mu_upper"].abs() + n.lines_t["mu_lower"].abs()
    return None


def jao_binding():
    rows = json.load(open(f"{SCRATCH}/jao/shadowPrices.json"))["data"]
    df = pd.DataFrame(rows)
    df["hour"] = pd.to_datetime(df.dateTimeUtc, utc=True)
    df["external"] = df.cnecName.str.startswith(("External Constraint", "Equality Constraint"))
    df["country"] = df.tso.map(TSO_COUNTRY)
    return df


def settled_prices():
    out = {}
    for c in CORE:
        try:
            d = json.load(open(f"{SCRATCH}/prices/{BZN[c]}.json"))
        except FileNotFoundError:
            print(f"  settled price missing for {c}", flush=True)
            continue
        s = pd.Series(d["price"], index=pd.to_datetime(d["unix_seconds"], unit="s", utc=True))
        out[c] = s[(s.index >= "2024-08-28T22:00Z") & (s.index < "2024-08-29T22:00Z")]
    return pd.DataFrame(out)


def to_snapshot_hours(index_utc, snapshots):
    """Each 2 h snapshot owns the two hours starting at it (snapshots are naive UTC)."""
    snap = pd.to_datetime(snapshots).tz_localize("UTC")
    return pd.cut(index_utc, bins=list(snap) + [snap[-1] + pd.Timedelta("2h")],
                  right=False, labels=snap)


def main():
    # Newest by mtime, not by name: candidates are suffixed with a pin SHA, which does not sort by age.
    cands = sorted(glob.glob("/Users/ljube/git/coppersushi/worktrees/solve-2024/networks/candidates/opf-2024-08-29-*.nc"),
                   key=lambda f: pathlib.Path(f).stat().st_mtime)
    if not cands:
        sys.exit("no 2024-08-29 candidate yet")
    n = load_model(sys.argv[1] if len(sys.argv) > 1 else cands[-1])

    zp = zonal_prices(n)[[c for c in CORE if c in zonal_prices(n).columns]]
    loading, binding = binding_lines(n)
    duals = line_duals(n)
    jao = jao_binding()
    settled = settled_prices()

    report = {"model": n.meta.get("name", "?"), "snapshots": [str(s) for s in n.snapshots]}

    # --- 1. binding elements, model vs JAO -------------------------------------------------
    jao_real = jao[~jao.external]
    per_hour = jao_real.groupby("hour").size()
    grp = to_snapshot_hours(per_hour.index, n.snapshots)
    jao_per_snap = per_hour.groupby(grp, observed=False).sum()
    model_per_snap = pd.Series({s: len(v) for s, v in binding.items()})
    cmp_bind = pd.DataFrame({"model_lines_at_cap": model_per_snap.values,
                             "jao_binding_cnecs": jao_per_snap.values},
                            index=[str(s) for s in n.snapshots])
    print("\n=== 1. binding elements per 2h snapshot ===", flush=True)
    print(cmp_bind.to_string(), flush=True)
    report["binding"] = cmp_bind.to_dict()

    model_countries = pd.Series([c for v in binding.values() for c in v if "-" not in str(c)]).value_counts()
    jao_countries = jao_real.country.value_counts()
    both = pd.DataFrame({"model": model_countries, "jao": jao_countries}).fillna(0).astype(int)
    both = both.loc[[c for c in both.index if c in CORE]].sort_values("jao", ascending=False)
    print("\n--- where the congestion sits (internal elements, whole day) ---", flush=True)
    print(both.to_string(), flush=True)
    if len(both) > 2:
        rho, p = spearmanr(both.model, both.jao)
        print(f"country-level Spearman rho = {rho:.3f} (p={p:.3f})", flush=True)
        report["country_rho"] = float(rho)
    report["country_counts"] = both.to_dict()

    # --- 2. zonal price level ---------------------------------------------------------------
    print("\n=== 2. zonal price, model vs settled (EUR/MWh) ===", flush=True)
    grp_s = to_snapshot_hours(settled.index, n.snapshots)
    settled_snap = settled.groupby(grp_s, observed=False).mean()
    settled_snap.index = n.snapshots[:len(settled_snap)]
    common = [c for c in CORE if c in zp.columns and c in settled_snap.columns]
    err = (zp[common] - settled_snap[common]).dropna(how="all")
    summary = pd.DataFrame({"model_mean": zp[common].mean().round(2),
                            "settled_mean": settled_snap[common].mean().round(2),
                            "bias": err.mean().round(2),
                            "MAE": err.abs().mean().round(2),
                            "corr": [zp[c].corr(settled_snap[c]).round(3) for c in common]})
    print(summary.to_string(), flush=True)
    print(f"\noverall MAE {err.abs().values[~np.isnan(err.abs().values)].mean():.2f} EUR/MWh, "
          f"bias {np.nanmean(err.values):+.2f}", flush=True)
    report["price_summary"] = summary.to_dict()

    # --- 3. zone-pair spread ranking (the spec's headline metric) ---------------------------
    print("\n=== 3. zone-pair spread ranking (Spearman per snapshot) ===", flush=True)
    rows = []
    for s in zp.index:
        if s not in settled_snap.index:
            continue
        pairs = [(a, b) for a, b in itertools.combinations(common, 2)]
        pred = [abs(zp.loc[s, a] - zp.loc[s, b]) for a, b in pairs]
        true = [abs(settled_snap.loc[s, a] - settled_snap.loc[s, b]) for a, b in pairs]
        ok = ~(np.isnan(pred) | np.isnan(true))
        if ok.sum() > 3:
            rho, p = spearmanr(np.array(pred)[ok], np.array(true)[ok])
            rows.append({"snapshot": str(s), "n_pairs": int(ok.sum()), "rho": round(float(rho), 3),
                         "p": round(float(p), 4)})
    rank = pd.DataFrame(rows)
    print(rank.to_string(index=False), flush=True)
    print(f"\nmean rho = {rank.rho.mean():.3f}   (0 = no skill, 1 = perfect ordering)", flush=True)
    report["pair_rank"] = rows
    report["mean_rho"] = float(rank.rho.mean())

    # --- 4. shadow price magnitude ----------------------------------------------------------
    print("\n=== 4. shadow prices (EUR/MW) ===", flush=True)
    jsp = jao_real.shadowPrice
    print(f"JAO   binding CNECs: n={len(jsp)} min={jsp.min():.2f} median={jsp.median():.2f} max={jsp.max():.2f}",
          flush=True)
    if duals is not None:
        nz = duals.values[duals.values > 1e-6]
        print(f"model line duals  : n={len(nz)} min={nz.min():.2f} median={np.median(nz):.2f} max={nz.max():.2f}",
              flush=True)
        report["duals"] = {"n": int(len(nz)), "median": float(np.median(nz)), "max": float(nz.max())}
    else:
        print("model: no line duals stored in this network", flush=True)

    json.dump(report, open(f"{SCRATCH}/backtest.json", "w"), indent=1, default=str)
    print("\nWROTE backtest.json", flush=True)


if __name__ == "__main__":
    main()
