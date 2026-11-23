"""Decode and verify the archived provider payloads used to collect a snapshot."""
from collections import defaultdict
from collections.abc import Sequence
import csv
from datetime import date, datetime
import io
import json
import math
from pathlib import Path
import zipfile

from forecasts.inputs.input_config import FIELDS
from forecasts.inputs.input_types import DemandSeries, PriceSeries, Report, WeatherSeries
from forecasts.market import BERLIN, UTC
from forecasts.provenance import digest

COUNTRY = "10Y1001A1001A83F"
START, END = date(2025, 10, 1), date(2026, 10, 1)
BASELINE_INPUTS = json.loads(Path(__file__).with_name("baseline-inputs.json").read_text())
PAYLOADS = {source: entry["path"] for source, entry in BASELINE_INPUTS.items()}
TIMING = {
    "prices": "Assume auction prices for earlier delivery dates are available at issue time; SMARD publication latency and revisions are unaudited.",
    "weather": "Assume documented previous_day2 fixed 48-hour lead; original publication times are unknown. Retrospective retrieval is not witnessed availability.",
    "demand": "Conditional on UpdateTime(UTC) describing availability; retain only archived versions updated by cutoff. Later revisions cannot recover overwritten earlier values.",
}


def stamp(value: str) -> datetime:
    """Parse a source timestamp as an aware UTC datetime."""
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def number(value: str | int | float | None) -> float | None:
    """Parse a finite source number; preserve missing values as None."""
    if value in (None, "", "n/e"):
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Non-finite source value")
    return result


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
