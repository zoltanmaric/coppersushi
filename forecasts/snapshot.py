"""Collect, publish and load fixed typed input snapshots; publish the manifest last."""
from collections.abc import Mapping, Sequence
from functools import cached_property
from typing import cast

import polars as pl
from pandera.typing.polars import DataFrame
from datetime import date
from forecasts.input_types import DemandSeries, PriceSeries, Report, Row, WeatherSeries
import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import time

import pyarrow as pa
from forecasts.coverage import require_quarters, require_static_features
from forecasts.input_config import FIELDS, WEATHER_FIELDS, WEATHER_LOCATIONS, WEATHER_TABLE_FIELDS
from forecasts.prices import LAGS, PriceFeatures, PriceHistory, PriceVersions, build_price_features, latest_versions, read_prices, select_history
import pyarrow.parquet as pq

from forecasts.dataset import (
    BERLIN, COUNTRY, END, PAYLOADS, ROOT, START, TIMING, assemble_features, assemble_price_calendar, cutoff, diagnostic_rows, quarters,
    digest, load_demand, load_prices, load_weather, stamp,
    verify_payloads,
)
from forecasts.fresh_sources import fetch_sources, require_coverage, source_receipts
from forecasts.schemas import SCHEMAS, VERSION, describe, validate
from forecasts.storage import get_verified, put_verified, verify_bucket
from forecasts.tables import DiagnosticFeatures, Features

LOCATIONS = {location.name.lower() for location in WEATHER_LOCATIONS}


def canonical(value: object) -> bytes:
    """Encode JSON deterministically for hashing and saved manifests."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def identity(value: object) -> str:
    """Hash the canonical JSON representation."""
    return hashlib.sha256(canonical(value)).hexdigest()


def collect(data_root: Path, output: Path, *,
            period: tuple[date, date] | None = None) -> Report:
    """Validate archived sources and save typed snapshot tables and a manifest."""
    start, end = period if period is not None else (START, END)
    inputs, receipts = source_receipts(data_root) if period is not None else (verify_payloads(data_root), {})
    prices = load_prices(data_root / PAYLOADS["prices"])
    weather: WeatherSeries = {}
    demand: DemandSeries = {}
    weather_metadata: Report = {}
    if period is None:
        weather, weather_metadata = load_weather(data_root / PAYLOADS["weather"], WEATHER_LOCATIONS)
        demand = load_demand(data_root / PAYLOADS["demand"], start, end)
    else:
        require_coverage(start, end, prices)
    output.mkdir(parents=True, exist_ok=period is None)
    raw, common = {}, {}
    for source, entry in inputs.items():
        prefix = f"raw/{source}/{entry['sha256']}"
        raw[source] = {**entry, "key": f"{prefix}/{Path(entry['path']).name}", "metadata_key": f"{prefix}/retrieval.json"}
        metadata = {"source": source, "source_archive_sha256": entry["sha256"],
                    "retrieved_at_utc": weather_metadata["retrieved_at_utc"] if source == "weather" else None,
                    "timing_evidence": "assumed", "assumption": TIMING[source]}
        if source == "weather":
            metadata.update(weather_metadata)
        elif source == "prices":
            metadata["request_url_pattern"] = "https://www.smard.de/app/chart_data/4169/DE/4169_DE_quarterhour_<week>.json"
        else:
            metadata["source_extract"] = "ENTSO-E File Library DayAheadTotalLoadForecast_6.1.B_r3; Germany country"
        if source in receipts:
            metadata.update(receipts[source])
        path = output / f"{source}-retrieval.json"
        path.write_bytes(canonical(metadata))
        raw[source]["metadata_sha256"] = digest(path)
        common[source] = {"source_update_utc": None,
                          "retrieved_at_utc": stamp(metadata["retrieved_at_utc"]) if metadata["retrieved_at_utc"] else None,
                          "timing_evidence": "assumed", "raw_key": raw[source]["key"]}
    records: dict[str, list[Row]] = {name: [] for name in inputs}
    for valid, value in sorted(prices.items()):
        records["prices"].append({**common["prices"], "valid_utc": valid, "price_eur_mwh": value,
                                  "version_id": identity([inputs["prices"]["sha256"], valid.isoformat()])})
    for field, values in weather.items():
        variable, location = next((v, field.removeprefix(v + "_")) for v in FIELDS if field.startswith(v + "_"))
        for valid, value in sorted(values.items()):
            records["weather"].append({**common["weather"], "valid_utc": valid,
                "source_valid_utc": valid + timedelta(hours=variable == "shortwave_radiation"),
                "location": location, "variable": variable, "value": value, "unit": FIELDS[variable],
                "model": "icon_eu", "lead_hours": 48, "data_kind": "forecast",
                "version_id": identity([inputs["weather"]["sha256"], field, valid.isoformat()])})
    for valid, versions in sorted(demand.items()):
        for i, version in enumerate(versions):
            records["demand"].append({**common["demand"], "valid_utc": valid, "source_update_utc": version["updated"],
                "area_code": COUNTRY, "demand_mw": version["value"],
                "version_id": identity([inputs["demand"]["sha256"], valid.isoformat(), version["source"], i])})
    files = {}
    for name, rows in records.items():
        table = validate(name, pa.Table.from_pylist(rows, schema=SCHEMAS[name]))
        path = output / f"{name}.parquet"
        pq.write_table(table, path, compression="zstd", version="2.6")
        validate(name, pq.read_table(path))
        # validate() above enforces non-null UTC timestamps.
        times = cast(list[datetime], table["valid_utc"].to_pylist())
        files[name] = {"file": path.name, "sha256": digest(path), "bytes": path.stat().st_size,
                       "rows": table.num_rows, "valid_min": min(times).isoformat(), "valid_max": max(times).isoformat(), "schema": describe(name)}
        print(f"Validated {name}: {table.num_rows} rows", flush=True)
    commit = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    dirty = bool(subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain", "--", "forecasts", "pyproject.toml", "pixi.lock"], text=True).strip())
    manifest = {"schema_version": VERSION, "files": files, "raw": raw, "timing_limits": {name: TIMING[name] for name in inputs},
                "code_revision": commit, "exploratory_code": dirty,
                "environment": {"python": platform.python_version(), "pyarrow": pa.__version__, "project_sha256": digest(ROOT / "pyproject.toml"), "pixi_lock_sha256": digest(ROOT / "pixi.lock")}}
    if period is not None:
        manifest["required_period_berlin"] = {"start": start.isoformat(), "end_exclusive": end.isoformat()}
    snapshot_id = identity(manifest)
    for name, entry in files.items():
        entry["key"] = f"snapshots/{snapshot_id}/{name}.parquet"
    manifest["snapshot_id"] = snapshot_id
    (output / "manifest.json").write_bytes(canonical(manifest))
    return manifest


def read_local(directory: Path) -> tuple[Report, dict[str, pa.Table]]:
    """Verify snapshot identity, hashes and schemas before returning Arrow tables."""
    manifest = json.loads((directory / "manifest.json").read_text())
    snapshot_id = manifest["snapshot_id"]
    if manifest["schema_version"] != VERSION or set(manifest["files"]) not in ({"prices"}, set(SCHEMAS)) or set(manifest["files"]) != set(manifest["raw"]):
        raise ValueError("Unsupported or incomplete snapshot manifest")
    payload = {k: v for k, v in manifest.items() if k != "snapshot_id"}
    payload = json.loads(json.dumps(payload))
    for entry in payload["files"].values():
        entry.pop("key")
    if identity(payload) != snapshot_id:
        raise ValueError("Manifest content does not match snapshot identifier")
    tables = {}
    for name, entry in manifest["files"].items():
        if entry["file"] != f"{name}.parquet" or entry["key"] != f"snapshots/{snapshot_id}/{name}.parquet" or entry["schema"] != describe(name):
            raise ValueError("Snapshot file location/schema is not canonical")
        path = directory / entry["file"]
        if digest(path) != entry["sha256"] or path.stat().st_size != entry["bytes"]:
            raise ValueError(f"Snapshot file checksum mismatch: {name}")
        tables[name] = validate(name, pq.read_table(path))
        if tables[name].num_rows != entry["rows"]:
            raise ValueError(f"Snapshot row count mismatch: {name}")
    return manifest, tables


def eligible(row: Row, deadline: datetime, live: bool = False) -> bool:
    """Check update/retrieval cutoffs and the permitted timing-evidence categories."""
    if row["source_update_utc"] is not None and row["source_update_utc"] > deadline:
        return False
    if live and (row["retrieved_at_utc"] is None or row["retrieved_at_utc"] > deadline):
        return False
    return row["timing_evidence"] in {"witnessed", "documented", "assumed"}


def select_records(tables: Mapping[str, pa.Table | list[Row]], day: date, live: bool = False, issue_time: datetime | None = None) -> dict[str, list[Row]]:
    """Select source versions eligible for a delivery day and its issue time."""
    deadline = _issue_deadline(day, live, issue_time)
    records = {name: table.to_pylist() if hasattr(table, "to_pylist") else table for name, table in tables.items() if name != "prices"}
    selected = _select_covariates(records, day, deadline, live)
    price_input = tables["prices"]
    price_table = price_input if isinstance(price_input, pa.Table) else pa.Table.from_pylist(price_input, schema=SCHEMAS["prices"])
    selected["prices"] = select_history(read_prices(price_table), day, deadline, live).to_dicts()
    return selected


class InputReader:
    """One shared reader and feature path for replay and later prediction."""
    def __init__(self, tables: Mapping[str, pa.Table]) -> None:
        self._tables = tables
        self.weather_fields = WEATHER_FIELDS
        self.prices = read_prices(tables["prices"])

    @cached_property
    def truth(self) -> PriceSeries:
        """Resolve retrospective realised prices for scoring and diagnostics."""
        return dict(latest_versions(self.prices).select("valid_utc", "price_eur_mwh").iter_rows())

    def features(self, day: date, live: bool = False, issue_time: datetime | None = None, *,
                 require_complete: bool = False) -> DataFrame[Features]:
        """Build one delivery day’s features from inputs eligible at its issue.

        Live selection requires a timezone-aware issue_time no later than the
        deadline. Return a native quarter-hour table without realised outcomes.
        """
        deadline = _issue_deadline(day, live, issue_time)
        history = self._day_prices(day, deadline, live, require_complete)
        rows = Features.validate(assemble_price_calendar(history))
        if require_complete:
            require_static_features(rows, day, day + timedelta(days=1))
        return rows

    def historical_features(self, start: date, end: date, *,
                            complete_from: date | None = None) -> DataFrame[Features]:
        """Build and validate [start, end) using each day's issue cutoff."""
        if start >= end:
            raise ValueError("Feature start must precede end")
        days = (start + timedelta(days=offset) for offset in range((end - start).days))
        rows = Features.validate(pl.concat([
            assemble_price_calendar(self._day_prices(day, cutoff(day), False, complete_from is not None and day >= complete_from))
            for day in days
        ]))
        if complete_from is not None:
            checked = cast(DataFrame[Features], rows.filter(pl.col("delivery_date") >= complete_from))
            require_static_features(checked, max(start, complete_from), end)
        return rows

    def replay(self, start: date, end: date) -> list[Row]:
        """Build the separate archived-source diagnostic and attach realised prices."""
        if start >= end:
            raise ValueError("Feature start must precede end")
        daily: dict[str, defaultdict[date, list[Row]]] = {name: defaultdict(list) for name in ("weather", "demand")}
        missing = sorted(daily.keys() - self._tables.keys())
        if missing:
            raise ValueError(f"Archived-source diagnostic requires a full historical snapshot; missing {', '.join(missing)} tables")
        for name, by_day in daily.items():
            for row in self._tables[name].to_pylist():
                by_day[row["valid_utc"].astimezone(BERLIN).date()].append(row)
        days = (start + timedelta(days=offset) for offset in range((end - start).days))
        frames = []
        for day in days:
            deadline = cutoff(day)
            selected = _select_covariates({name: by_day[day] for name, by_day in daily.items()}, day, deadline, False)
            weather, demand = _covariate_inputs(selected)
            frames.append(assemble_features(self._day_prices(day, deadline, False, False), weather, demand))
        return diagnostic_rows(DiagnosticFeatures.validate(pl.concat(frames)), self.truth, WEATHER_TABLE_FIELDS)

    def _day_prices(self, day: date, deadline: datetime, live: bool, require_complete: bool) -> DataFrame[PriceFeatures]:
        # Fourteen local days cover every agreed lag and daily summary.
        candidates = cast(DataFrame[PriceVersions], self.prices.filter(
            pl.col("valid_utc").dt.convert_time_zone("Europe/Berlin").dt.date() >= day - timedelta(days=14)))
        selected = select_history(candidates, day, deadline, live)
        history = PriceHistory.validate(selected.select("valid_utc", "price_eur_mwh"))
        if require_complete:
            observed = {timestamp for timestamp, value in history.iter_rows() if value is not None}
            for lag in LAGS:
                lag_day = day - timedelta(days=lag)
                stop = lag_day + timedelta(days=1)
                require_quarters((timestamp for timestamp in quarters(lag_day, stop) if timestamp in observed),
                                 lag_day, stop,
                                 f"Eligible SMARD prices at {deadline.isoformat()} for delivery {day} (D-{lag})")
        return build_price_features(history, list(quarters(day, day + timedelta(days=1))))


def publish(profile: str, region: str, bucket: str, directory: Path, data_root: Path) -> None:
    """Verify and upload snapshot objects, publishing the manifest last."""
    manifest, _ = read_local(directory)
    verify_bucket(profile, region, bucket)
    # Validate all provenance records before starting publication.
    for source, entry in manifest["raw"].items():
        if digest(data_root / PAYLOADS[source]) != entry["sha256"]:
            raise ValueError("Raw inputs changed after collection")
        if digest(directory / f"{source}-retrieval.json") != entry["metadata_sha256"]:
            raise ValueError("Retrieval metadata changed after collection")
    for source, entry in manifest["raw"].items():
        path = data_root / PAYLOADS[source]
        put_verified(profile, region, bucket, entry["key"], path)
        put_verified(profile, region, bucket, entry["metadata_key"], directory / f"{source}-retrieval.json")
    for entry in manifest["files"].values():
        put_verified(profile, region, bucket, entry["key"], directory / entry["file"])
    put_verified(profile, region, bucket, f"snapshots/{manifest['snapshot_id']}/manifest.json", directory / "manifest.json")
    print(f"Published fixed snapshot {manifest['snapshot_id']}", flush=True)


def load(profile: str, region: str, bucket: str, snapshot_id: str, directory: Path) -> tuple[Report, dict[str, pa.Table]]:
    """Download a fixed S3 snapshot and verify it before returning its tables."""
    if len(snapshot_id) != 64 or any(c not in "0123456789abcdef" for c in snapshot_id):
        raise ValueError("Snapshot identifier must be a SHA-256 digest")
    started = time.monotonic()
    directory.mkdir(parents=True, exist_ok=True)
    # A missing manifest rejects partial publication before reading any input file.
    get_verified(profile, region, bucket, f"snapshots/{snapshot_id}/manifest.json", directory / "manifest.json")
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest.get("snapshot_id") != snapshot_id:
        raise ValueError("Wrong snapshot identifier")
    if set(manifest["files"]) not in ({"prices"}, set(SCHEMAS)):
        raise ValueError("Unsupported or incomplete snapshot manifest")
    for name, entry in manifest["files"].items():
        if entry["file"] != f"{name}.parquet" or entry["key"] != f"snapshots/{snapshot_id}/{name}.parquet":
            raise ValueError("Invalid snapshot location")
        get_verified(profile, region, bucket, entry["key"], directory / entry["file"], entry["sha256"])
    manifest, tables = read_local(directory)
    measurements = {"snapshot_id": snapshot_id, "input_bytes": sum(e["bytes"] for e in manifest["files"].values()),
                    "cold_load_seconds": time.monotonic() - started, "rows": {n: t.num_rows for n, t in tables.items()}}
    (directory / "load-report.json").write_text(json.dumps(measurements, indent=2) + "\n")
    print(json.dumps(measurements), flush=True)
    return manifest, tables


def main() -> None:
    """Dispatch collection, publication or loading of a fixed input snapshot."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", help="User-local AWS profile required for publish/load")
    parser.add_argument("--region", default="eu-west-1")
    parser.add_argument("--bucket", help="Private bucket name; keep account-specific settings outside Git")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("collect", "publish"):
        p = sub.add_parser(command)
        p.add_argument("--data-root", type=Path, default=ROOT / "data/forecasts")
        p.add_argument("--directory", type=Path, default=ROOT / "data/forecasts/snapshot")
        if command == "collect":
            p.add_argument("--publish", action="store_true", help="Publish the validated collection to S3 in this run")
    p = sub.add_parser("refresh", help="Download SMARD prices and stage a price snapshot")
    p.add_argument("--start", type=date.fromisoformat, required=True)
    p.add_argument("--end-exclusive", type=date.fromisoformat, required=True)
    p.add_argument("--data-root", type=Path, required=True, help="New directory for the raw responses")
    p.add_argument("--directory", type=Path, required=True, help="New directory for the typed snapshot")
    p = sub.add_parser("load")
    p.add_argument("snapshot_id")
    p.add_argument("--directory", type=Path, default=ROOT / "data/forecasts/loaded-snapshot")
    args = parser.parse_args()
    if (args.command in {"load", "publish"} or getattr(args, "publish", False)) and (not args.profile or not args.bucket):
        parser.error("publish/load require an explicit user-local --profile and private --bucket")
    if args.command == "collect":
        manifest = collect(args.data_root, args.directory)
        print(manifest["snapshot_id"], flush=True)
        if args.publish:
            publish(args.profile, args.region, args.bucket, args.directory, args.data_root)
    elif args.command == "publish":
        publish(args.profile, args.region, args.bucket, args.directory, args.data_root)
    elif args.command == "refresh":
        if args.data_root.exists() or args.directory.exists() or args.data_root.resolve() == args.directory.resolve():
            parser.error("refresh requires new, distinct paths for the raw archives and typed snapshot")
        fetch_sources(args.data_root, args.start, args.end_exclusive)
        manifest = collect(args.data_root, args.directory, period=(args.start, args.end_exclusive))
        print(manifest["snapshot_id"], flush=True)
    else:
        load(args.profile, args.region, args.bucket, args.snapshot_id, args.directory)


def _issue_deadline(day: date, live: bool, issue_time: datetime | None) -> datetime:
    deadline = cutoff(day)
    if live:
        if issue_time is None or issue_time.utcoffset() is None:
            raise ValueError("Live selection requires an actual timezone-aware issue timestamp")
        if issue_time > deadline:
            raise ValueError("Actual issue time is after the delivery day's deadline")
        deadline = issue_time
    return deadline


def _select_covariates(records: Mapping[str, list[Row]], day: date, deadline: datetime,
                       live: bool) -> dict[str, list[Row]]:
    selected: dict[str, list[Row]] = {"weather": [], "demand": []}
    for row in records["weather"]:
        if (row["model"] != "icon_eu" or row["lead_hours"] != 48 or row["data_kind"] != "forecast"
                or row["location"] not in LOCATIONS or row["variable"] not in FIELDS
                or row["valid_utc"].astimezone(BERLIN).date() != day
                or row["source_valid_utc"] - timedelta(hours=48) > deadline
                or not eligible(row, deadline, live)):
            continue
        selected["weather"].append(row)
    for row in records["demand"]:
        if (row["area_code"] == COUNTRY and row["valid_utc"].astimezone(BERLIN).date() == day
                and row["source_update_utc"] is not None and eligible(row, deadline, live)):
            selected["demand"].append(row)
    selected["weather"] = _latest_rows(selected["weather"], ["valid_utc", "location", "variable"], "value")
    return selected


def _latest_rows(rows: list[Row], keys: Sequence[str], value: str) -> list[Row]:
    """Keep latest weather versions, with the same tie rules as prices.

    Missing updates rank oldest. Reject conflicting values at any equal update,
    even if a newer revision supersedes them. Equal-value ties retain the last
    input record. Unlike demand selection, a missing value can be the latest.
    """
    selected: dict[tuple[object, ...], Row] = {}
    seen: dict[tuple[object, ...], object] = {}
    earliest = datetime.min.replace(tzinfo=timezone.utc)
    for row in rows:
        key = tuple(row[k] for k in keys)
        revision = (*key, row["source_update_utc"])
        if revision in seen and seen[revision] != row[value]:
            raise ValueError("Conflicting source values at the same update time")
        seen[revision] = row[value]
        prior = selected.get(key)
        update = (row["source_update_utc"] is not None, row["source_update_utc"] or earliest)
        if prior is not None:
            previous = (prior["source_update_utc"] is not None, prior["source_update_utc"] or earliest)
            if update < previous:
                continue
        selected[key] = row
    return list(selected.values())


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
