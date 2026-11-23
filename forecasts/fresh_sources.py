"""Fetch the three maintained forecast sources for a specified Berlin date range."""
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zipfile import ZIP_DEFLATED, ZipFile

from forecasts.fms import access_token
from forecasts.dataset import BERLIN, FIELDS, PAYLOADS, digest, quarters
from forecasts.input_config import WEATHER_LOCATIONS
from forecasts.input_types import DemandSeries, PriceSeries, Report, WeatherSeries

SMARD = "https://www.smard.de/app/chart_data/4169/DE/"
OPEN_METEO = "https://previous-runs-api.open-meteo.com/v1/forecast"
FMS = "https://fms.tp.entsoe.eu/downloadFileContent"
DEMAND_EXTRACT = "DayAheadTotalLoadForecast_6.1.B_r3"
RECEIPT = "retrieval.json"


def fetch_sources(root: Path, start: date, end: date, credentials: Path) -> None:
    """Fetch dated source archives, aborting when any required source fails."""
    if start >= end:
        raise ValueError("Source collection requires a nonempty Berlin date range")
    (root / "inputs").mkdir(parents=True)
    fetch_demand(root / PAYLOADS["demand"], start, end, credentials)
    _fetch_prices(root / PAYLOADS["prices"], start, end)
    _fetch_weather(root / PAYLOADS["weather"], start, end)


def fetch_demand(path: Path, start: date, end: date, credentials: Path) -> None:
    """Sign in and save the official monthly extracts and their actual receipt times."""
    token = access_token(credentials)
    start_utc = next(quarters(start, end))
    end_utc = next(quarters(end, end + timedelta(days=1))) - timedelta(minutes=15)
    month = start_utc.date().replace(day=1)
    with ZipFile(path, "x", compression=ZIP_DEFLATED) as archive:
        receipts = {}
        while month <= end_utc.date():
            name = f"{month:%Y_%m}_{DEMAND_EXTRACT}.csv"
            body = {"folder": f"/TP_export/{DEMAND_EXTRACT}/", "filename": name,
                    "topLevelFolder": "TP_export", "downloadAsZip": False}
            request = Request(FMS, data=json.dumps(body).encode(),
                              headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
            raw, receipt = _fetch(request)
            archive.writestr(name, raw)
            receipts[name] = {**receipt, "request": body}
            month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
        _write_receipt(archive, receipts)


def require_coverage(start: date, end: date, prices: PriceSeries,
                     weather: WeatherSeries, demand: DemandSeries) -> None:
    """Require measured archive coverage before creating a refreshed snapshot."""
    if start >= end:
        raise ValueError("Source collection requires a nonempty Berlin date range")
    expected = list(quarters(start, end))
    missing_demand = sum(not any(v["updated"] is not None and v["value"] is not None for v in demand.get(t, []))
                         for t in expected)
    missing_prices = sum(prices.get(t) is None for t in expected)
    hours = [t for t in expected if t.minute == 0]
    missing_weather = sum(weather.get(f"{field}_{loc.name.lower()}", {}).get(t) is None
                          for loc in WEATHER_LOCATIONS for field in FIELDS for t in hours)
    if missing_demand or missing_prices or missing_weather:
        raise ValueError(f"Incomplete source interval [{start}, {end}): {missing_demand} Germany demand quarters, "
                         f"{missing_prices} price quarters, {missing_weather} weather field-hours missing")


def source_receipts(root: Path) -> tuple[dict[str, Report], dict[str, Report]]:
    """Return the original bytes' identities and acquisition records."""
    archives, receipts = {}, {}
    for source, relative in PAYLOADS.items():
        path = root / relative
        with ZipFile(path) as archive:
            receipt = json.loads(archive.read(RECEIPT))
        archives[source] = {"path": relative, "bytes": path.stat().st_size, "sha256": digest(path)}
        receipts[source] = receipt
    return archives, receipts


def _fetch_prices(path: Path, start: date, end: date) -> None:
    raw, index_receipt = _fetch(Request(SMARD + "index_quarterhour.json"))
    available = set(json.loads(raw)["timestamps"])
    first = start - timedelta(days=start.weekday() + 14)
    with ZipFile(path, "x", compression=ZIP_DEFLATED) as archive:
        archive.writestr("prices/index.json", raw)
        receipts = {"prices/index.json": index_receipt}
        for diff in range(0, (end - first).days, 7):
            week = first + timedelta(days=diff)
            moment = datetime.combine(week, datetime.min.time(), BERLIN)
            timestamp = int(moment.timestamp() * 1000)
            if timestamp not in available:
                raise ValueError(f"SMARD quarter-hour index omits week starting {week}")
            name = f"4169_DE_quarterhour_{timestamp}.json"
            data, receipt = _fetch(Request(SMARD + name))
            archive.writestr("prices/" + name, data)
            receipts["prices/" + name] = receipt
        _write_receipt(archive, receipts)


def _fetch_weather(path: Path, start: date, end: date) -> None:
    params = {"latitude": ",".join(str(loc.latitude) for loc in WEATHER_LOCATIONS),
              "longitude": ",".join(str(loc.longitude) for loc in WEATHER_LOCATIONS),
              "models": "icon_eu", "hourly": ",".join(f"{name}_previous_day2" for name in FIELDS),
              "timezone": "UTC", "timeformat": "unixtime",
              "start_date": (start - timedelta(days=1)).isoformat(), "end_date": end.isoformat()}
    data, receipt = _fetch(Request(f"{OPEN_METEO}?{urlencode(params)}"))
    with ZipFile(path, "x", compression=ZIP_DEFLATED) as archive:
        archive.writestr("response.json", data)
        archive.writestr("history.json", json.dumps({**receipt, "data": json.loads(data)}))
        _write_receipt(archive, {"response.json": receipt})


def _fetch(request: Request) -> tuple[bytes, Report]:
    with urlopen(request, timeout=45) as response:
        raw = response.read()
        return raw, {"url": request.full_url, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                     "last_modified": response.headers.get("Last-Modified")}


def _write_receipt(archive: ZipFile, files: dict[str, Report]) -> None:
    archive.writestr(RECEIPT, json.dumps({"files": files, "retrieved_at_utc": max(
        record["retrieved_at_utc"] for record in files.values())}))
