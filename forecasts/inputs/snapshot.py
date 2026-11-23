"""Collect, publish and load fixed typed input snapshots."""
import argparse
from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import time
from typing import cast

import pyarrow as pa
import pyarrow.parquet as pq

from forecasts.inputs.fresh_sources import fetch_sources, require_coverage, source_receipts
from forecasts.inputs.input_config import FIELDS, WEATHER_LOCATIONS
from forecasts.inputs.input_types import DemandSeries, Report, Row, WeatherSeries
from forecasts.inputs.schemas import SCHEMAS, VERSION, describe, validate
from forecasts.inputs.sources import (
    COUNTRY, END, PAYLOADS, START, TIMING, load_demand, load_prices, load_weather, stamp, verify_payloads,
)
from forecasts.provenance import ROOT, digest
from forecasts.inputs.storage import get_verified, put_verified, verify_bucket


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


if __name__ == "__main__":
    main()
