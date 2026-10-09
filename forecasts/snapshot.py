"""Collect, publish and load fixed typed input snapshots; publish the manifest last."""
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
import pyarrow.parquet as pq

from forecasts.dataset import (
    BERLIN, COUNTRY, END, FIELDS, PAYLOADS, ROOT, START, TIMING, build_rows, cutoff,
    digest, load_demand, load_prices, load_weather, reconcile, stamp, summarize,
    verify_payloads,
)
from forecasts.schemas import SCHEMAS, VERSION, describe, validate
from forecasts.storage import get_verified, put_verified, verify_bucket

LOCATIONS = {name.lower() for name, _, _ in json.loads((ROOT / "forecasts/evidence/forecast-bounded-evidence-20261007/design.json").read_text())["locations"]}
WEATHER_FIELDS = sorted(f"{variable}_{location}" for variable in FIELDS for location in LOCATIONS)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def identity(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def collect(data_root, output):
    inputs = verify_payloads(data_root)
    output.mkdir(parents=True, exist_ok=True)
    design = json.loads((ROOT / "forecasts/evidence/forecast-bounded-evidence-20261007/design.json").read_text())
    prices = load_prices(data_root / PAYLOADS["prices"])
    weather, weather_metadata = load_weather(data_root / PAYLOADS["weather"], design["locations"])
    demand = load_demand(data_root / PAYLOADS["demand"], START, END)
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
        path = output / f"{source}-retrieval.json"
        path.write_bytes(canonical(metadata))
        raw[source]["metadata_sha256"] = digest(path)
        common[source] = {"source_update_utc": None,
                          "retrieved_at_utc": stamp(metadata["retrieved_at_utc"]) if metadata["retrieved_at_utc"] else None,
                          "timing_evidence": "assumed", "raw_key": raw[source]["key"]}
    records = {"prices": [], "weather": [], "demand": []}
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
        times = table["valid_utc"].to_pylist()
        files[name] = {"file": path.name, "sha256": digest(path), "bytes": path.stat().st_size,
                       "rows": table.num_rows, "valid_min": min(times).isoformat(), "valid_max": max(times).isoformat(), "schema": describe(name)}
        print(f"Validated {name}: {table.num_rows} rows", flush=True)
    commit = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    dirty = bool(subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain", "--", "forecasts"], text=True).strip())
    manifest = {"schema_version": VERSION, "files": files, "raw": raw, "timing_limits": TIMING,
                "code_revision": commit, "exploratory_code": dirty,
                "environment": {"python": platform.python_version(), "pyarrow": pa.__version__, "requirements_sha256": digest(ROOT / "forecasts/requirements.txt")}}
    snapshot_id = identity(manifest)
    for name, entry in files.items():
        entry["key"] = f"snapshots/{snapshot_id}/{name}.parquet"
    manifest["snapshot_id"] = snapshot_id
    (output / "manifest.json").write_bytes(canonical(manifest))
    return manifest


def read_local(directory):
    manifest = json.loads((directory / "manifest.json").read_text())
    snapshot_id = manifest["snapshot_id"]
    if manifest["schema_version"] != VERSION or set(manifest["files"]) != set(SCHEMAS):
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


def eligible(row, deadline, live=False):
    if row["source_update_utc"] is not None and row["source_update_utc"] > deadline:
        return False
    if live and (row["retrieved_at_utc"] is None or row["retrieved_at_utc"] > deadline):
        return False
    return row["timing_evidence"] in {"witnessed", "documented", "assumed"}


def select_records(tables, day, live=False, issue_time=None):
    deadline = cutoff(day)
    if live:
        if issue_time is None or issue_time.tzinfo is None:
            raise ValueError("Live selection requires an actual timezone-aware issue timestamp")
        if issue_time > deadline:
            raise ValueError("Actual issue time is after the delivery day's deadline")
        deadline = issue_time
    records = {name: table.to_pylist() if hasattr(table, "to_pylist") else table for name, table in tables.items()}
    selected = {"prices": [], "weather": [], "demand": []}
    for row in records["prices"]:
        if row["valid_utc"].astimezone(BERLIN).date() < day and eligible(row, deadline, live):
            selected["prices"].append(row)
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
    selected["prices"] = latest_rows(selected["prices"], ["valid_utc"], "price_eur_mwh")
    selected["weather"] = latest_rows(selected["weather"], ["valid_utc", "location", "variable"], "value")
    return selected


def latest_rows(rows, keys, value):
    selected = {}
    earliest = datetime.min.replace(tzinfo=timezone.utc)
    for row in rows:
        key = tuple(row[k] for k in keys)
        prior = selected.get(key)
        update = row["source_update_utc"] or earliest
        if prior is not None:
            previous = prior["source_update_utc"] or earliest
            if update == previous and row[value] != prior[value]:
                raise ValueError("Conflicting source values at the same update time")
            if update < previous:
                continue
        selected[key] = row
    return list(selected.values())


def select_inputs(tables, day, live=False, issue_time=None):
    selected = select_records(tables, day, live, issue_time)
    prices, weather, demand = {}, {}, {}
    for row in selected["prices"]:
        t = row["valid_utc"]
        if t in prices and prices[t] != row["price_eur_mwh"]:
            raise ValueError("Ambiguous eligible price versions")
        prices[t] = row["price_eur_mwh"]
    for row in selected["weather"]:
        key = f"{row['variable']}_{row['location']}"
        values = weather.setdefault(key, {})
        if row["valid_utc"] in values and values[row["valid_utc"]] != row["value"]:
            raise ValueError("Ambiguous eligible weather versions")
        values[row["valid_utc"]] = row["value"]
    for row in selected["demand"]:
        demand.setdefault(row["valid_utc"], []).append({"updated": row["source_update_utc"], "value": row["demand_mw"], "source": row["raw_key"]})
    return prices, weather, demand


class InputReader:
    """One shared reader and feature path for replay and later prediction."""
    def __init__(self, tables):
        self.daily = {name: defaultdict(list) for name in SCHEMAS}
        self.truth = {}
        self.weather_fields = WEATHER_FIELDS
        for name, table in tables.items():
            for row in table.to_pylist():
                self.daily[name][row["valid_utc"].astimezone(BERLIN).date()].append(row)
        # Retrospective truth is joined only by replay(), never by features().
        for row in latest_rows(tables["prices"].to_pylist(), ["valid_utc"], "price_eur_mwh"):
            self.truth[row["valid_utc"]] = row["price_eur_mwh"]

    def features(self, day, live=False, issue_time=None):
        # Fourteen days cover every agreed price lag and daily summary.
        candidates = {"prices": [row for lag in range(1, 15) for row in self.daily["prices"][day - timedelta(days=lag)]],
                      "weather": self.daily["weather"][day], "demand": self.daily["demand"][day]}
        prices, weather, demand = select_inputs(candidates, day, live, issue_time)
        for field in self.weather_fields:
            weather.setdefault(field, {})
        return build_rows(prices, weather, demand, day, day + timedelta(days=1), targets={})

    def replay(self, start, end):
        rows, day = [], start
        while day < end:
            daily = self.features(day)
            for row in daily:
                row["price_eur_mwh"] = self.truth.get(stamp(row["delivery_utc"]))
                row["target_missing"] = int(row["price_eur_mwh"] is None)
            rows.extend(daily)
            day += timedelta(days=1)
        return rows

    def labels_at(self, fit_day):
        """Training truth is selected at the fold's first issue, separately from scoring truth."""
        candidates = [row for day, rows in self.daily["prices"].items() if day < fit_day
                      for row in rows if eligible(row, cutoff(fit_day))]
        return {row["valid_utc"]: row["price_eur_mwh"]
                for row in latest_rows(candidates, ["valid_utc"], "price_eur_mwh")}


def publish(profile, region, bucket, directory, data_root):
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


def load(profile, region, bucket, snapshot_id, directory):
    if len(snapshot_id) != 64 or any(c not in "0123456789abcdef" for c in snapshot_id):
        raise ValueError("Snapshot identifier must be a SHA-256 digest")
    started = time.monotonic()
    directory.mkdir(parents=True, exist_ok=True)
    # A missing manifest rejects partial publication before reading any input file.
    get_verified(profile, region, bucket, f"snapshots/{snapshot_id}/manifest.json", directory / "manifest.json")
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest.get("snapshot_id") != snapshot_id:
        raise ValueError("Wrong snapshot identifier")
    for name in SCHEMAS:
        entry = manifest["files"][name]
        if entry["file"] != f"{name}.parquet" or entry["key"] != f"snapshots/{snapshot_id}/{name}.parquet":
            raise ValueError("Invalid snapshot location")
        get_verified(profile, region, bucket, entry["key"], directory / entry["file"], entry["sha256"])
    manifest, tables = read_local(directory)
    measurements = {"snapshot_id": snapshot_id, "input_bytes": sum(e["bytes"] for e in manifest["files"].values()),
                    "cold_load_seconds": time.monotonic() - started, "rows": {n: t.num_rows for n, t in tables.items()}}
    (directory / "load-report.json").write_text(json.dumps(measurements, indent=2) + "\n")
    print(json.dumps(measurements), flush=True)
    return manifest, tables


def main():
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
    p = sub.add_parser("load")
    p.add_argument("snapshot_id")
    p.add_argument("--directory", type=Path, default=ROOT / "data/forecasts/loaded-snapshot")
    args = parser.parse_args()
    if (args.command != "collect" or args.publish) and (not args.profile or not args.bucket):
        parser.error("publish/load require an explicit user-local --profile and private --bucket")
    if args.command == "collect":
        manifest = collect(args.data_root, args.directory)
        print(manifest["snapshot_id"], flush=True)
        if args.publish:
            publish(args.profile, args.region, args.bucket, args.directory, args.data_root)
    elif args.command == "publish":
        publish(args.profile, args.region, args.bucket, args.directory, args.data_root)
    else:
        load(args.profile, args.region, args.bucket, args.snapshot_id, args.directory)


if __name__ == "__main__":
    main()
