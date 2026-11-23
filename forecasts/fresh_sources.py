"""Fetch SMARD price history for a specified Berlin date range."""
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from urllib.request import Request, urlopen
from zipfile import ZIP_DEFLATED, ZipFile

from forecasts.dataset import BERLIN, PAYLOADS, digest, quarters
from forecasts.input_types import PriceSeries, Report

SMARD = "https://www.smard.de/app/chart_data/4169/DE/"
RECEIPT = "retrieval.json"


def fetch_sources(root: Path, start: date, end: date) -> None:
    """Fetch the dated SMARD archive, aborting if a required request fails."""
    if start >= end:
        raise ValueError("Source collection requires a nonempty Berlin date range")
    (root / "inputs").mkdir(parents=True)
    _fetch_prices(root / PAYLOADS["prices"], start, end)


def require_coverage(start: date, end: date, prices: PriceSeries) -> None:
    """Require one price per Berlin delivery quarter, including clock changes."""
    if start >= end:
        raise ValueError("Source collection requires a nonempty Berlin date range")
    missing = [t for t in quarters(start, end) if prices.get(t) is None]
    if missing:
        raise ValueError(f"Missing {len(missing)} price quarters, first at {missing[0]}")


def source_receipts(root: Path) -> tuple[dict[str, Report], dict[str, Report]]:
    """Return the original price archive's identity and acquisition record."""
    relative = PAYLOADS["prices"]
    path = root / relative
    with ZipFile(path) as archive:
        receipt = json.loads(archive.read(RECEIPT))
    return {"prices": {"path": relative, "bytes": path.stat().st_size, "sha256": digest(path)}}, {"prices": receipt}


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
