"""JAO's Core publication web service: a market day of both feeds, fetched and kept as CSV.

`https://publicationtool.jao.eu/core/api/data/<page>?FromUtc=…&ToUtc=…`, public and keyless.
Every column decision lives in `cnecs`; this module is the HTTP, the hour loop and the CSV.

Two things about the service shape the code. An hour of `finalComputation` is about 20 MB of
JSON, so it is requested one hour at a time and turned into its tidy frames before the next
request — a day of raw rows would be half a gigabyte. And the response is a paged envelope
whose `totalRows` can exceed the rows it carries, which is why every response is checked:
a silently truncated hour is indistinguishable from a quiet one.

Field meanings: `wiki/literature/jao-core-publication-handbook.md`. Design: `wiki/specs/jao-grid.md`.
"""

import json
import logging
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from typing import NamedTuple

import pandas as pd
import pandera as pa
from pandera.typing import DataFrame

from coppersushi import REPO, cnecs
from coppersushi.data_model.jao import (
    ActiveConstraints,
    ActiveExternalConstraints,
    Contingencies,
    ConstraintPtdfs,
    ElementEnds,
    Elements,
    ExternalConstraints,
    ExternalConstraintsWithPrices,
    ShadowPrices,
)
from coppersushi.market_day import MarketDay

logger = logging.getLogger(__name__)

BASE_URL = "https://publicationtool.jao.eu/core/api/data"
JAO_DIR = REPO / "data" / "jao"
TIMEOUT_SECONDS = 300


class InvalidDomainCache(RuntimeError):
    """Domain tables with missing or incompatible endpoint coverage."""


class Day(NamedTuple):
    """One market day of JAO, as the five tables `cnecs` builds."""

    elements: DataFrame[Elements]
    contingencies: DataFrame[Contingencies]
    shadow_prices: DataFrame[ShadowPrices]
    external_constraints: DataFrame[ExternalConstraintsWithPrices]
    element_ends: DataFrame[ElementEnds]  # Hour-free: each publisher's orientation of its elements


class ActiveDay(NamedTuple):
    """Post-auction flow-based constraints: physical rows, PTDFs and non-spatial rows."""

    constraints: DataFrame[ActiveConstraints]
    ptdfs: DataFrame[ConstraintPtdfs]
    external_constraints: DataFrame[ActiveExternalConstraints]


MODELS = (Elements, Contingencies, ShadowPrices, ExternalConstraintsWithPrices, ElementEnds)
ACTIVE_MODELS = (ActiveConstraints, ConstraintPtdfs, ActiveExternalConstraints)


def day_dir(day: str) -> Path:
    return JAO_DIR / day


def hours_for(day: str) -> pd.DatetimeIndex:
    """The hours to fetch: the market day, which is not the UTC day and is not always 24 long."""
    return MarketDay.on(day).hours()


def check_complete(endpoint: str, rows: list[dict], total: int) -> None:
    """Raise unless the response carried every row it claims to have."""
    if len(rows) != total:
        raise RuntimeError(f"{endpoint} returned {len(rows)} of {total} rows: the response is paginated")


def _stamp(moment: pd.Timestamp) -> str:
    """An instant in the form the service's `FromUtc`/`ToUtc` expect."""
    return moment.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _get(
    endpoint: str, start: pd.Timestamp, end: pd.Timestamp, timeout: int = TIMEOUT_SECONDS,
    base_url: str = BASE_URL,
) -> list[dict]:
    """The rows of one page over `[start, end)`, refusing a truncated response."""
    # JAO requires a page size; its maximum keeps our bounded window in one response.
    window = {"FromUtc": _stamp(start), "ToUtc": _stamp(end), "Take": 100_000_000}
    url = f"{base_url}/{endpoint}?{urllib.parse.urlencode(window)}"
    logger.info("jao: GET %s %s..%s", endpoint, window["FromUtc"], window["ToUtc"])
    with urllib.request.urlopen(url, timeout=timeout) as response:
        payload = json.load(response)
    rows = payload["data"]
    if "totalRows" in payload:
        check_complete(endpoint, rows, payload["totalRows"])
    logger.info("jao: %s %s → %d rows", endpoint, window["FromUtc"], len(rows))
    return rows


def fetch_hours(
    hours: pd.DatetimeIndex,
) -> tuple[
    DataFrame[Elements],
    DataFrame[Contingencies],
    DataFrame[ExternalConstraints],
    DataFrame[ElementEnds],
]:
    """`finalComputation` for each hour, tidied and discarded before the next is requested."""
    elements, contingencies, externals, ends = [], [], [], []
    for hour in hours:
        rows = _get("finalComputation", hour, hour + pd.Timedelta(hours=1))
        elements.append(cnecs.elements(rows))
        contingencies.append(cnecs.contingencies(rows))
        externals.append(cnecs.external_constraints(rows))
        ends.append(cnecs.element_ends(rows))
    return (
        pd.concat(elements, ignore_index=True).pipe(Elements.validate),
        pd.concat(contingencies, ignore_index=True).pipe(Contingencies.validate),
        pd.concat(externals, ignore_index=True).pipe(ExternalConstraints.validate),
        # A publisher's ends do not change by the hour; a day that says otherwise fails here
        pd.concat(ends, ignore_index=True).drop_duplicates(ignore_index=True).pipe(ElementEnds.validate),
    )


def fetch_day(day: str) -> Path:
    """Fetch one market day into `data/jao/<day>/` and return the directory.

    The shadow-price feed is one request for the whole window: it carries only the elements
    that bound, so a day of it is small. Its non-physical rows are joined onto the domain
    feed's rather than concatenated, so a constraint that bound is one row and not two.
    """
    hours = hours_for(day)
    elements, contingencies, externals, ends = fetch_hours(hours)
    prices = _get("shadowPrices", hours[0], hours[-1] + pd.Timedelta(hours=1))
    return write_day(
        day_dir(day),
        elements,
        contingencies,
        cnecs.shadow_prices(prices),
        cnecs.with_constraint_prices(externals, cnecs.external_constraints(prices)),
        ends,
    )


def fetch_active_day(day: str) -> Path:
    """Fetch the post-auction active flow-based constraints for one market day."""
    market_day = MarketDay.on(day)
    rows = _get(
        "activeFbConstraints",
        market_day.start_time_utc,
        market_day.end_time_utc,
    )
    return write_active_day(
        day_dir(day),
        cnecs.active_constraints(rows),
        cnecs.constraint_ptdfs(rows),
        cnecs.active_external_constraints(rows),
    )


def write_day(
    directory: Path,
    elements: DataFrame[Elements],
    contingencies: DataFrame[Contingencies],
    shadow_prices: DataFrame[ShadowPrices],
    external_constraints: DataFrame[ExternalConstraintsWithPrices],
    element_ends: DataFrame[ElementEnds],
) -> Path:
    """Write the five tables after checking endpoint coverage."""
    tables = Day(elements, contingencies, shadow_prices, external_constraints, element_ends)
    _check_domain_contract(tables)
    directory.mkdir(parents=True, exist_ok=True)
    for name, frame in zip(Day._fields, tables):
        frame.to_csv(_path(directory, name), index=False)
    logger.info("jao: wrote %s", directory)
    return directory


def write_active_day(
    directory: Path,
    constraints: DataFrame[ActiveConstraints],
    ptdfs: DataFrame[ConstraintPtdfs],
    external_constraints: DataFrame[ActiveExternalConstraints],
) -> Path:
    """Cache normalized active flow-based tables locally; their directory is gitignored."""
    directory.mkdir(parents=True, exist_ok=True)
    for name, frame in zip(ActiveDay._fields, (constraints, ptdfs, external_constraints)):
        frame.to_csv(_path(directory, f"active_{name}"), index=False)
    logger.info("jao: wrote active flow-based tables to %s", directory)
    return directory


def read_day(directory: Path) -> Day:
    """The five tables back from CSV, each validated once its zone is restored."""
    frames = []
    for name, model in zip(Day._fields, MODELS):
        frame = pd.read_csv(_path(directory, name))
        if "hour" in frame:
            # `read_csv`'s own date parsing is inconsistent about tz across versions, so the
            # column is read as text and converted here.
            frame = frame.assign(hour=pd.to_datetime(frame.hour, utc=True))
        frames.append(_restore_blanks(frame, model).pipe(model.validate))
    day = Day(*frames)
    _check_domain_contract(day)
    return day


def read_active_day(directory: Path) -> ActiveDay:
    frames = []
    for name, model in zip(ActiveDay._fields, ACTIVE_MODELS):
        frame = pd.read_csv(_path(directory, f"active_{name}"))
        frame = frame.assign(interval=pd.to_datetime(frame.interval, utc=True, format="ISO8601"))
        frames.append(_restore_blanks(frame, model).pipe(model.validate))
    return ActiveDay(*frames)


def _restore_blanks(frame: pd.DataFrame, model: type) -> pd.DataFrame:
    """Put back the empty strings CSV cannot tell from missing values.

    `normalise_tso` writes `""` for the TSO of a constraint that belongs to none, and a
    round trip through CSV returns it as NaN. The model says which columns are text that
    may not be null, so those are the ones filled.
    """
    blanks = {
        name: ""
        for name, column in model.to_schema().columns.items()
        if name in frame and not column.nullable and str(column.dtype).startswith("string")
    }
    return frame.fillna(blanks)


def read_element_ends() -> DataFrame[ElementEnds]:
    """The small endpoint cache shared across delivery days."""
    frame = pd.read_csv(JAO_DIR / "element-ends.csv")
    return _restore_blanks(frame, ElementEnds).pipe(ElementEnds.validate)


def write_element_ends(ends: DataFrame[ElementEnds]) -> Path:
    """Replace one validated CSV atomically, so readers never see a half-written cache."""
    ElementEnds.validate(ends)
    JAO_DIR.mkdir(parents=True, exist_ok=True)
    path = JAO_DIR / "element-ends.csv"
    with tempfile.NamedTemporaryFile(dir=JAO_DIR, suffix=".csv", delete=False) as file:
        temporary = Path(file.name)
    try:
        ends.to_csv(temporary, index=False)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def seed_element_ends(days: list[str]) -> Path:
    """Build a deployment seed from validated domain days; the latest day's ends win."""
    ends = pd.concat([read_day(day_dir(day)).element_ends for day in sorted(days)], ignore_index=True)
    ends = ends.drop_duplicates(["eic", "tso", "name"], keep="last")
    if ends.empty:
        raise InvalidDomainCache("endpoint seed is empty")
    return write_element_ends(ends)


def load_element_ends(interval: pd.Timestamp, required: pd.DataFrame) -> DataFrame[ElementEnds]:
    """Use the seed, fetching only the viewed hour when an active element is absent.

    The image carries the seed through dyno restarts. Runtime additions are disposable:
    losing one only costs another hourly fetch, so no background job or lock is needed.
    """
    try:
        ends = read_element_ends()
    except (OSError, ValueError, pa.errors.SchemaError) as error:
        logger.warning("jao: ignoring unusable endpoint cache: %s", error)
        ends = pd.DataFrame(columns=cnecs.END_COLUMNS).pipe(ElementEnds.validate)
    if _missing_element_ends(required, ends).empty:
        return ends
    # Work in UTC: flooring a local DST-change hour can be ambiguous.
    hour = interval.tz_convert("UTC").floor("h")
    try:
        rows = _get("finalComputation", hour, hour + pd.Timedelta(hours=1), timeout=25)
        fetched = cnecs.element_ends(rows)
        combined = pd.concat([ends, fetched], ignore_index=True).drop_duplicates(
            ["eic", "tso", "name"], keep="last"
        )
        _require_element_ends(required, combined)
        write_element_ends(combined)
    except Exception as error:
        logger.exception("jao: endpoint fetch failed for %s", hour)
        raise RuntimeError("Could not load line locations. Please retry.") from error
    return combined


def load_active_day(day: str, refresh: bool = False) -> ActiveDay:
    """Read cached active flow-based tables, fetching on first use or explicit refresh.

    A cache an older adapter wrote lacks columns the tables have since gained; it fails
    validation and is fetched again once. A failure after that is the feed's and propagates.
    """
    directory = day_dir(day)
    first = _path(directory, f"active_{ActiveDay._fields[0]}")
    if refresh or not first.is_file():
        fetch_active_day(day)
        return read_active_day(directory)
    try:
        return read_active_day(directory)
    except pa.errors.SchemaError as stale:
        logger.info("jao: cached %s predates the current tables, fetching again: %s", day, stale)
        fetch_active_day(day)
        return read_active_day(directory)


def _path(directory: Path, name: str) -> Path:
    return directory / f"{name.replace('_', '-')}.csv"


def _check_domain_contract(day: Day) -> None:
    """Every publisher retained by a domain consumer must retain its oriented endpoints."""
    priced = day.shadow_prices[day.shadow_prices.hour.isin(day.elements.hour)]
    identity = ["eic", "tso", "name"]
    required = pd.concat(
        [day.elements[identity], priced[identity]], ignore_index=True
    ).drop_duplicates()
    _require_element_ends(required, day.element_ends)


def _missing_element_ends(required: pd.DataFrame, ends: pd.DataFrame) -> pd.DataFrame:
    identity = ["eic", "tso", "name"]
    missing = required[identity].drop_duplicates().merge(
        ends[identity], on=identity, how="left", indicator=True
    )
    return missing[missing._merge.eq("left_only")]


def _require_element_ends(required: pd.DataFrame, ends: pd.DataFrame) -> None:
    missing = _missing_element_ends(required, ends)
    if not missing.empty:
        pairs = ", ".join(
            f"{row.name} / {row.eic} ({row.tso})" for row in missing.itertuples()
        )
        raise InvalidDomainCache(f"element ends missing named publisher/EIC rows: {pairs}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    match sys.argv[1:]:
        case ["fetch", day]:
            fetch_day(day)
        case ["fetch-active", day]:
            fetch_active_day(day)
        case ["seed", *days] if days:
            seed_element_ends(days)
        case ["check-seed"]:
            if read_element_ends().empty:
                sys.exit("endpoint seed is empty; run the seed command before building")
        case _:
            sys.exit(f"usage: python -m {__spec__.name} {{fetch|fetch-active|seed}} <day> [days...] | check-seed")
