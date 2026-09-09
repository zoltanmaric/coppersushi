"""JAO's Core Static Grid Model: one release's workbook, fetched and kept as CSV.

A release is a zip of a handbook, a map and one workbook, published at a stable URL under
`https://www.jao.eu/sites/default/files/`. Every release back to the 1st stays downloadable
under an `outdated_` prefix, so provenance is the URL plus the workbook's own date.

**Nothing derived from the workbook is committed.** JAO's terms of use reserve every right
of reproduction and permit only "internal information purposes", so neither the workbook nor
the tables built from it may be redistributed. `fetch` is the only way to obtain them, and it
writes into a gitignored `data/` — anyone reproducing this work runs it.

`coppersushi/data_sources/jao.py` is untouched by this. That module reads the publication
tool — what the grid *did* in a given hour; this one reads what the equipment *is*. Two
sources, two modules, one join key (`EIC_Code`).

Every column decision lives in `static_grid`; this module is the HTTP, the zip and the CSV.

Three things are asserted before a byte is parsed, because the release is identified by
nothing inside the workbook itself: the zip's byte count, the workbook's date prefix — the
containing folder is named for the upload month (`2024-10`), not the release — and the
sheet names.

Design: `wiki/specs/jao-grid.md`.
"""

import io
import logging
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import NamedTuple

import pandas as pd
from pandera.typing import DataFrame

from coppersushi import REPO, static_grid
from coppersushi.data_model.static_grid import Branches, Transformers

logger = logging.getLogger(__name__)

BASE_URL = "https://www.jao.eu/sites/default/files"
STATIC_GRID_DIR = REPO / "data" / "jao-static-grid"
TIMEOUT_SECONDS = 300

WORKBOOK_SHEETS = ("Lines", "Tielines", "Transformers", "Remedial Actions", "Change Log")


class Release(NamedTuple):
    """Where one release lives and what it must turn out to be."""

    path: str  # Under BASE_URL, percent-encoded as JAO publishes it
    workbook: str  # The member to read; its date prefix is the release's identity
    zip_bytes: int  # Measured; a different size is a different publication


RELEASES = {
    "2024-03-29": Release(
        path="2024-10/outdated_Core%20Static%20Grid%20Model%20%E2%80%93%205th%20release.zip",
        workbook="20240329_Core Static Grid Model_public.xlsx",
        zip_bytes=1_727_357,
    ),
}


class Model(NamedTuple):
    """One release of the Static Grid Model, as the two tables `static_grid` builds."""

    transformers: DataFrame[Transformers]
    branches: DataFrame[Branches]


TABLES = {"transformers": Transformers, "branches": Branches}  # file stem → its model


def release_dir(release: str) -> Path:
    return STATIC_GRID_DIR / release


def check_download(spec: Release, payload: bytes) -> None:
    """Raise unless the zip is the one that was measured."""
    if len(payload) != spec.zip_bytes:
        raise RuntimeError(f"{spec.path}: {len(payload)} bytes, expected {spec.zip_bytes}")


def check_workbook(release: str, name: str, sheets: list[str]) -> None:
    """Raise unless the extracted workbook is this release's, with the sheets it should have."""
    expected_date = release.replace("-", "")
    if not name.startswith(expected_date):
        raise RuntimeError(f"{name}: not the {release} release; the folder is named for the upload month")
    if tuple(sheets) != WORKBOOK_SHEETS:
        raise RuntimeError(f"{name}: sheets {sheets}, expected {list(WORKBOOK_SHEETS)}")


def read_sheets(release: str, workbook: bytes, name: str) -> dict[str, pd.DataFrame]:
    """The three equipment sheets, read past the merged banner row."""
    with pd.ExcelFile(io.BytesIO(workbook), engine="openpyxl") as book:
        check_workbook(release, name, book.sheet_names)
        return {
            sheet: book.parse(sheet_name=sheet, header=static_grid.HEADER_ROW)
            for sheet in static_grid.SHEETS
        }


def download(spec: Release) -> bytes:
    """The release zip, refused unless it is the size it was measured at."""
    url = f"{BASE_URL}/{spec.path}"
    logger.info("jao static grid: GET %s", url)
    with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:
        payload = response.read()
    check_download(spec, payload)
    logger.info("jao static grid: %d bytes", len(payload))
    return payload


def fetch(release: str = static_grid.RELEASE) -> Path:
    """Fetch one release into `data/jao-static-grid/<release>/` and return the directory."""
    spec = RELEASES[release]
    with zipfile.ZipFile(io.BytesIO(download(spec))) as archive:
        workbook = archive.read(spec.workbook)
    sheets = read_sheets(release, workbook, spec.workbook)
    return write_release(
        release_dir(release),
        static_grid.transformers(sheets["Transformers"]),
        static_grid.branches(sheets["Lines"], sheets["Tielines"]),
    )


def write_release(
    directory: Path,
    transformers: DataFrame[Transformers],
    branches: DataFrame[Branches],
) -> Path:
    """Write the two tables as CSV, creating the directory, after reporting what is in them.

    The two counts are logged because neither is visible in the CSV without looking for
    it, and both are traps for whatever joins these tables next: rows the workbook gives
    an unusable reactance, and EICs it publishes twice.
    """
    directory.mkdir(parents=True, exist_ok=True)
    for name, frame in {"transformers": transformers, "branches": branches}.items():
        report(name, frame)
        frame.to_csv(directory / f"{name}.csv", index=False)
    logger.info("jao static grid: wrote %s", directory)
    return directory


def report(name: str, frame: pd.DataFrame) -> None:
    """Log the two counts a consumer of this table has to make a decision about."""
    unusable = frame[~frame.x_physical]
    collisions = static_grid.eic_collisions(frame)
    logger.info(
        "jao static grid: %s: %d rows; %d with an unusable reactance %s; %d rows over %d colliding EICs %s",
        name, len(frame), len(unusable), sorted(unusable.eic.dropna())[:5],
        len(collisions), collisions.eic.nunique(), sorted(set(collisions.eic))[:5],
    )


def read_release(directory: Path) -> Model:
    """The two tables back from CSV, each validated."""
    return Model(
        **{
            name: pd.read_csv(directory / f"{name}.csv").pipe(model.validate)
            for name, model in TABLES.items()
        }
    )


def load_release(release: str = static_grid.RELEASE) -> Model:
    return read_release(release_dir(release))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    match sys.argv[1:]:
        case ["fetch"]:
            fetch()
        case ["fetch", release]:
            fetch(release)
        case _:
            sys.exit(f"usage: python -m {__spec__.name} fetch [<release>]")
