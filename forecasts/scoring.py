"""Five-quantile scores and paired uncertainty over whole local days."""
from collections import defaultdict
from datetime import date, datetime, timedelta
from collections.abc import Sequence
from numpy.typing import ArrayLike

from forecasts.config import BootstrapSettings, RunConfig
from forecasts.contracts import BacktestPredictions, EvaluationResult, FloatArray, Report, Row
from forecasts.dataset import stamp, TIMING

import numpy as np

from forecasts.config import QUANTILES as FIXED_QUANTILES

QUANTILES = np.array(FIXED_QUANTILES)


def score_forecasts(backtest: BacktestPredictions, truth: dict[datetime, float | None],
                    config: RunConfig) -> EvaluationResult:
    """Join realised prices only after prediction, then score common target rows.

    Keep rows without truth in the output and disclose their count. Report
    aggregate/monthly/demand scores and paired seven-day-block comparisons.
    Raise ValueError when no scoring truth exists.
    """
    predictions = _join_truth(backtest.rows, truth)
    scored = [r for r in predictions if r["target"] is not None]
    if not scored:
        raise ValueError("No evaluation truth")
    names = [*config.features, "reference", "system"]
    groups: dict[str, dict[str, list[Row]]] = {"month": defaultdict(list), "demand_available": defaultdict(list)}
    for row in predictions:
        groups["month"][row["delivery_date"][:7]].append(row)
        groups["demand_available"][str(row["demand_available"])].append(row)
    breakdowns = {}
    for group_name, group in groups.items():
        breakdowns[group_name] = {
            key: {"delivery_rows": len(rows), "missing_truth": sum(r["target"] is None for r in rows),
                  "forecast_coverage": 1.,
                  "metrics": _method_scores([r for r in rows if r["target"] is not None], names, config)}
            for key, rows in group.items()
        }
    report = {
        "metrics": _method_scores(scored, names, config), "breakdowns": breakdowns,
        "comparison": paired_blocks(
            np.array([r["target"] for r in scored]),
            {name: np.array([[r[f"{name}_q{q}"] for q in config.quantiles] for r in scored]) for name in names},
            [r["delivery_date"] for r in scored], config.bootstrap),
        "delivery_rows": len(predictions), "scored_rows": len(scored),
        "missing_truth": len(predictions) - len(scored), "forecast_coverage": 1.,
        "fallback_rows": backtest.fallback_rows, "prediction_failures": backtest.failures,
        "raw_crossing_rows": backtest.crossing_rows,
        "raw_crossing_fraction": {name: count / len(predictions) for name, count in backtest.crossing_rows.items()},
        "folds": backtest.folds, "timing_limits": TIMING,
        "limitations": ["Retrospective single-year evaluation; August–September were inspected in earlier diagnostics.",
                        "Historical price/weather availability assumed; demand UpdateTime semantics conditional.",
                        "Intervals are marginal per quarter; no trading-profitability or daily-readiness claim."]}
    return EvaluationResult(predictions, report)


def wis(y: ArrayLike, q: ArrayLike) -> FloatArray:
    """Return weighted interval score per quarter; lower is better, in €/MWh."""
    y, q = np.asarray(y), np.asarray(q)
    error = y[:, None] - q
    return 2 * np.mean(np.maximum(QUANTILES * error, (QUANTILES - 1) * error), axis=1)


def metrics(y: ArrayLike, q: ArrayLike, days: Sequence[str]) -> dict[str, float | int]:
    """Score five ordered quantiles against common available outcomes."""
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


def paired_blocks(y: FloatArray, predictions: dict[str, FloatArray], days: Sequence[str],
                  settings: BootstrapSettings) -> Report:
    """Moving blocks cannot cross missing dates; quarter counts weight sampled scores."""
    unique = sorted(set(days))
    length = settings.block_days
    blocks = [unique[i:i + length] for i in range(len(unique) - length + 1)
              if all(date.fromisoformat(unique[i + j]) == date.fromisoformat(unique[i]) + timedelta(days=j)
                     for j in range(length))]
    if not blocks:
        raise ValueError("Insufficient contiguous days for block comparison")
    sums = {}
    for name, q in predictions.items():
        daily: dict[str, list[float]] = defaultdict(lambda: [0., 0])
        for day, score in zip(days, wis(y, q)):
            daily[day][0] += score
            daily[day][1] += 1
        sums[name] = daily
    rng = np.random.default_rng(settings.seed)
    draws: dict[str, list[float]] = {n: [] for n in predictions if n != "reference"}
    for _ in range(settings.samples):
        sampled = [d for i in rng.integers(len(blocks), size=(len(unique) + length - 1) // length)
                   for d in blocks[i]][:len(unique)]
        scores = {n: sum(v[d][0] for d in sampled) / sum(v[d][1] for d in sampled) for n, v in sums.items()}
        for name in draws:
            draws[name].append(scores[name] - scores["reference"])
    return {n: {"wis_difference": float(np.mean(wis(y, predictions[n]) - wis(y, predictions["reference"]))),
                "ci_95": np.quantile(values, [.025, .975]).tolist()}
            for n, values in draws.items()}


def _join_truth(rows: list[Row], truth: dict[datetime, float | None]) -> list[Row]:
    joined = []
    for row in rows:
        # Keep the established Parquet column order while adding truth here only.
        record = {k: row[k] for k in ("delivery_utc", "delivery_date", "demand_available")}
        record["target"] = truth.get(stamp(row["delivery_utc"]))
        record.update(row)
        record["target_missing"] = int(record["target"] is None)
        joined.append(record)
    return joined


def _method_scores(rows: list[Row], names: list[str], config: RunConfig) -> Report:
    return {name: metrics([r["target"] for r in rows],
                          [[r[f"{name}_q{q}"] for q in config.quantiles] for r in rows],
                          [r["delivery_date"] for r in rows]) for name in names}
