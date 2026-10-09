"""Ordinary Python fitting/evaluation functions shared by the local workflow and replay."""
from collections import Counter, defaultdict
from datetime import date, timedelta
import json
from pathlib import Path

from catboost import CatBoostError, CatBoostRegressor
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from forecasts.dataset import BERLIN, cutoff, stamp, TIMING
from forecasts.scoring import QUANTILES, metrics, paired_blocks
from forecasts.snapshot import WEATHER_FIELDS

CALENDAR = ["quarter_of_day", "day_of_week", "month", "public_holiday"]
PRICE = [f"price_lag_{d}" for d in (1, 2, 7, 14)] + [f"price_day_{d}_{s}" for d in (1, 7) for s in ("mean", "min", "max")]
BASE = CALENDAR + PRICE + [f + "_missing" for f in PRICE]
WEATHER = list(WEATHER_FIELDS) + [f + "_missing" for f in WEATHER_FIELDS]
FEATURES = {"prices": BASE, "weather": BASE + WEATHER,
            "demand": BASE + WEATHER + ["demand_mw", "demand_available", "demand_missing"]}


def matrix(rows, fields):
    return np.array([[np.nan if row[f] is None else row[f] for f in fields] for row in rows], dtype=float)


def training_rows(reader, features, fit_day, start):
    labels = reader.labels_at(fit_day)
    rows, y = [], []
    for row in features:
        if start <= date.fromisoformat(row["delivery_date"]) < fit_day:
            value = labels.get(stamp(row["delivery_utc"]))
            if value is not None:
                rows.append(row)
                y.append(value)
    if not rows:
        raise ValueError("No eligible training labels")
    return rows, np.asarray(y)


def simple_estimate(row, medians):
    available = [row[f"price_lag_{d}"] for d in (1, 7) if row[f"price_lag_{d}"] is not None]
    return float(np.mean(available)) if available else medians.get(row["quarter_of_day"])


def quarter_medians(labels, minimum):
    values = defaultdict(list)
    for timestamp, value in labels.items():
        local = timestamp.astimezone(BERLIN)
        if value is not None:
            values[local.hour * 4 + local.minute // 15].append(value)
    return {q: float(np.median(v)) for q, v in values.items() if len(v) >= minimum}


def fit_reference(reader, rows, y, fit_day, config):
    history_start = date.fromisoformat(config["history_start"])
    labels = {t: v for t, v in reader.labels_at(fit_day).items() if t.astimezone(BERLIN).date() >= history_start}
    medians = quarter_medians(labels, config["reference_min_per_quarter"])
    if set(medians) != set(range(96)):
        raise ValueError("Insufficient reference history for every local quarter")
    past, errors, excluded = {}, [], 0
    for row, actual in zip(rows, y):
        day = date.fromisoformat(row["delivery_date"])
        if day not in past:
            earlier = {t: v for t, v in reader.labels_at(day).items() if t.astimezone(BERLIN).date() >= history_start}
            past[day] = quarter_medians(earlier, config["reference_min_per_quarter"])
        estimate = simple_estimate(row, past[day])
        if estimate is None:
            excluded += 1
        else:
            errors.append(actual - estimate)
    if len(errors) < config["reference_min_errors"]:
        raise ValueError("Insufficient eligible reference calibration errors")
    return {"medians": medians, "offsets": np.quantile(errors, QUANTILES, method="linear").tolist(),
            "calibration_rows": len(errors), "excluded_rows": excluded}


def reference_predict(rows, reference):
    medians = {int(k): v for k, v in reference["medians"].items()}
    return np.array([simple_estimate(row, medians) for row in rows])[:, None] + np.asarray(reference["offsets"])


def fit_models(rows, y, config, directory):
    directory.mkdir(parents=True, exist_ok=True)
    models, failures = {}, {}
    for name, fields in config["features"].items():
        model = CatBoostRegressor(**config["catboost"])
        try:
            model.fit(matrix(rows, fields), y)
            model.save_model(str(directory / f"{name}.cbm"))
            models[name] = model
        except (CatBoostError, ValueError) as error:
            failures[name] = str(error)
    return models, failures


def predict_day(rows, models, reference, config):
    ref = reference_predict(rows, reference)
    raw, predictions, failures, crossing = {}, {}, {}, {}
    for name, fields in config["features"].items():
        try:
            if name not in models:
                raise ValueError("Model fit failed")
            q = np.asarray(models[name].predict(matrix(rows, fields)))
            if q.shape != (len(rows), 5) or not np.isfinite(q).all():
                raise ValueError("Non-finite or incomplete model output")
            raw[name], predictions[name] = q, np.sort(q, axis=1)
            crossing[name] = int((np.diff(q, axis=1) < 0).any(axis=1).sum())
        except (CatBoostError, ValueError) as error:
            failures[name] = str(error)
            raw[name], predictions[name], crossing[name] = ref, ref, 0
    reasons = []
    chosen = "reference"
    for name in ("demand", "weather", "prices"):
        if rows[0]["price_lags_unavailable"]:
            reasons.append(f"{name}:price_lags_unavailable")
        elif name in failures:
            reasons.append(f"{name}:prediction_failure")
        elif name in ("demand", "weather") and rows[0]["weather_source_unavailable"]:
            reasons.append(f"{name}:weather_source_unavailable")
        elif name == "demand" and rows[0]["demand_source_unavailable"]:
            reasons.append("demand:demand_source_unavailable")
        elif name == "prices" and rows[0]["price_lags_unavailable"]:
            reasons.append("prices:price_lags_unavailable")
        else:
            chosen = name
            break
    predictions.update(reference=ref, system=predictions.get(chosen, ref))
    return raw, predictions, failures, crossing, chosen, ";".join(reasons)


def next_month(day):
    return date(day.year + (day.month == 12), day.month % 12 + 1, 1)


def evaluate(reader, config, output, restore_models=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    history_start, train_start, start, end = [date.fromisoformat(config[k]) for k in
                                            ("history_start", "train_start", "evaluation_start", "end_exclusive")]
    if not history_start <= train_start < start < end or start.day != 1 or end.day != 1:
        raise ValueError("Invalid chronological monthly fold dates")
    if config["features"] != FEATURES or config["quantiles"] != QUANTILES.tolist():
        raise ValueError("Feature/quantile contract changed")
    # Features are selected at each historical issue; labels are joined separately per fit.
    features, day = [], history_start
    while day < end:
        features.extend(reader.features(day))
        day += timedelta(days=1)
    pq.write_table(pa.Table.from_pylist(features), output / "features.parquet", compression="zstd")
    by_day = defaultdict(list)
    for row in features:
        by_day[row["delivery_date"]].append(row)
    predictions, fold_reports, failures, fallback, crossings = [], [], [], Counter(), Counter()
    fold = start
    while fold < end:
        stop = min(next_month(fold), end)
        print(f"Fitting fold {fold} -> {stop}", flush=True)
        train, y = training_rows(reader, features, fold, train_start)
        directory = output / "models" / fold.isoformat()
        reference = fit_reference(reader, train, y, fold, config)
        if restore_models:
            source = Path(restore_models) / fold.isoformat()
            fit_failures = json.loads((source / "failures.json").read_text())
            models = {}
            for name in config["features"]:
                if name not in fit_failures:
                    models[name] = CatBoostRegressor().load_model(str(source / f"{name}.cbm"))
            directory.mkdir(parents=True, exist_ok=True)
        else:
            models, fit_failures = fit_models(train, y, config, directory)
        (directory / "reference.json").write_text(json.dumps(reference, sort_keys=True))
        (directory / "failures.json").write_text(json.dumps(fit_failures, sort_keys=True))
        fold_reports.append({"first_delivery_day": fold.isoformat(), "end_exclusive": stop.isoformat(),
                             "fit_cutoff": cutoff(fold).isoformat(),
                             "training_rows": len(train), "reference": reference, "fit_failures": fit_failures})
        day = fold
        while day < stop:
            rows = by_day[day.isoformat()]
            raw, ordered, failed, crossed, chosen, reason = predict_day(rows, models, reference, config)
            if failed:
                failures.append({"day": day.isoformat(), "models": failed})
            crossings.update(crossed)
            fallback[chosen] += len(rows)
            for i, row in enumerate(rows):
                record = {k: row[k] for k in ("delivery_utc", "delivery_date", "demand_available")}
                record.update(target=reader.truth.get(stamp(row["delivery_utc"])), selected_model=chosen, fallback_reason=reason,
                              fold=fold.isoformat(),
                              **{k: v for k, v in row.items() if k.endswith(("_missing", "_unavailable")) or k == "demand_selected_update_utc"})
                for name, q in ordered.items():
                    for j, quantile in enumerate(config["quantiles"]):
                        record[f"{name}_q{quantile}"] = float(q[i, j])
                for name, q in raw.items():
                    for j, quantile in enumerate(config["quantiles"]):
                        record[f"{name}_raw_q{quantile}"] = float(q[i, j])
                predictions.append(record)
            day += timedelta(days=1)
        fold = stop
    pq.write_table(pa.Table.from_pylist(predictions), output / "predictions.parquet", compression="zstd")
    scored = [r for r in predictions if r["target"] is not None]
    if not scored:
        raise ValueError("No evaluation truth")
    names = [*config["features"], "reference", "system"]
    def scores(rows):
        return {name: metrics([r["target"] for r in rows],
                              [[r[f"{name}_q{q}"] for q in config["quantiles"]] for r in rows],
                              [r["delivery_date"] for r in rows]) for name in names}
    groups = {"month": defaultdict(list), "demand_available": defaultdict(list)}
    for row in predictions:
        groups["month"][row["delivery_date"][:7]].append(row)
        groups["demand_available"][str(row["demand_available"])].append(row)
    report = {"metrics": scores(scored), "breakdowns": {k: {g: {"delivery_rows": len(v), "missing_truth": sum(r["target"] is None for r in v),
                                               "forecast_coverage": 1., "metrics": scores([r for r in v if r["target"] is not None])}
                                    for g, v in groups[k].items()} for k in groups},
              "comparison": paired_blocks(np.array([r["target"] for r in scored]),
                                          {n: np.array([[r[f"{n}_q{q}"] for q in config["quantiles"]] for r in scored]) for n in names},
                                          [r["delivery_date"] for r in scored], config["bootstrap"]),
              "delivery_rows": len(predictions), "scored_rows": len(scored), "missing_truth": len(predictions) - len(scored),
              "forecast_coverage": 1., "fallback_rows": dict(fallback), "prediction_failures": failures,
              "raw_crossing_rows": dict(crossings), "raw_crossing_fraction": {n: v / len(predictions) for n, v in crossings.items()},
              "folds": fold_reports, "timing_limits": TIMING,
              "limitations": ["Retrospective single-year evaluation; August–September were inspected in earlier diagnostics.",
                              "Historical price/weather availability assumed; demand UpdateTime semantics conditional.",
                              "Intervals are marginal per quarter; no trading-profitability or daily-readiness claim."]}
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    return report
