"""Build retrospective source coverage from archived weather, demand and prices."""
import argparse
from collections import Counter, defaultdict
from collections.abc import Collection, Mapping, Sequence
import csv
from datetime import date, timedelta
import json
from pathlib import Path
import platform

from pandera.typing.polars import DataFrame
import polars as pl
import pyarrow as arrow

from forecasts.inputs.input_config import WEATHER_FIELDS, WEATHER_LOCATIONS, WEATHER_TABLE_FIELDS
from forecasts.inputs.input_types import DemandSeries, PriceSeries, Report, Row, WeatherSeries
from forecasts.inputs.prices import PriceHistory
from forecasts.inputs.selection import InputReader, select_covariates, select_demand
from forecasts.inputs.snapshot import read_local
from forecasts.inputs.sources import (
    END, PAYLOADS, START, TIMING, load_demand, load_prices, load_weather, verify_payloads,
)
from forecasts.provenance import ROOT, digest
from forecasts.market import BERLIN, cutoff, quarters
from forecasts.source_audit.price_features import PriceFeatures, build_price_features


def main() -> None:
    """Build and save the diagnostic dataset from local inputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=ROOT / "data/forecasts")
    parser.add_argument("--snapshot", type=Path, help="Validated local snapshot loaded from S3; no source-provider calls")
    parser.add_argument("--output", type=Path, default=ROOT / "data/forecasts/dataset")
    args = parser.parse_args()
    if args.snapshot:
        manifest, tables = read_local(args.snapshot)
        inputs = manifest["raw"]
        metadata = {"snapshot_id": manifest["snapshot_id"]}
        rows = replay_snapshot(tables, START, END)
        weather_fields = WEATHER_FIELDS
    else:
        inputs = verify_payloads(args.data_root)
        print("Verified three input archives", flush=True)
        prices = load_prices(args.data_root / PAYLOADS["prices"])
        weather, metadata = load_weather(args.data_root / PAYLOADS["weather"], WEATHER_LOCATIONS)
        demand = load_demand(args.data_root / PAYLOADS["demand"], START, END)
        rows = build_rows(prices, weather, demand)
        weather_fields = list(weather)
    counts = summarize(rows, weather_fields)
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / "quarters.csv"
    with path.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    report = {"start": START.isoformat(), "end_exclusive": END.isoformat(), "timezone": "Europe/Berlin",
              "counts": counts, "inputs": inputs, "weather": metadata,
              "timing_limits": TIMING, "prices_attribution": "Bundesnetzagentur | SMARD.de",
              "transformations": {"price_lags_days": [1, 2, 7, 14], "price_daily_summaries_days": [1, 7],
                                  "clock_match": "same local quarter; average duplicates; nonexistent quarters missing",
                                  "weather": "repeat UTC hours across quarters; radiation shifted back one hour; gaps missing",
                                  "demand": "latest retained nonmissing country version updated by preceding-day 11:00 Berlin",
                                  "calendar": "quarter of day, Monday=0 weekday, month, nationwide German holidays"},
              "runtime": {"python": platform.python_version(), "inputs": "typed Parquet snapshot" if args.snapshot else "raw archive diagnostic"},
              "implementation_sha256": digest(Path(__file__)),
              "dataset": {"file": path.name, "sha256": digest(path), "columns": list(rows[0])}}
    (args.output / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(counts, indent=2), flush=True)


def replay_snapshot(tables: Mapping[str, arrow.Table], start: date, end: date) -> list[Row]:
    """Replay the full archived snapshot and attach retrospective price outcomes."""
    if start >= end:
        raise ValueError("Feature start must precede end")
    daily: dict[str, defaultdict[date, list[Row]]] = {name: defaultdict(list) for name in ("weather", "demand")}
    missing = sorted(daily.keys() - tables.keys())
    if missing:
        raise ValueError(f"Archived-source diagnostic requires a full historical snapshot; missing {', '.join(missing)} tables")
    for name, by_day in daily.items():
        for row in tables[name].to_pylist():
            by_day[row["valid_utc"].astimezone(BERLIN).date()].append(row)
    reader = InputReader(tables)
    days = (start + timedelta(days=offset) for offset in range((end - start).days))
    rows = []
    targets = reader.realized_prices()
    for day in days:
        deadline = cutoff(day)
        selected = select_covariates({name: by_day[day] for name, by_day in daily.items()}, day, deadline, False)
        weather, demand = _covariate_inputs(selected)
        history = reader.price_history(day, deadline, earliest_day=day - timedelta(days=14))
        features = build_price_features(history, list(quarters(day, day + timedelta(days=1))))
        rows.extend(assemble_rows(features, {field: weather.get(field, {}) for field in WEATHER_TABLE_FIELDS}, demand, targets))
    return rows


def build_rows(prices: PriceSeries, weather: WeatherSeries, demand: DemandSeries, start: date = START, end: date = END, targets: PriceSeries | None = None) -> list[Row]:
    """Adapt unversioned archive values to tables for the raw diagnostic CLI.

    Snapshot prediction keeps tables intact and calls assemble_rows directly.
    """
    history = PriceHistory.validate(pl.DataFrame(
        {"valid_utc": list(prices), "price_eur_mwh": list(prices.values())},
        schema={"valid_utc": pl.Datetime("us", "UTC"), "price_eur_mwh": pl.Float64}))
    features = build_price_features(history, list(quarters(start, end)))
    return assemble_rows(features, weather, demand, prices if targets is None else targets)


def assemble_rows(price_features: DataFrame[PriceFeatures], weather: WeatherSeries,
                  demand: DemandSeries, targets: PriceSeries) -> list[Row]:
    """Join price features with calendar, weather, demand and optional outcomes.

    Convert price features to records only here, at the shared assembly boundary.
    Prediction passes empty targets; retrospective replay joins truth separately.
    """
    price_rows = price_features.to_dicts()
    years = {row["delivery_utc"].astimezone(BERLIN).year for row in price_rows}
    rows = []
    holiday_dates = set().union(*(holidays(y) for y in years))
    for price_row in price_rows:
        timestamp = price_row["delivery_utc"]
        local = timestamp.astimezone(BERLIN)
        day, quarter = local.date(), local.hour * 4 + local.minute // 15
        deadline = cutoff(day)
        offset = local.utcoffset()
        assert offset is not None  # local is explicitly Europe/Berlin-aware.
        row: Row = {"delivery_utc": timestamp.isoformat(), "delivery_date": day.isoformat(), "issue_cutoff_utc": deadline.isoformat(),
               "utc_offset_minutes": int(offset.total_seconds() / 60), "clock_fold": local.fold,
               "price_eur_mwh": targets.get(timestamp), "target_missing": int(targets.get(timestamp) is None),
               "quarter_of_day": quarter, "day_of_week": local.weekday(), "month": local.month,
               "public_holiday": int(day in holiday_dates), "price_timing_assumed": 1,
               "weather_timing_assumed": 1, "demand_timing_conditional": 1}
        row.update({key: value for key, value in price_row.items() if key != "delivery_utc"})
        for key in list(row):
            if key.startswith(("price_lag_", "price_day_")):
                row[key + "_missing"] = int(row[key] is None)
        hour = timestamp.replace(minute=0)
        for field, values in weather.items():
            row[field] = values.get(hour)
            row[field + "_missing"] = int(row[field] is None)
        value, updated, reason = select_demand(demand.get(timestamp, []), deadline)
        archived_updates = [v["updated"] for v in demand.get(timestamp, []) if v["updated"] is not None]
        row.update(demand_mw=value, demand_available=int(value is not None), demand_missing=int(value is None),
                   demand_selected_update_utc=updated.isoformat() if updated else None, demand_screen=reason,
                   demand_archive_versions=len(demand.get(timestamp, [])),
                   demand_archived_latest_update_utc=max(archived_updates).isoformat() if archived_updates else None)
        rows.append(row)
    by_day: dict[str, list[Row]] = defaultdict(list)
    for row in rows:
        by_day[row["delivery_date"]].append(row)
    for daily in by_day.values():
        demand_absent = int(all(r["demand_missing"] for r in daily))
        weather_absent = int(all(r[f] is None for r in daily for f in weather))
        prices_absent = int(all(r[f"price_lag_{d}"] is None for r in daily for d in (1, 2, 7, 14)))
        for row in daily:
            row.update(demand_source_unavailable=demand_absent, weather_source_unavailable=weather_absent,
                       price_lags_unavailable=prices_absent)
    return rows


def summarize(rows: list[Row], weather_fields: Collection[str]) -> Report:
    """Count coverage and missing inputs without dropping delivery rows."""
    daily = Counter(r["delivery_date"] for r in rows)
    return {
        "rows": len(rows), "days": len(daily), "target_missing": sum(r["target_missing"] for r in rows),
        "negative_prices": sum(r["price_eur_mwh"] is not None and r["price_eur_mwh"] < 0 for r in rows),
        "clock_change_days": {day: n for day, n in daily.items() if n != 96},
        "demand_usable": sum(r["demand_available"] for r in rows),
        "demand_unusable": sum(r["demand_missing"] for r in rows),
        "demand_unavailable_days": len({r["delivery_date"] for r in rows if r["demand_source_unavailable"]}),
        "weather_missing_quarters": {f: sum(r[f + "_missing"] for r in rows) for f in weather_fields},
        "price_feature_missing_quarters": {f: sum(r[f + "_missing"] for r in rows) for f in rows[0] if f.startswith(("price_lag_", "price_day_")) and not f.endswith("_missing")},
    }


def holidays(year: int) -> set[date]:
    # Gregorian Easter (Meeus/Jones/Butcher); only nationwide German holidays.
    """Return nationwide German holidays for the supplied year."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    easter = date(year, (h + l - 7 * m + 114) // 31, (h + l - 7 * m + 114) % 31 + 1)
    return {date(year, month, day) for month, day in [(1, 1), (5, 1), (10, 3), (12, 25), (12, 26)]} | {
        easter + timedelta(days=offset) for offset in [-2, 1, 39, 50]
    }


def _covariate_inputs(selected: Mapping[str, list[Row]]) -> tuple[WeatherSeries, DemandSeries]:
    weather: WeatherSeries = {}
    demand: DemandSeries = {}
    for row in selected["weather"]:
        key = f"{row['variable']}_{row['location']}"
        values = weather.setdefault(key, {})
        if row["valid_utc"] in values and values[row["valid_utc"]] != row["value"]:
            raise ValueError("Ambiguous eligible weather versions")
        values[row["valid_utc"]] = row["value"]
    for row in selected["demand"]:
        demand.setdefault(row["valid_utc"], []).append({"updated": row["source_update_utc"], "value": row["demand_mw"], "source": row["raw_key"]})
    return weather, demand


if __name__ == "__main__":
    main()
