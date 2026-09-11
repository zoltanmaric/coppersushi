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

import fcntl
import hashlib
import json
import logging
import sys
import tempfile
import threading
import time
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
# Bump when a table's meaning changes without a schema change. Old caches must never be
# allowed to impersonate output from a newer normaliser, as the pre-manifest endpoint table did.
DOMAIN_CACHE_VERSION = 1
DOMAIN_MANIFEST = "domain-cache-manifest.json"
DOMAIN_FETCH_LOCK = ".domain-fetch.lock"
DOMAIN_FETCH_FAILURE = ".domain-fetch-failure.json"
DOMAIN_FETCH_RETRY_SECONDS = 300
_DOMAIN_FETCH_LOCK = threading.Lock()


class InvalidDomainCache(RuntimeError):
    """A domain cache that was not completely written by this adapter version."""


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


def _get(endpoint: str, start: pd.Timestamp, end: pd.Timestamp) -> list[dict]:
    """The rows of one page over `[start, end)`, refusing a truncated response."""
    window = {"FromUtc": _stamp(start), "ToUtc": _stamp(end)}
    url = f"{BASE_URL}/{endpoint}?{urllib.parse.urlencode(window)}"
    logger.info("jao: GET %s %s..%s", endpoint, window["FromUtc"], window["ToUtc"])
    with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:
        payload = json.load(response)
    rows = payload["data"]
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
    """Publish one validated, versioned set of domain tables.

    The manifest is the completion marker. Its version invalidates tables made by an
    older normaliser even when their CSV schema still happens to validate; its hashes
    reject interrupted writes that mixed two generations of the cache.
    """
    day = Day(elements, contingencies, shadow_prices, external_constraints, element_ends)
    _check_domain_contract(day)
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".domain-cache-", dir=directory) as staging_name:
        staging = Path(staging_name)
        files = {}
        for name, frame in zip(Day._fields, day):
            path = _path(staging, name)
            frame.to_csv(path, index=False)
            files[path.name] = _sha256(path)
        manifest = {"version": DOMAIN_CACHE_VERSION, "files": files}
        staged_manifest = staging / DOMAIN_MANIFEST
        staged_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

        # Files move first and the manifest last. An interrupted update therefore leaves
        # hashes that cannot authenticate a mixture of two cache generations.
        for name in Day._fields:
            _path(staging, name).replace(_path(directory, name))
        staged_manifest.replace(directory / DOMAIN_MANIFEST)
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
    """The five tables back from one complete, current cache generation."""
    _check_domain_manifest(directory)
    try:
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
    except InvalidDomainCache:
        raise
    except (KeyError, OSError, ValueError, pa.errors.SchemaError) as error:
        raise InvalidDomainCache(f"invalid JAO domain cache in {directory}: {error}") from error


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


def load_day(day: str, refresh: bool = False) -> Day:
    """Read a domain day, fetching it once inside the first request that needs it.

    The file lock makes this single-flight across web workers as well as threads. A failed
    attempt leaves a short-lived marker so callbacks already queued behind it surface the
    same error instead of each restarting the half-gigabyte download.
    """
    directory = day_dir(day)
    if not refresh:
        try:
            return read_day(directory)
        except InvalidDomainCache as stale:
            logger.info("jao: cached %s is fetched again: %s", day, stale)
    directory.mkdir(parents=True, exist_ok=True)
    # Dash may handle several initial callbacks concurrently. Serialising domain refreshes
    # is deliberate: each one downloads roughly half a gigabyte from JAO.
    with _DOMAIN_FETCH_LOCK:
        with (directory / DOMAIN_FETCH_LOCK).open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not refresh:
                try:
                    loaded = read_day(directory)  # Another worker may have finished it.
                    _clear_domain_fetch_failure(directory)
                    return loaded
                except InvalidDomainCache:
                    pass
                if failure := _recent_domain_fetch_failure(directory):
                    raise RuntimeError(
                        f"JAO domain fetch for {day} failed recently; not retrying yet: {failure}"
                    )
            try:
                fetch_day(day)
                loaded = read_day(directory)
            except Exception as error:
                _record_domain_fetch_failure(directory, error)
                raise
            _clear_domain_fetch_failure(directory)
            return loaded


def _recent_domain_fetch_failure(directory: Path) -> str | None:
    path = directory / DOMAIN_FETCH_FAILURE
    try:
        failure = json.loads(path.read_text())
        if time.time() - float(failure["failed_at"]) < DOMAIN_FETCH_RETRY_SECONDS:
            return str(failure["message"])
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        pass
    return None


def _record_domain_fetch_failure(directory: Path, error: Exception) -> None:
    try:
        (directory / DOMAIN_FETCH_FAILURE).write_text(
            json.dumps({"failed_at": time.time(), "message": str(error)}) + "\n"
        )
    except OSError as marker_error:
        logger.warning("jao: could not record failed domain fetch: %s", marker_error)


def _clear_domain_fetch_failure(directory: Path) -> None:
    try:
        (directory / DOMAIN_FETCH_FAILURE).unlink(missing_ok=True)
    except OSError as marker_error:
        logger.warning("jao: could not clear failed domain fetch marker: %s", marker_error)


def has_day(day: str) -> bool:
    """Whether a current adapter completely wrote and can authenticate this domain day."""
    try:
        _check_domain_manifest(day_dir(day))
        return True
    except InvalidDomainCache:
        return False


def domain_generation(day: str) -> str | None:
    """Cheap identity of a current cache generation, for invalidating in-memory derivatives."""
    try:
        manifest = _read_domain_manifest(day_dir(day))
    except InvalidDomainCache:
        return None
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_domain_manifest(directory: Path) -> dict:
    """Read a current manifest and cheaply prove that every table it names exists."""
    path = directory / DOMAIN_MANIFEST
    try:
        manifest = json.loads(path.read_text())
        if manifest.get("version") != DOMAIN_CACHE_VERSION:
            raise InvalidDomainCache(
                f"JAO domain cache in {directory} has version {manifest.get('version')!r}, "
                f"expected {DOMAIN_CACHE_VERSION}"
            )
        expected = {_path(directory, name).name for name in Day._fields}
        files = manifest["files"]
        if not isinstance(files, dict):
            raise InvalidDomainCache(f"JAO domain cache in {directory} has an invalid manifest")
        if set(files) != expected:
            raise InvalidDomainCache(f"JAO domain cache in {directory} names the wrong tables")
        missing = [name for name in files if not (directory / name).is_file()]
        if missing:
            raise InvalidDomainCache(f"JAO domain cache in {directory} misses {', '.join(missing)}")
        return manifest
    except InvalidDomainCache:
        raise
    except (json.JSONDecodeError, KeyError, OSError, TypeError) as error:
        raise InvalidDomainCache(f"incomplete JAO domain cache in {directory}: {error}") from error


def _check_domain_manifest(directory: Path) -> None:
    """Refuse absent, obsolete, incomplete and mixed-generation domain caches."""
    manifest = _read_domain_manifest(directory)
    changed = [
        name for name, digest in manifest["files"].items() if _sha256(directory / name) != digest
    ]
    if changed:
        raise InvalidDomainCache(
            f"JAO domain cache in {directory} failed its checksum: {', '.join(changed)}"
        )


def _check_domain_contract(day: Day) -> None:
    """Every publisher retained by a domain consumer must retain its oriented endpoints."""
    priced = day.shadow_prices[day.shadow_prices.hour.isin(day.elements.hour)]
    identity = ["eic", "tso", "name"]
    required = pd.concat(
        [day.elements[identity], priced[identity]], ignore_index=True
    ).drop_duplicates()
    present = day.element_ends[identity].drop_duplicates()
    missing = required.merge(present, on=identity, how="left", indicator=True)
    missing = missing[missing._merge.eq("left_only")]
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
        case _:
            sys.exit(f"usage: python -m {__spec__.name} {{fetch|fetch-active}} <day>")
