"""Expand the training window monthly; predict every day with that month's fit."""
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from forecasts.config import RunConfig
from forecasts.contracts import BacktestPredictions, DayForecast, Report
from pandera.typing.polars import DataFrame
import polars as pl
from typing import cast
from forecasts.tables import Features, Predictions
from forecasts.dataset import cutoff
from forecasts.prediction import predict_day
from forecasts.snapshot import InputReader
from forecasts.training import fit_month


def forecast_months(reader: InputReader, features: DataFrame[Features], config: RunConfig,
                    output: Path, restore_models: Path | None = None) -> BacktestPredictions:
    """Fit each monthly window, then predict its days without joining scoring truth.

    Features were frozen at each day's own issue cutoff. Each successive fit
    adds eligible past labels. Save models by the first delivery date of their
    window; return fixed predictions and diagnostics for later scoring.
    """
    by_day = {key[0]: cast(DataFrame[Features], daily)
              for key, daily in features.partition_by("delivery_date", as_dict=True, maintain_order=True).items()}
    predictions: list[pl.DataFrame] = []
    folds: list[Report] = []
    failures: list[Report] = []
    fallback: Counter[str] = Counter()
    crossings: Counter[str] = Counter()
    fold = config.evaluation_start
    end = config.end_exclusive
    while fold < end:
        stop = min(_next_month(fold), end)
        print(f"Fitting fold {fold} -> {stop}", flush=True)
        fitted = fit_month(reader, features, fold, config, output / "models" / fold.isoformat(),
                           restore_models / fold.isoformat() if restore_models else None)
        folds.append({"first_delivery_day": fold.isoformat(), "end_exclusive": stop.isoformat(),
                      "fit_cutoff": cutoff(fold).isoformat(), "training_rows": fitted.training_rows,
                      "reference": fitted.reference, "fit_failures": fitted.failures})
        day = fold
        while day < stop:
            rows = by_day[day]
            forecast = predict_day(rows, fitted.models, fitted.reference, config)
            predictions.append(_prediction_table(rows, forecast, fold, config))
            if forecast.failures:
                failures.append({"day": day.isoformat(), "models": forecast.failures})
            crossings.update(forecast.crossings)
            fallback[forecast.selected_model] += len(rows)
            day += timedelta(days=1)
        fold = stop
    return BacktestPredictions(Predictions.validate(pl.concat(predictions)), folds, failures, dict(fallback), dict(crossings))


def _prediction_table(rows: DataFrame[Features], forecast: DayForecast, fold: date,
                      config: RunConfig) -> pl.DataFrame:
    metadata = [name for name in rows.columns if name.endswith(("_missing", "_unavailable"))
                or name == "demand_selected_update_utc"]
    result = rows.select("delivery_utc", "delivery_date", "demand_available").with_columns(
        pl.lit(forecast.selected_model).alias("selected_model"),
        pl.lit(forecast.fallback_reason).alias("fallback_reason"), pl.lit(fold).alias("fold"))
    result = result.hstack(rows.select(metadata))
    for name, quantiles in forecast.ordered.items():
        result = result.with_columns([pl.Series(f"{name}_q{q}", quantiles[:, j])
                                      for j, q in enumerate(config.quantiles)])
    for name, quantiles in forecast.raw.items():
        result = result.with_columns([pl.Series(f"{name}_raw_q{q}", quantiles[:, j])
                                      for j, q in enumerate(config.quantiles)])
    return result


def _next_month(day: date) -> date:
    return date(day.year + (day.month == 12), day.month % 12 + 1, 1)
