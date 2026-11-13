"""Reproduce Polish export-cap, neighbouring-price and reserve comparisons.

Run: python -m scripts.polish_export_caps --start 2026-05-06 --end 2026-11-13
Outputs and licensed price responses stay in ignored data/, never in the wiki.
"""
import argparse
import json
import hashlib
import logging
import urllib.parse
import urllib.request
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, FiniteFloat, AwareDatetime

from coppersushi.pipelines.cnec import attribution as cnec_attribution
from coppersushi.pipelines.data_model.cnec_attribution import AllocationConstraint, NetPosition, PolishAlternative, JaoRecord
from coppersushi.pipelines.cnec.data_sources import electricity_maps, jao
from coppersushi.pipelines.market_day import MarketDay

NEIGHBOURS = ("DE", "CZ", "SK")
ZONES = ("PL", *NEIGHBOURS)


class Purchase(BaseModel):
    """Hourly upward balancing capacity purchased in PSE's primary auction (MW)."""
    model_config = ConfigDict(extra="ignore")
    dtime_utc: str
    publication_ts_utc: str
    fcr_g: FiniteFloat | None
    afrr_g: FiniteFloat | None
    mfrrd_g: FiniteFloat | None
    rr_g: FiniteFloat | None


class Requirement(BaseModel):
    """Hourly upward requirement; FRR is additional to the aFRR requirement."""
    model_config = ConfigDict(extra="ignore")
    dtime_utc: str
    publication_ts_utc: str
    fcrg: FiniteFloat | None
    afrrg: FiniteFloat | None
    frrg: FiniteFloat | None
    rrg: FiniteFloat | None


def procurement_frame(purchases: list[dict], requirements: list[dict]) -> pd.DataFrame:
    frames = []
    for rows, model, fields, prefix in (
        (purchases, Purchase, ["fcr_g", "afrr_g", "mfrrd_g", "rr_g"], "procured"),
        (requirements, Requirement, ["fcrg", "afrrg", "frrg", "rrg"], "required"),
    ):
        frame = pd.DataFrame([model.model_validate(row).model_dump() for row in rows])
        if frame.empty:
            frames.append(pd.DataFrame({"interval": pd.Series(dtype="datetime64[ns, UTC]"),
                                        prefix + "_mw": pd.Series(dtype=float),
                                        prefix + "_published": pd.Series(dtype="datetime64[ns, UTC]")}))
            continue
        frame["interval"] = pd.to_datetime(frame.dtime_utc, utc=True) - pd.Timedelta(hours=1)
        if frame.interval.duplicated().any():
            raise ValueError("Ambiguous hourly procurement versions")
        publication = pd.to_datetime(frame.publication_ts_utc, utc=True)
        # SDAC gate closure is noon CET/CEST on the preceding delivery day.
        local_day = frame.interval.dt.tz_convert("Europe/Warsaw").dt.tz_localize(None).dt.normalize()
        deadline = (local_day - pd.Timedelta(days=1) + pd.Timedelta(hours=12)).dt.tz_localize("Europe/Warsaw").dt.tz_convert("UTC")
        frame[prefix + "_published"] = publication
        frame[prefix + "_mw"] = frame[fields].sum(axis=1, min_count=4).where(publication < deadline)
        selected = frame[["interval", prefix + "_mw", prefix + "_published"]]
        if prefix == "procured":
            for field in fields:
                selected = selected.assign(**{field: frame[field].where(publication < deadline)})
        frames.append(selected)
    result = frames[0].merge(frames[1], on="interval", how="outer", validate="one_to_one")
    return pd.concat([result.assign(interval=result.interval + pd.Timedelta(minutes=m))
                      for m in (0, 15, 30, 45)], ignore_index=True)


class Retrieval(BaseModel):
    """Observed fetch window and requests for one cached input's exact bytes."""
    urls: list[str]
    started_at: AwareDatetime
    completed_at: AwareDatetime
    sha256: str


def record_retrieval(path: Path, urls: list[str], started_at: datetime) -> None:
    record = Retrieval(urls=urls, started_at=started_at, completed_at=datetime.now(UTC),
                       sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    path.with_suffix(path.suffix + ".retrieval.json").write_text(record.model_dump_json(indent=2))


class InputRetrieval(BaseModel):
    """Whether retrieval evidence is available for an input used by the collection."""
    input: str
    status: Literal["dated", "undated", "source_cache_missing", "provenance_mismatch"]
    retrieval: Retrieval | None = None


class RetrievalCoverage(BaseModel):
    """Observed fetch span; incomplete when any contributing cache is undated."""
    inputs: list[InputRetrieval]
    dated_inputs: int
    undated_inputs: int
    earliest_retrieval_utc: AwareDatetime | None
    latest_retrieval_utc: AwareDatetime | None
    span_complete: bool


def retrieval_coverage(cache: Path, days: list[str]) -> RetrievalCoverage:
    records = []
    for day in days:
        for suffix in ("allocationConstraint.json", "netPos.json", "DA_PL_AC.json",
                       "prices.csv", "mbp-tp.json", "wmb.json"):
            path = cache / f"{day}-{suffix}"
            sidecar = path.with_suffix(path.suffix + ".retrieval.json")
            entry = InputRetrieval(input=path.name, status="undated")
            if not path.exists():
                entry.status = "source_cache_missing"
            elif sidecar.exists():
                record = Retrieval.model_validate_json(sidecar.read_text())
                if record.sha256 == hashlib.sha256(path.read_bytes()).hexdigest():
                    entry.status, entry.retrieval = "dated", record
                else:
                    entry.status = "provenance_mismatch"
            records.append(entry)
    dated = [r.retrieval for r in records if r.retrieval is not None]
    return RetrievalCoverage(inputs=records, dated_inputs=len(dated), undated_inputs=len(records) - len(dated),
                earliest_retrieval_utc=min((r.started_at for r in dated), default=None),
                latest_retrieval_utc=max((r.completed_at for r in dated), default=None),
                span_complete=len(dated) == len(records))


def pse(endpoint: str, day: str, cache: Path) -> list[dict]:
    path = cache / f"{day}-{endpoint}.json"
    if path.exists():
        return json.loads(path.read_text())["value"]
    query = urllib.parse.urlencode({"$filter": f"business_date eq '{day}'", "$first": 1000})
    url = f"https://api.raporty.pse.pl/api/{endpoint}?{query}"
    rows = []
    urls = []
    started_at = datetime.now(UTC)
    while url:
        urls.append(url)
        with urllib.request.urlopen(url, timeout=30) as response:
            payload = json.load(response)
        rows.extend(payload["value"])
        url = payload.get("nextLink")
        if url and not url.startswith("https://api.raporty.pse.pl/api/"):
            raise ValueError("Unexpected PSE pagination host")
    path.write_text(json.dumps({"value": rows}))
    record_retrieval(path, urls, started_at)
    return rows


def collect(day: MarketDay, cache: Path) -> pd.DataFrame:
    key = day.date.isoformat()
    path = cache / f"{key}-joined.csv"
    if path.exists():
        frame = pd.read_csv(path)
        frame["interval"] = pd.to_datetime(frame.interval, utc=True)
        return frame[["interval", "import_limit", "export_limit", "polish_position", "polish_alt", *ZONES]]
    def feed[T: JaoRecord](endpoint: str, model: type[T], cross: bool = False) -> list[T]:
        target = cache / f"{key}-{endpoint}.json"
        if not target.exists():
            kwargs = {"base_url": "https://publicationtool.jao.eu/crossCCR/api/data"} if cross else {}
            started_at = datetime.now(UTC)
            rows = jao._get(endpoint, day.start_time_utc, day.end_time_utc, timeout=30, **kwargs)
            target.write_text(json.dumps(rows))
            base_url = kwargs.get("base_url", jao.BASE_URL)
            query = urllib.parse.urlencode(dict(FromUtc=jao._stamp(day.start_time_utc),
                                                ToUtc=jao._stamp(day.end_time_utc), Take=100_000_000))
            record_retrieval(target, [f"{base_url}/{endpoint}?{query}"], started_at)
        return [model.model_validate(row) for row in json.loads(target.read_text())]
    context = cnec_attribution.context(day, [], feed("allocationConstraint", AllocationConstraint),
                                      feed("netPos", NetPosition), feed("DA_PL_AC", PolishAlternative, True))
    price_path = cache / f"{key}-prices.csv"
    if price_path.exists():
        prices = electricity_maps.read_day(price_path)
    else:
        started_at = datetime.now(UTC)
        prices = electricity_maps.fetch_day(key, ZONES)
        prices.to_csv(price_path, index=False)
        urls = [f"{electricity_maps.BASE_URL}?{urllib.parse.urlencode(electricity_maps.query(zone, day))}"
                for zone in ZONES]
        record_retrieval(price_path, urls, started_at)
    prices = prices[prices.zone.isin(ZONES)]
    electricity_maps.market.check_complete(prices, day, ZONES)
    frame = context.drop(columns="alpha").merge(
        prices.pivot(index="interval", columns="zone", values="price").reset_index(),
        on="interval", how="left", validate="one_to_one")
    frame.to_csv(path, index=False)
    return frame


def classify(frame: pd.DataFrame, tolerance: float) -> pd.DataFrame:
    frame = frame.copy()
    frame["cap_published"] = frame.export_limit.notna()
    frame["zero_export_cap"] = frame.export_limit.abs().le(0.001) & frame.cap_published
    frame["at_export_limit"] = (frame.polish_position - frame.export_limit).abs().le(cnec_attribution.POSITION_TOLERANCE_MW)
    known = frame[["PL", "polish_alt", "polish_position", "export_limit"]].notna().all(axis=1)
    below = (frame.export_limit - frame.polish_position).gt(cnec_attribution.POSITION_TOLERANCE_MW)
    frame["binding_known"] = known | below
    frame["binding_export"] = known & frame.at_export_limit & (frame.polish_alt - frame.PL).gt(tolerance)
    for zone in NEIGHBOURS:
        frame[f"lower_{zone}"] = frame.PL.lt(frame[zone]).where(
            frame[[zone, "PL"]].notna().all(axis=1))
    complete = frame[list(ZONES)].notna().all(axis=1)
    frame["lower_all"] = frame[[f"lower_{z}" for z in NEIGHBOURS]].eq(True).all(axis=1).where(complete)
    frame["lower_any"] = frame[[f"lower_{z}" for z in NEIGHBOURS]].eq(True).any(axis=1).where(complete)
    return frame


def summarize(frame: pd.DataFrame) -> pd.DataFrame:
    records = []
    for cohort in ("cap_published", "zero_export_cap", "at_export_limit", "binding_export"):
        selected = frame[frame[cohort]]
        for comparison in (*NEIGHBOURS, "all", "any"):
            values = selected[f"lower_{comparison}"].dropna()
            records.append(dict(cohort=cohort, comparison=comparison, selected=len(selected),
                                comparable=len(values), lower=int(values.sum()),
                                share=float(values.mean()) if len(values) else None))
    return pd.DataFrame(records)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True, help="Inclusive delivery date")
    parser.add_argument("--output", type=Path, default=Path("data/polish-export-caps"))
    parser.add_argument("--price-tolerance", type=float, default=0.01, help="EUR/MWh threshold for inferred binding effect only; neighbour comparison is strictly <")
    parser.add_argument("--price-token-file", type=Path)
    args = parser.parse_args()
    if args.start < date(2026, 5, 6) or args.end < args.start or args.price_tolerance < 0:
        parser.error("Require 2026-05-06 <= start <= end and nonnegative price tolerance")
    if args.price_token_file:
        electricity_maps.TOKEN_FILE = args.price_token_file
    args.output.mkdir(parents=True, exist_ok=True)
    cache = args.output / "inputs"
    cache.mkdir(exist_ok=True)
    frames, failures = [], []
    day = args.start
    while day <= args.end:
        logging.warning("Collecting %s", day)
        try:
            frames.append(collect(MarketDay.on(day), cache))
        except Exception as error:
            logging.exception("Failed day %s", day)
            failures.append({"day": str(day), "error": type(error).__name__})
        day += timedelta(days=1)
    (args.output / "failures.json").write_text(json.dumps(failures, indent=2))
    if not frames:
        raise RuntimeError("No complete days collected; see failures.json")
    frame = classify(pd.concat(frames, ignore_index=True), args.price_tolerance)
    purchases = []
    completed_dates = sorted(frame.interval.dt.tz_convert("Europe/Warsaw").dt.date.unique())
    for key in completed_dates:
        purchases.append(procurement_frame(pse("mbp-tp", str(key), cache), pse("wmb", str(key), cache)))
    frame = frame.merge(pd.concat(purchases, ignore_index=True), on="interval", how="left", validate="one_to_one")
    frame.to_csv(args.output / "intervals.csv", index=False)
    summary = summarize(frame)
    summary.to_csv(args.output / "summary.csv", index=False)
    from scripts.polish_export_caps_report import render
    render(frame, args.output, args.start, args.end, args.price_tolerance)
    coverage = dict(start=str(args.start), end=str(args.end), completed_days=len(frames),
                    failed_days=len(failures), intervals=len(frame),
                    binding_known=int(frame.binding_known.sum()),
                    procurement_intervals=int(frame.procured_mw.notna().sum()),
                    active_procurement_intervals=int(frame.loc[frame.binding_export, "procured_mw"].notna().sum()),
                    price_tolerance_eur_mwh=args.price_tolerance,
                    retrieval=retrieval_coverage(cache, [str(day) for day in completed_dates]).model_dump(mode="json"))
    (args.output / "coverage.json").write_text(json.dumps(coverage, indent=2))
    print(summary.to_string(index=False), flush=True)
    if failures:
        raise SystemExit("Partial report written; failed days must be resolved before population claims")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    main()
