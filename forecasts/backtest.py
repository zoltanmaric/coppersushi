"""Expand the training window monthly; predict every day with that month's fit."""
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

from forecasts.config import RunConfig
from forecasts.contracts import BacktestPredictions, DayForecast, Report, Row
from forecasts.dataset import cutoff
from forecasts.prediction import predict_day
from forecasts.snapshot import InputReader
from forecasts.training import fit_month


def forecast_months(reader: InputReader, features: list[Row], config: RunConfig,
                    output: Path, restore_models: Path | None = None) -> BacktestPredictions:
    """Fit each monthly window, then predict its days without joining scoring truth.

    Features were frozen at each day's own issue cutoff. Each successive fit
    adds eligible past labels. Save models by the first delivery date of their
    window; return fixed predictions and diagnostics for later scoring.
    """
    by_day: dict[str, list[Row]] = defaultdict(list)
    for row in features:
        by_day[row["delivery_date"]].append(row)
    predictions: list[Row] = []
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
            rows = by_day[day.isoformat()]
            forecast = predict_day(rows, fitted.models, fitted.reference, config)
            predictions.extend(_prediction_records(rows, forecast, fold, config))
            if forecast.failures:
                failures.append({"day": day.isoformat(), "models": forecast.failures})
            crossings.update(forecast.crossings)
            fallback[forecast.selected_model] += len(rows)
            day += timedelta(days=1)
        fold = stop
    return BacktestPredictions(predictions, folds, failures, dict(fallback), dict(crossings))


def _prediction_records(rows: list[Row], forecast: DayForecast, fold: date,
                        config: RunConfig) -> list[Row]:
    records = []
    for i, row in enumerate(rows):
        record = {k: row[k] for k in ("delivery_utc", "delivery_date", "demand_available")}
        record.update(selected_model=forecast.selected_model, fallback_reason=forecast.fallback_reason,
                      fold=fold.isoformat(),
                      **{k: v for k, v in row.items() if k.endswith(("_missing", "_unavailable"))
                         or k == "demand_selected_update_utc"})
        for name, quantiles in forecast.ordered.items():
            for j, quantile in enumerate(config.quantiles):
                record[f"{name}_q{quantile}"] = float(quantiles[i, j])
        for name, quantiles in forecast.raw.items():
            for j, quantile in enumerate(config.quantiles):
                record[f"{name}_raw_q{quantile}"] = float(quantiles[i, j])
        records.append(record)
    return records


def _next_month(day: date) -> date:
    return date(day.year + (day.month == 12), day.month % 12 + 1, 1)
