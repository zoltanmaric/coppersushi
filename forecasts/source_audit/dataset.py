"""Build retrospective source coverage from archived weather, demand and prices."""
import argparse
from collections import Counter, defaultdict
from collections.abc import Collection, Mapping, Sequence
import csv
from datetime import date, timedelta
from functools import cache
import json
from pathlib import Path
import platform

import pandera.polars as pa
from pandera.typing.polars import DataFrame
import polars as pl
import pyarrow as arrow

from forecasts.inputs.input_config import WEATHER_FIELDS, WEATHER_LOCATIONS, WEATHER_TABLE_FIELDS
from forecasts.inputs.input_types import DemandSeries, PriceSeries, Report, Row, WeatherSeries
from forecasts.inputs.prices import PriceHistory, UTC
from forecasts.inputs.selection import InputReader, select_covariates, select_demand
from forecasts.inputs.snapshot import read_local
from forecasts.inputs.sources import (
    COUNTRY, END, PAYLOADS, START, TIMING, load_demand, load_prices, load_weather, verify_payloads,
)
from forecasts.provenance import ROOT, digest
from forecasts.market import BERLIN, cutoff, quarters
from forecasts.model.calendar import CLOCK_COLUMNS, assemble_price_calendar
from forecasts.config import CALENDAR_COLUMNS, PRICE_FEATURES, PRICE_UNAVAILABLE
from forecasts.model.features import build_day_features
from forecasts.model.price_features import build_price_features
from forecasts.model.tables import Features

TIMING_COLUMNS = ("price_timing_assumed", "weather_timing_assumed", "demand_timing_conditional")
DEMAND_COLUMNS = ("demand_mw", "demand_available", "demand_missing", "demand_selected_update_utc",
                  "demand_screen", "demand_archive_versions", "demand_archived_latest_update_utc")
WEATHER_MISSING_FIELDS = [f"{field}_missing" for field in WEATHER_FIELDS]
SOURCE_FLAGS = ("demand_source_unavailable", "weather_source_unavailable", PRICE_UNAVAILABLE)


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
    frames = []
    for day in days:
        deadline = cutoff(day)
        selected = select_covariates({name: by_day[day] for name, by_day in daily.items()}, day, deadline, False)
        weather, demand = _covariate_inputs(selected, daily["demand"][day])
        frames.append(_assemble_features(build_day_features(reader, day), weather, demand))
    return _diagnostic_rows(DiagnosticFeatures.validate(pl.concat(frames)), reader.realized_prices(), WEATHER_TABLE_FIELDS)


def build_rows(prices: PriceSeries, weather: WeatherSeries, demand: DemandSeries, start: date = START, end: date = END, targets: PriceSeries | None = None) -> list[Row]:
    """Adapt unversioned archive values for the raw diagnostic CLI."""
    history = PriceHistory.validate(pl.DataFrame(
        {"valid_utc": list(prices), "price_eur_mwh": list(prices.values())},
        schema={"valid_utc": pl.Datetime("us", "UTC"), "price_eur_mwh": pl.Float64}))
    price_features = build_price_features(history, list(quarters(start, end)))
    price_calendar = assemble_price_calendar(price_features)
    features = DiagnosticFeatures.validate(_assemble_features(price_calendar, weather, demand))
    return _diagnostic_rows(features, prices if targets is None else targets, list(weather))


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


class DiagnosticFeatures(Features):
    """Historical source coverage, including weather and demand evidence."""

    weather_timing_assumed: int = pa.Field(eq=1)
    demand_timing_conditional: int = pa.Field(eq=1)
    demand_mw: float = pa.Field(nullable=True)
    demand_available: int = pa.Field(isin=[0, 1])
    demand_missing: int = pa.Field(isin=[0, 1])
    demand_selected_update_utc: UTC = pa.Field(nullable=True)
    demand_screen: str
    demand_archive_versions: int = pa.Field(ge=0)
    demand_archived_latest_update_utc: UTC = pa.Field(nullable=True)

    @classmethod
    @cache
    def to_schema(cls) -> pa.DataFrameSchema:
        """Add the fixed weather inventory and its per-column missing flags."""
        schema = super().to_schema()
        columns = {name: pa.Column(float, nullable=True, checks=pa.Check(_finite))
                   for name in WEATHER_FIELDS}
        columns.update({name: pa.Column(int, checks=pa.Check.isin([0, 1]))
                        for name in [*WEATHER_MISSING_FIELDS, "demand_source_unavailable", "weather_source_unavailable"]})
        return schema.add_columns(columns)

    @pa.dataframe_check
    @classmethod
    def valid_demand(cls, data: pa.PolarsData) -> pl.LazyFrame:
        """Allow missing demand and reject non-finite values."""
        return data.lazyframe.select(pl.col("demand_mw").is_null() | pl.col("demand_mw").is_finite())


def _assemble_features(price_calendar: pl.DataFrame, weather: WeatherSeries,
                       demand: DemandSeries) -> pl.DataFrame:
    """Join weather and demand for the historical source diagnostic."""
    rows = []
    for timestamp, deadline in price_calendar.select("delivery_utc", "issue_cutoff_utc").iter_rows():
        hour = timestamp.replace(minute=0)
        versions = demand.get(timestamp, [])
        value, updated, reason = select_demand(versions, deadline)
        archived_updates = [v["updated"] for v in versions if v["updated"] is not None]
        row: Row = {
            "weather_timing_assumed": 1, "demand_timing_conditional": 1,
            "demand_mw": value, "demand_available": int(value is not None), "demand_missing": int(value is None),
            "demand_selected_update_utc": updated, "demand_screen": reason, "demand_archive_versions": len(versions),
            "demand_archived_latest_update_utc": max(archived_updates, default=None),
        }
        row.update({name: values.get(hour) for name, values in weather.items()})
        rows.append(row)
    columns = DiagnosticFeatures.to_schema().columns
    source_schema = {name: columns[name].dtype.type for name in (*TIMING_COLUMNS[1:], *WEATHER_FIELDS, *DEMAND_COLUMNS)}
    features = price_calendar.hstack(pl.DataFrame(rows, schema=source_schema)).with_columns(
        *[pl.col(name).is_null().cast(pl.Int64).alias(name + "_missing") for name in WEATHER_FIELDS],
        _all_missing(["demand_mw"]).alias("demand_source_unavailable"),
        _all_missing(WEATHER_FIELDS).alias("weather_source_unavailable"),
    )
    return features.select(*CLOCK_COLUMNS, *_feature_columns(WEATHER_TABLE_FIELDS))


def _diagnostic_rows(features: DataFrame[DiagnosticFeatures], targets: PriceSeries, weather_fields: Sequence[str]) -> list[Row]:
    """Join retrospective truth and serialize clocks for the diagnostic CSV."""
    rows = []
    for row in features.select(*CLOCK_COLUMNS, *_feature_columns(weather_fields)).to_dicts():
        target = targets.get(row["delivery_utc"])
        for name in ("delivery_utc", "delivery_date", "issue_cutoff_utc", "demand_selected_update_utc",
                     "demand_archived_latest_update_utc"):
            if row[name] is not None:
                row[name] = row[name].isoformat()
        clocks = {key: row.pop(key) for key in CLOCK_COLUMNS}
        rows.append(dict(clocks, price_eur_mwh=target, target_missing=int(target is None), **row))
    return rows


def _all_missing(fields: Sequence[str]) -> pl.Expr:
    return pl.all_horizontal(pl.col(fields).is_null()).all().over("delivery_date").cast(pl.Int64)


def _feature_columns(weather_fields: Sequence[str]) -> list[str]:
    return [*CALENDAR_COLUMNS, *TIMING_COLUMNS, *PRICE_FEATURES, *[f"{name}_missing" for name in PRICE_FEATURES],
            *[key for name in weather_fields for key in (name, name + "_missing")], *DEMAND_COLUMNS, *SOURCE_FLAGS]


def _covariate_inputs(selected: Mapping[str, list[Row]], archive: list[Row]) -> tuple[WeatherSeries, DemandSeries]:
    weather: WeatherSeries = {}
    demand: DemandSeries = {}
    for row in selected["weather"]:
        key = f"{row['variable']}_{row['location']}"
        values = weather.setdefault(key, {})
        if row["valid_utc"] in values and values[row["valid_utc"]] != row["value"]:
            raise ValueError("Ambiguous eligible weather versions")
        values[row["valid_utc"]] = row["value"]
    eligible_keys = {(row["valid_utc"], row["version_id"]) for row in selected["demand"]}
    for row in archive:
        if row["area_code"] == COUNTRY:
            timestamp = row["valid_utc"]
            demand.setdefault(timestamp, []).append({
                "updated": row["source_update_utc"], "value": row["demand_mw"], "source": row["raw_key"],
                "eligible_at_issue": (timestamp, row["version_id"]) in eligible_keys,
            })
    return weather, demand


def _finite(data: pa.PolarsData) -> pl.LazyFrame:
    return data.lazyframe.select(pl.col(data.key).is_finite())


if __name__ == "__main__":
    main()
