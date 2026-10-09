"""Five-quantile scores and paired uncertainty over whole local days."""
from collections import defaultdict
from datetime import date, timedelta

import numpy as np

QUANTILES = np.array([.025, .25, .5, .75, .975])


def wis(y, q):
    y, q = np.asarray(y), np.asarray(q)
    error = y[:, None] - q
    return 2 * np.mean(np.maximum(QUANTILES * error, (QUANTILES - 1) * error), axis=1)


def metrics(y, q, days):
    y, q = np.asarray(y), np.asarray(q)
    if not len(y):
        return {"rows": 0}
    if q.shape != (len(y), 5) or not np.isfinite(q).all() or (np.diff(q, axis=1) < 0).any():
        raise ValueError("Expected five ordered finite quantiles per target")
    covered = (y[:, None] >= q[:, [1, 0]]) & (y[:, None] <= q[:, [3, 4]])
    daily = defaultdict(list)
    for day, pair in zip(days, covered):
        daily[day].append(pair)
    return {"rows": len(y), "days": len(daily), "wis": float(np.mean(wis(y, q))),
            "median_mae": float(np.mean(abs(y - q[:, 2]))),
            "median_rmse": float(np.sqrt(np.mean((y - q[:, 2]) ** 2))),
            "coverage_50": float(covered[:, 0].mean()), "coverage_95": float(covered[:, 1].mean()),
            "width_50": float(np.mean(q[:, 3] - q[:, 1])), "width_95": float(np.mean(q[:, 4] - q[:, 0])),
            "daily_coverage_50": float(np.mean([np.mean(v, axis=0)[0] for v in daily.values()])),
            "daily_coverage_95": float(np.mean([np.mean(v, axis=0)[1] for v in daily.values()]))}


def paired_blocks(y, predictions, days, settings):
    """Moving blocks cannot cross missing dates; quarter counts weight sampled scores."""
    unique = sorted(set(days))
    length = settings["block_days"]
    blocks = [unique[i:i + length] for i in range(len(unique) - length + 1)
              if all(date.fromisoformat(unique[i + j]) == date.fromisoformat(unique[i]) + timedelta(days=j)
                     for j in range(length))]
    if not blocks:
        raise ValueError("Insufficient contiguous days for block comparison")
    sums = {}
    for name, q in predictions.items():
        daily = defaultdict(lambda: [0., 0])
        for day, score in zip(days, wis(y, q)):
            daily[day][0] += score
            daily[day][1] += 1
        sums[name] = daily
    rng = np.random.default_rng(settings["seed"])
    draws = {n: [] for n in predictions if n != "reference"}
    for _ in range(settings["samples"]):
        sampled = [d for i in rng.integers(len(blocks), size=(len(unique) + length - 1) // length)
                   for d in blocks[i]][:len(unique)]
        scores = {n: sum(v[d][0] for d in sampled) / sum(v[d][1] for d in sampled) for n, v in sums.items()}
        for name in draws:
            draws[name].append(scores[name] - scores["reference"])
    return {n: {"wis_difference": float(np.mean(wis(y, predictions[n]) - wis(y, predictions["reference"]))),
                "ci_95": np.quantile(values, [.025, .975]).tolist()}
            for n, values in draws.items()}
