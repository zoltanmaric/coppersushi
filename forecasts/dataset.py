"""Build an all-date replay from immutable, hash-verified evidence snapshots."""
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
import statistics
import zipfile
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")
UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[1]
FIELDS = {"temperature_2m": "°C", "wind_speed_120m": "km/h", "shortwave_radiation": "W/m²"}
COUNTRY = "10Y1001A1001A83F"
START, END = date(2025, 10, 1), date(2026, 10, 1)
PAYLOADS = {
    "prices": "evidence/forecast-bounded-evidence-20261007/inputs.zip",
    "weather": "evidence/weather-compatibility-evidence-20261008/responses.zip",
    "demand": "entsoe-files.zip",
}
TIMING = {
    "prices": "Assume auction prices for earlier delivery dates are available at issue time; SMARD publication latency and revisions are unaudited.",
    "weather": "Assume documented previous_day2 fixed 48-hour lead; original publication times are unknown. Retrospective retrieval is not witnessed availability.",
    "demand": "Conditional on UpdateTime(UTC) describing availability; retain only archived versions updated by cutoff. Later revisions cannot recover overwritten earlier values.",
}


def stamp(value):
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def cutoff(day):
    return datetime.combine(day - timedelta(days=1), time(11), BERLIN).astimezone(UTC)


def quarters(start, end):
    current = datetime.combine(start, time(), BERLIN).astimezone(UTC)
    stop = datetime.combine(end, time(), BERLIN).astimezone(UTC)
    while current < stop:
        yield current
        current += timedelta(minutes=15)


def number(value):
    if value in (None, "", "n/e"):
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Non-finite source value")
    return result


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def verify_payloads(data_root):
    manifest = json.loads((ROOT / "forecasts/evidence/payload-manifest.json").read_text())
    expected = {p["path"].removeprefix("data/forecasts/"): p for p in manifest["payloads"]}
    result = {}
    for source, relative in PAYLOADS.items():
        path = data_root / relative
        entry = expected[relative]
        if path.stat().st_size != entry["bytes"] or digest(path) != entry["sha256"]:
            raise ValueError(f"Snapshot checksum mismatch: {relative}")
        result[source] = {"path": relative, "bytes": entry["bytes"], "sha256": entry["sha256"]}
    return result


def load_prices(path):
    prices = {}
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


class PriceHistory:
    def __init__(self, prices):
        self.clock = defaultdict(list)
        self.daily = defaultdict(list)
        for timestamp, value in prices.items():
            if value is not None:
                local = timestamp.astimezone(BERLIN)
                self.clock[local.date(), local.hour * 4 + local.minute // 15].append(value)
                self.daily[local.date()].append(value)
        self.daily_stats = {day: (statistics.mean(values), min(values), max(values)) for day, values in self.daily.items()}

    def lag(self, day, quarter, days):
        values = self.clock.get((day - timedelta(days=days), quarter), [])
        return statistics.mean(values) if values else None

    def summary(self, day, days):
        return self.daily_stats.get(day - timedelta(days=days), (None, None, None))


def load_weather(path, locations):
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


def load_demand(path, start, end):
    versions = defaultdict(list)
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            if not name.endswith(".csv") or "DayAheadTotalLoadForecast_6.1.B_r3" not in name:
                continue
            with archive.open(name) as raw:
                for row in csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig"), delimiter="\t"):
                    if row["AreaCode"] != COUNTRY:
                        continue
                    timestamp = stamp(row["DateTime(UTC)"])
                    if not start <= timestamp.astimezone(BERLIN).date() < end:
                        continue
                    if row["ResolutionCode"] != "PT15M" or timestamp.minute % 15 or timestamp.second:
                        raise ValueError("Unexpected country demand resolution")
                    versions[timestamp].append({"updated": stamp(row["UpdateTime(UTC)"]) if row["UpdateTime(UTC)"] else None,
                                                "value": number(row["TotalLoad[MW]"]), "source": name})
    return versions


def select_demand(versions, deadline):
    usable = [v for v in versions if v["updated"] is not None and v["updated"] <= deadline and v["value"] is not None]
    if usable:
        latest = max(v["updated"] for v in usable)
        selected = [v for v in usable if v["updated"] == latest]
        if len({v["value"] for v in selected}) != 1:
            raise ValueError("Conflicting demand values at the same update time")
        return selected[0]["value"], selected[0]["updated"].isoformat(), "usable"
    reason = "absent" if not versions else "late_or_missing_update_or_value"
    return None, None, reason


def holidays(year):
    # Gregorian Easter (Meeus/Jones/Butcher); only nationwide German holidays.
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


def build_rows(prices, weather, demand, start=START, end=END, targets=None):
    history = PriceHistory(prices)
    targets = prices if targets is None else targets
    rows = []
    holiday_dates = set().union(*(holidays(y) for y in range(start.year, end.year + 1)))
    for timestamp in quarters(start, end):
        local = timestamp.astimezone(BERLIN)
        day, quarter = local.date(), local.hour * 4 + local.minute // 15
        deadline = cutoff(day)
        row = {"delivery_utc": timestamp.isoformat(), "delivery_date": day.isoformat(), "issue_cutoff_utc": deadline.isoformat(),
               "utc_offset_minutes": int(local.utcoffset().total_seconds() / 60), "clock_fold": local.fold,
               "price_eur_mwh": targets.get(timestamp), "target_missing": int(targets.get(timestamp) is None),
               "quarter_of_day": quarter, "day_of_week": local.weekday(), "month": local.month,
               "public_holiday": int(day in holiday_dates), "price_timing_assumed": 1,
               "weather_timing_assumed": 1, "demand_timing_conditional": 1}
        for days in (1, 2, 7, 14):
            row[f"price_lag_{days}"] = history.lag(day, quarter, days)
        for days in (1, 7):
            for stat, value in zip(("mean", "min", "max"), history.summary(day, days)):
                row[f"price_day_{days}_{stat}"] = value
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
                   demand_selected_update_utc=updated, demand_screen=reason,
                   demand_archive_versions=len(demand.get(timestamp, [])),
                   demand_archived_latest_update_utc=max(archived_updates).isoformat() if archived_updates else None)
        rows.append(row)
    days = defaultdict(list)
    for row in rows:
        days[row["delivery_date"]].append(row)
    for daily in days.values():
        demand_absent = int(all(r["demand_missing"] for r in daily))
        weather_absent = int(all(r[f] is None for r in daily for f in weather))
        prices_absent = int(all(r[f"price_lag_{d}"] is None for r in daily for d in (1, 2, 7, 14)))
        for row in daily:
            row.update(demand_source_unavailable=demand_absent, weather_source_unavailable=weather_absent,
                       price_lags_unavailable=prices_absent)
    return rows


def summarize(rows, weather_fields):
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


def reconcile(counts, rows):
    demand = json.loads((ROOT / "forecasts/evidence/demand-recovery-evidence-20261008/summary.json").read_text())
    country = next(s for s in demand["summary"] if s["area"] == "Germany country")
    expected = {"rows": 35040, "days": 365, "target_missing": 0, "demand_usable": country["pre_cutoff"],
                "demand_unavailable_days": 71, "clock_change_days": {"2025-10-26": 100, "2026-03-29": 92}}
    for key, value in expected.items():
        if counts[key] != value:
            raise ValueError(f"Evidence contradiction for {key}: {counts[key]} != {value}")
    daily = defaultdict(lambda: [0, 0])
    for row in rows:
        daily[row["delivery_date"]][0] += 1
        daily[row["delivery_date"]][1] += row["demand_available"]
    with (ROOT / "forecasts/evidence/demand-recovery-evidence-20261008/daily-coverage.csv").open() as source:
        evidence = {r["local_date"]: [int(r["rows"]), int(r["pre_cutoff"])] for r in csv.DictReader(source) if r["AreaCode"] == COUNTRY}
    if dict(daily) != evidence:
        raise ValueError("Daily country demand coverage contradicts the saved audit")
    # Both missing fields span 95 aligned hours at each of the twelve locations.
    for field, missing in counts["weather_missing_quarters"].items():
        expected_missing = 0 if field.startswith("temperature") else 95 * 4
        if missing != expected_missing:
            raise ValueError(f"Weather evidence contradiction: {field}: {missing} != {expected_missing}")
    return expected


def main():
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
        weather = reader.weather_fields
    else:
        inputs = verify_payloads(args.data_root)
        print("Verified three input archives", flush=True)
        prices = load_prices(args.data_root / PAYLOADS["prices"])
        design = json.loads((ROOT / "forecasts/evidence/forecast-bounded-evidence-20261007/design.json").read_text())
        weather, metadata = load_weather(args.data_root / PAYLOADS["weather"], design["locations"])
        demand = load_demand(args.data_root / PAYLOADS["demand"], START, END)
        rows = build_rows(prices, weather, demand)
    counts = summarize(rows, weather)
    expected = reconcile(counts, rows)
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / "quarters.csv"
    with path.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    report = {"start": START.isoformat(), "end_exclusive": END.isoformat(), "timezone": "Europe/Berlin",
              "counts": counts, "reconciled_evidence": expected, "inputs": inputs, "weather": metadata,
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
