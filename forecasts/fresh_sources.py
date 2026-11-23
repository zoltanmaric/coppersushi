"""Fetch price history and optional research archives for a specified Berlin date range."""
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from urllib.request import Request, urlopen
from zipfile import ZIP_DEFLATED, ZipFile

from forecasts.fms import access_token
from forecasts.dataset import BERLIN, PAYLOADS, digest, quarters
from forecasts.input_types import PriceSeries, Report

SMARD = "https://www.smard.de/app/chart_data/4169/DE/"
FMS = "https://fms.tp.entsoe.eu/downloadFileContent"
DEMAND_EXTRACT = "DayAheadTotalLoadForecast_6.1.B_r3"
RECEIPT = "retrieval.json"


def fetch_sources(root: Path, start: date, end: date) -> None:
    """Fetch dated source archives, aborting when any required source fails."""
    if start >= end:
        raise ValueError("Source collection requires a nonempty Berlin date range")
    (root / "inputs").mkdir(parents=True)
    _fetch_prices(root / PAYLOADS["prices"], start, end)


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


def require_coverage(start: date, end: date, prices: PriceSeries) -> None:
    """Require one price per Berlin delivery quarter, including clock changes."""
    if start >= end:
        raise ValueError("Source collection requires a nonempty Berlin date range")
    missing = [t for t in quarters(start, end) if prices.get(t) is None]
    if missing:
        raise ValueError(f"Missing {len(missing)} price quarters, first at {missing[0]}")


def source_receipts(root: Path) -> tuple[dict[str, Report], dict[str, Report]]:
    """Return the original bytes' identities and acquisition records."""
    archives, receipts = {}, {}
    for source in ("prices",):
        relative = PAYLOADS[source]
        path = root / relative
        with ZipFile(path) as archive:
            receipt = json.loads(archive.read(RECEIPT))
        archives[source] = {"path": relative, "bytes": path.stat().st_size, "sha256": digest(path)}
        receipts[source] = receipt
    return archives, receipts


def _fetch_prices(path: Path, start: date, end: date) -> None:
    raw, index_receipt = _fetch(Request(SMARD + "index_quarterhour.json"))
    available = set(json.loads(raw)["timestamps"])
    first = start - timedelta(days=start.weekday())
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


def _fetch(request: Request) -> tuple[bytes, Report]:
    with urlopen(request, timeout=45) as response:
        raw = response.read()
        return raw, {"url": request.full_url, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                     "last_modified": response.headers.get("Last-Modified")}


def _write_receipt(archive: ZipFile, files: dict[str, Report]) -> None:
    archive.writestr(RECEIPT, json.dumps({"files": files, "retrieved_at_utc": max(
        record["retrieved_at_utc"] for record in files.values())}))
