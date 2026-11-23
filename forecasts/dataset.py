"""Build an all-date replay from immutable, hash-verified evidence snapshots."""
from collections.abc import Collection, Iterator, Sequence
from forecasts.input_config import FIELDS, WEATHER_FIELDS, WEATHER_LOCATIONS, WEATHER_TABLE_FIELDS
import polars as pl
from pandera.typing.polars import DataFrame
from forecasts.prices import LAGS, PRICE_FEATURES, PriceFeatures, PriceHistory, build_price_features
from forecasts.input_types import DemandSeries, DemandVersion, PriceSeries, Report, Row, WeatherSeries
from forecasts.tables import DiagnosticFeatures, Features, PRICE_UNAVAILABLE, SOURCE_FLAGS
import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import platform
import zipfile
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")
UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[1]
COUNTRY = "10Y1001A1001A83F"
START, END = date(2025, 10, 1), date(2026, 10, 1)
BASELINE_INPUTS = json.loads((ROOT / "forecasts/data/baseline-inputs.json").read_text())
PAYLOADS = {source: entry["path"] for source, entry in BASELINE_INPUTS.items()}
TIMING = {
    "prices": "Assume auction prices for earlier delivery dates are available at issue time; SMARD publication latency and revisions are unaudited.",
    "weather": "Assume documented previous_day2 fixed 48-hour lead; original publication times are unknown. Retrospective retrieval is not witnessed availability.",
    "demand": "Conditional on UpdateTime(UTC) describing availability; retain only archived versions updated by cutoff. Later revisions cannot recover overwritten earlier values.",
}
CLOCK_COLUMNS = ("delivery_utc", "delivery_date", "issue_cutoff_utc", "utc_offset_minutes", "clock_fold")
CALENDAR_COLUMNS = ("quarter_of_day", "day_of_week", "month", "public_holiday")
TIMING_COLUMNS = ("price_timing_assumed", "weather_timing_assumed", "demand_timing_conditional")
DEMAND_COLUMNS = ("demand_mw", "demand_available", "demand_missing", "demand_selected_update_utc",
                  "demand_screen", "demand_archive_versions", "demand_archived_latest_update_utc")


def stamp(value: str) -> datetime:
    """Parse a source timestamp as an aware UTC datetime."""
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def cutoff(day: date) -> datetime:
    """Return the preceding-day 11:00 Berlin issue deadline in UTC."""
    return datetime.combine(day - timedelta(days=1), time(11), BERLIN).astimezone(UTC)


def quarters(start: date, end: date) -> Iterator[datetime]:
    """Yield actual UTC delivery quarters in the local-date interval [start, end)."""
    current = datetime.combine(start, time(), BERLIN).astimezone(UTC)
    stop = datetime.combine(end, time(), BERLIN).astimezone(UTC)
    while current < stop:
        yield current
        current += timedelta(minutes=15)


def number(value: str | int | float | None) -> float | None:
    """Parse a finite source number; preserve missing values as None."""
    if value in (None, "", "n/e"):
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Non-finite source value")
    return result


def digest(path: Path) -> str:
    """Return the SHA-256 digest of a file."""
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def verify_payloads(data_root: Path) -> dict[str, Report]:
    """Verify archived source bytes against the recorded payload manifest."""
    result = {}
    for source, relative in PAYLOADS.items():
        path = data_root / relative
        entry = BASELINE_INPUTS[source]
        if path.stat().st_size != entry["bytes"] or digest(path) != entry["sha256"]:
            raise ValueError(f"Snapshot checksum mismatch: {relative}")
        result[source] = {"path": relative, "bytes": entry["bytes"], "sha256": entry["sha256"]}
    return result


def load_prices(path: Path) -> PriceSeries:
    """Load validated quarter-hour prices from the source archive."""
    prices: PriceSeries = {}
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            if not name.startswith("prices/") or not name.endswith(".json") or name == "prices/index.json":
                continue
            for milliseconds, value in json.loads(archive.read(name))["series"]:
                timestamp = datetime.fromtimestamp(milliseconds / 1000, UTC)
                if timestamp.second or timestamp.microsecond or timestamp.minute % 15:
                    raise ValueError("Price timestamp is not a delivery quarter")
                value = number(value)
                if timestamp in prices and prices[timestamp] != value:
                    raise ValueError(f"Conflicting price snapshots at {timestamp}")
                prices[timestamp] = value
    return prices


def load_weather(path: Path, locations: Sequence[tuple[str, float, float]]) -> tuple[WeatherSeries, Report]:
    """Load hourly forecast fields and align radiation to the preceding hour."""
    with zipfile.ZipFile(path) as archive:
        snapshot = json.loads(archive.read("history.json"))
    payload = snapshot["data"]
    if len(payload) != len(locations):
        raise ValueError("Weather location count differs from design")
    frames, metadata = {}, []
    for (name, latitude, longitude), point in zip(locations, payload):
        if abs(point["latitude"] - latitude) > .15 or abs(point["longitude"] - longitude) > .15:
            raise ValueError(f"Weather grid does not match {name}")
        if point["utc_offset_seconds"] != 0:
            raise ValueError("Weather timestamps must use UTC")
        times = point["hourly"]["time"]
        if len(set(times)) != len(times) or any(t % 3600 for t in times):
            raise ValueError("Weather timestamps are duplicated or not hourly")
        metadata.append({"name": name, "requested_latitude": latitude, "requested_longitude": longitude,
                         "grid_latitude": point["latitude"], "grid_longitude": point["longitude"], "elevation": point["elevation"]})
        for field, unit in FIELDS.items():
            key = field + "_previous_day2"
            values = point["hourly"][key]
            if point["hourly_units"][key] != unit or len(values) != len(times):
                raise ValueError(f"Weather unit/length mismatch: {name}/{field}")
            shift = 3600 if field == "shortwave_radiation" else 0
            frames[f"{field}_{name.lower()}"] = {
                datetime.fromtimestamp(t - shift, UTC): number(v) for t, v in zip(times, values)
            }
    return frames, {"request_url": snapshot["url"], "retrieved_at_utc": snapshot["retrieved_at_utc"], "locations": metadata}


def load_demand(path: Path, start: date, end: date, *,
                require_country_metadata: bool = False) -> DemandSeries:
    """Load archived country-demand versions for local dates in [start, end)."""
    versions: DemandSeries = defaultdict(list)
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            if not name.endswith(".csv") or "DayAheadTotalLoadForecast_6.1.B_r3" not in name:
                continue
            with archive.open(name) as raw:
                for row in csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig"), delimiter="\t"):
                    if row["AreaCode"] != COUNTRY:
                        continue
                    if require_country_metadata and (row.get("AreaTypeCode"), row.get("AreaMapCode")) != ("CTY", "DE"):
                        raise ValueError("Expected Germany country metadata in the File Library extract")
                    timestamp = stamp(row["DateTime(UTC)"])
                    if not start <= timestamp.astimezone(BERLIN).date() < end:
                        continue
                    if row["ResolutionCode"] != "PT15M" or timestamp.minute % 15 or timestamp.second:
                        raise ValueError("Unexpected country demand resolution")
                    versions[timestamp].append({"updated": stamp(row["UpdateTime(UTC)"]) if row["UpdateTime(UTC)"] else None,
                                                "value": number(row["TotalLoad[MW]"]), "source": name})
    return versions


def select_demand(versions: list[DemandVersion], deadline: datetime) -> tuple[float | None, datetime | None, str]:
    """Select the latest nonmissing version eligible by the issue deadline."""
    usable = [v for v in versions if v["updated"] is not None and v["updated"] <= deadline and v["value"] is not None]
    if usable:
        latest = max(v["updated"] for v in usable if v["updated"] is not None)
        selected = [v for v in usable if v["updated"] == latest]
        if len({v["value"] for v in selected}) != 1:
            raise ValueError("Conflicting demand values at the same update time")
        return selected[0]["value"], latest, "usable"
    reason = "absent" if not versions else "late_or_missing_update_or_value"
    return None, None, reason


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


def build_rows(prices: PriceSeries, weather: WeatherSeries, demand: DemandSeries, start: date = START, end: date = END, targets: PriceSeries | None = None) -> list[Row]:
    """Adapt unversioned archive values for the raw diagnostic CLI."""
    history = PriceHistory.validate(pl.DataFrame(
        {"valid_utc": list(prices), "price_eur_mwh": list(prices.values())},
        schema={"valid_utc": pl.Datetime("us", "UTC"), "price_eur_mwh": pl.Float64}))
    price_features = build_price_features(history, list(quarters(start, end)))
    features = DiagnosticFeatures.validate(assemble_features(price_features, weather, demand))
    return diagnostic_rows(features, prices if targets is None else targets, list(weather))


def assemble_price_calendar(price_features: DataFrame[PriceFeatures]) -> pl.DataFrame:
    """Add Berlin delivery clocks, calendar values and price coverage flags."""
    timestamps = price_features["delivery_utc"].to_list()
    local_times = [timestamp.astimezone(BERLIN) for timestamp in timestamps]
    holiday_dates = set().union(*(holidays(year) for year in {local.year for local in local_times}))
    deadlines = {day: cutoff(day) for day in {local.date() for local in local_times}}
    rows = []
    for timestamp, local in zip(timestamps, local_times, strict=True):
        day = local.date()
        deadline = deadlines[day]
        offset = local.utcoffset()
        assert offset is not None  # local is explicitly Europe/Berlin-aware.
        rows.append({
            "delivery_date": day, "issue_cutoff_utc": deadline, "utc_offset_minutes": int(offset.total_seconds() / 60),
            "clock_fold": local.fold, "quarter_of_day": local.hour * 4 + local.minute // 15,
            "day_of_week": local.weekday(), "month": local.month, "public_holiday": int(day in holiday_dates),
            "price_timing_assumed": 1,
        })
    columns = Features.to_schema().columns
    schema = {name: columns[name].dtype.type for name in (*CLOCK_COLUMNS[1:], *CALENDAR_COLUMNS, TIMING_COLUMNS[0])}
    return price_features.hstack(pl.DataFrame(rows, schema=schema)).with_columns(
        *[pl.col(name).is_null().cast(pl.Int64).alias(name + "_missing") for name in PRICE_FEATURES],
        _all_missing([f"price_lag_{day}" for day in LAGS]).alias(PRICE_UNAVAILABLE),
    )


def assemble_features(price_features: DataFrame[PriceFeatures], weather: WeatherSeries,
                      demand: DemandSeries) -> pl.DataFrame:
    """Join weather and demand for the historical source diagnostic."""
    price_calendar = assemble_price_calendar(price_features)
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


def diagnostic_rows(features: DataFrame[DiagnosticFeatures], targets: PriceSeries, weather_fields: Sequence[str]) -> list[Row]:
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


def main() -> None:
    """Build and save the diagnostic dataset from local inputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=ROOT / "data/forecasts")
    parser.add_argument("--snapshot", type=Path, help="Validated local snapshot loaded from S3; no source-provider calls")
    parser.add_argument("--output", type=Path, default=ROOT / "data/forecasts/dataset")
    args = parser.parse_args()
    if args.snapshot:
        from forecasts.snapshot import InputReader, read_local
        manifest, tables = read_local(args.snapshot)
        inputs = manifest["raw"]
        metadata = {"snapshot_id": manifest["snapshot_id"]}
        reader = InputReader(tables)
        rows = reader.replay(START, END)
        weather_fields = reader.weather_fields
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


if __name__ == "__main__":
    main()
