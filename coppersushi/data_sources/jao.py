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
import urllib.parse
import urllib.request
from pathlib import Path
from typing import NamedTuple

import pandas as pd
from pandera.typing import DataFrame

from coppersushi import REPO, cnecs
from coppersushi.data_model.jao import (
    Contingencies,
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


class Day(NamedTuple):
    """One market day of JAO, as the four tables `cnecs` builds."""

    elements: DataFrame[Elements]
    contingencies: DataFrame[Contingencies]
    shadow_prices: DataFrame[ShadowPrices]
    external_constraints: DataFrame[ExternalConstraintsWithPrices]


MODELS = (Elements, Contingencies, ShadowPrices, ExternalConstraintsWithPrices)


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
) -> tuple[DataFrame[Elements], DataFrame[Contingencies], DataFrame[ExternalConstraints]]:
    """`finalComputation` for each hour, tidied and discarded before the next is requested."""
    elements, contingencies, externals = [], [], []
    for hour in hours:
        rows = _get("finalComputation", hour, hour + pd.Timedelta(hours=1))
        elements.append(cnecs.elements(rows))
        contingencies.append(cnecs.contingencies(rows))
        externals.append(cnecs.external_constraints(rows))
    return (
        pd.concat(elements, ignore_index=True).pipe(Elements.validate),
        pd.concat(contingencies, ignore_index=True).pipe(Contingencies.validate),
        pd.concat(externals, ignore_index=True).pipe(ExternalConstraints.validate),
    )


def fetch_day(day: str) -> Path:
    """Fetch one market day into `data/jao/<day>/` and return the directory.

    The shadow-price feed is one request for the whole window: it carries only the elements
    that bound, so a day of it is small. Its non-physical rows are joined onto the domain
    feed's rather than concatenated, so a constraint that bound is one row and not two.
    """
    hours = hours_for(day)
    elements, contingencies, externals = fetch_hours(hours)
    prices = _get("shadowPrices", hours[0], hours[-1] + pd.Timedelta(hours=1))
    return write_day(
        day_dir(day),
        elements,
        contingencies,
        cnecs.shadow_prices(prices),
        cnecs.with_constraint_prices(externals, cnecs.external_constraints(prices)),
    )


def write_day(
    directory: Path,
    elements: DataFrame[Elements],
    contingencies: DataFrame[Contingencies],
    shadow_prices: DataFrame[ShadowPrices],
    external_constraints: DataFrame[ExternalConstraintsWithPrices],
) -> Path:
    """Write the four tables as CSV, creating the directory."""
    directory.mkdir(parents=True, exist_ok=True)
    for name, frame in zip(Day._fields, (elements, contingencies, shadow_prices, external_constraints)):
        frame.to_csv(_path(directory, name), index=False)
    logger.info("jao: wrote %s", directory)
    return directory


def read_day(directory: Path) -> Day:
    """The four tables back from CSV, each validated once its zone is restored."""
    frames = []
    for name, model in zip(Day._fields, MODELS):
        frame = pd.read_csv(_path(directory, name))
        # `read_csv`'s own date parsing is inconsistent about tz across versions, so the
        # column is read as text and converted here.
        frame = frame.assign(hour=pd.to_datetime(frame.hour, utc=True))
        frames.append(_restore_blanks(frame, model).pipe(model.validate))
    return Day(*frames)


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


def load_day(day: str) -> Day:
    return read_day(day_dir(day))


def _path(directory: Path, name: str) -> Path:
    return directory / f"{name.replace('_', '-')}.csv"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    match sys.argv[1:]:
        case ["fetch", day]:
            fetch_day(day)
        case _:
            sys.exit(f"usage: python -m {__spec__.name} fetch <day>")
