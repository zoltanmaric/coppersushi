"""Five-quantile scores and paired uncertainty over whole local days."""
from collections import defaultdict
from datetime import date, datetime, timedelta
from collections.abc import Sequence
from numpy.typing import ArrayLike

from forecasts.config import BootstrapSettings, RunConfig
from forecasts.contracts import BacktestPredictions, EvaluationResult, FloatArray, Report
from forecasts.tables import Predictions, ScoredPredictions
from pandera.typing.polars import DataFrame
import polars as pl
from typing import cast
from forecasts.dataset import TIMING

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
    scored = cast(DataFrame[ScoredPredictions], predictions.filter(pl.col("target").is_not_null()))
    if scored.is_empty():
        raise ValueError("No evaluation truth")
    names = [*config.features, "reference", "system"]
    breakdowns: dict[str, Report] = {}
    for group_name, group in (("month", pl.col("delivery_date").dt.strftime("%Y-%m")),
                              ("demand_available", pl.col("demand_available").cast(pl.String))):
        grouped = predictions.with_columns(group.alias("_group"))
        breakdowns[group_name] = {}
        for (key,), subset in grouped.partition_by("_group", as_dict=True, maintain_order=True).items():
            rows = cast(DataFrame[ScoredPredictions], subset.drop("_group"))
            available = cast(DataFrame[ScoredPredictions], rows.filter(pl.col("target").is_not_null()))
            breakdowns[group_name][key] = {
                "delivery_rows": len(rows), "missing_truth": rows["target"].null_count(),
                "forecast_coverage": 1., "metrics": _method_scores(available, names, config)}
    report = {
        "metrics": _method_scores(scored, names, config), "breakdowns": breakdowns,
        "comparison": paired_blocks(
            scored["target"].to_numpy(),
            {name: scored.select([f"{name}_q{q}" for q in config.quantiles]).to_numpy() for name in names},
            scored["delivery_date"].to_list(), config.bootstrap),
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


def metrics(y: ArrayLike, q: ArrayLike, days: Sequence[date]) -> dict[str, float | int]:
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


def paired_blocks(y: FloatArray, predictions: dict[str, FloatArray], days: Sequence[date],
                  settings: BootstrapSettings) -> Report:
    """Moving blocks cannot cross missing dates; quarter counts weight sampled scores."""
    unique = sorted(set(days))
    length = settings.block_days
    blocks = [unique[i:i + length] for i in range(len(unique) - length + 1)
              if all(unique[i + j] == unique[i] + timedelta(days=j)
                     for j in range(length))]
    if not blocks:
        raise ValueError("Insufficient contiguous days for block comparison")
    sums = {}
    for name, q in predictions.items():
        daily: dict[date, list[float]] = defaultdict(lambda: [0., 0])
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


def _join_truth(rows: DataFrame[Predictions], truth: dict[datetime, float | None]) -> DataFrame[ScoredPredictions]:
    outcomes = pl.DataFrame({"delivery_utc": list(truth), "target": list(truth.values())},
                            schema={"delivery_utc": pl.Datetime("us", "UTC"), "target": pl.Float64})
    joined = rows.join(outcomes, on="delivery_utc", how="left", maintain_order="left").with_columns(
        pl.col("target").is_null().cast(pl.Int64).alias("target_missing"))
    # Preserve the established artifact order while adding truth only here.
    first = ["delivery_utc", "delivery_date", "demand_available", "target"]
    return ScoredPredictions.validate(joined.select(*first, *[name for name in rows.columns if name not in first]))


def _method_scores(rows: DataFrame[ScoredPredictions], names: Sequence[str], config: RunConfig) -> Report:
    return {name: metrics(rows["target"].to_numpy(),
                          rows.select([f"{name}_q{q}" for q in config.quantiles]).to_numpy(),
                          rows["delivery_date"].to_list()) for name in names}
