"""Substation coordinates for JAO Static Grid Model names, borrowed from core-tso-data.

JAO publishes grid elements with substation *names* and no coordinates. `github.com/fneum/
core-tso-data` (MIT, by the PyPSA developers) carries hand-corrected geocoding of those
names: one CSV per TSO template under its `OSM-locator/` directory, each row a Static Grid
Model substation name matched to an OSM object's centroid. That directory is our interim
source of coordinates until the JAO/OSM matcher of `wiki/specs/jao-grid.md` lands.

**Nothing extracted here is committed.** The CSVs' first column is JAO Static Grid Model
Content, whose terms forbid redistribution, so the cache lives in a gitignored `data/`
exactly as `jao.py` and `jao_static_grid.py` do; anyone reproducing this work runs `fetch`.

The repository is pinned to a commit rather than tracked on `main`: the corrections are
hand-made and edited in place, so a moving branch would silently move a substation.

This module is a reader and nothing more. One name reaches several templates — a tie-line's
far end appears in both TSOs' files, and the French 225 kV template repeats whole substations
of the 400 kV one — and every such row is returned verbatim. Deciding that two spellings are
one substation, and refusing the pairs that are not, is matching, which lives once in the
pure matcher (`coppersushi/cnec_geometry.py`) because it depends on the key being matched on.
"""

import io
import logging
import re
import sys
import tarfile
import urllib.request
from pathlib import Path

import pandas as pd
from pandera.typing import DataFrame

from coppersushi import REPO
from coppersushi.data_model.osm_locator import LocatedSubstations

logger = logging.getLogger(__name__)

COMMIT = "e5ec3414dad2530f9d57cffb5b23f1a3d100f9cc"
TARBALL_URL = f"https://codeload.github.com/fneum/core-tso-data/tar.gz/{COMMIT}"
CACHE_DIR = REPO / "data" / "osm-locator"
# Committed, unlike the cache: a hand-made list of spellings, carrying no locator content.
ALIASES_FILE = REPO / "config" / "substation-aliases.csv"
TIMEOUT_SECONDS = 300

MEMBER_PATTERN = re.compile(r"^[^/]+/OSM-locator/[^/]+\.csv$")
EXPECTED_CSVS = 18  # Measured at COMMIT: 17 TSO templates plus OTHERCOUNTRIES.
TEMPLATE_PATTERN = re.compile(r"Static Grid Model_(?:template_)?([^_]+)")

# Continental Europe, generously: a corrupt or column-shifted download lands outside it.
EUROPE_BOUNDS = {"x": (-12.0, 35.0), "y": (34.0, 72.0)}


def template_token(filename: str) -> str:
    """The TSO template a cached CSV came from, the only country hint the files carry.

    `..._template_FR225kv_OSM_corrected.csv` is `FR225kv`, and the Belgian file, named for a
    quarter and an EIC dump rather than a template, is `BE`.
    """
    match = TEMPLATE_PATTERN.search(filename)
    if not match:
        raise RuntimeError(f"{filename}: no template token in the name")
    return match.group(1)


def download() -> bytes:
    """The pinned repository tarball."""
    logger.info("osm locator: GET %s", TARBALL_URL)
    with urllib.request.urlopen(TARBALL_URL, timeout=TIMEOUT_SECONDS) as response:
        payload = response.read()
    logger.info("osm locator: %d bytes", len(payload))
    return payload


def locator_members(archive: tarfile.TarFile) -> list[tarfile.TarInfo]:
    """The `OSM-locator/*.csv` members, refusing any name that could escape the cache."""
    members = []
    for member in archive.getmembers():
        if not MEMBER_PATTERN.match(member.name):
            continue
        if Path(member.name).is_absolute() or ".." in Path(member.name).parts:
            raise RuntimeError(f"{member.name}: unsafe member name")
        members.append(member)
    if len(members) != EXPECTED_CSVS:
        raise RuntimeError(f"{len(members)} OSM-locator CSVs, expected {EXPECTED_CSVS}")
    return members


def write_csvs(directory: Path, payload: bytes) -> Path:
    """Extract the locator CSVs into `directory`, flattened to their basenames."""
    directory.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        for member in locator_members(archive):
            extracted = archive.extractfile(member)
            if extracted is None:
                raise RuntimeError(f"{member.name}: not a regular file")
            (directory / Path(member.name).name).write_bytes(extracted.read())
    logger.info("osm locator: wrote %d CSVs to %s", EXPECTED_CSVS, directory)
    return directory


def fetch(directory: Path = CACHE_DIR) -> Path:
    return write_csvs(directory, download())


def read_csv(path: Path) -> pd.DataFrame:
    """One template's rows. The substation name is the CSVs' headerless first column."""
    frame = pd.read_csv(path, index_col=0).rename_axis("name").reset_index()
    return frame.assign(template=template_token(path.name))


def check_located(frame: pd.DataFrame) -> None:
    """Raise unless every row carries a coordinate that could be a European substation."""
    for column, (low, high) in EUROPE_BOUNDS.items():
        outside = frame[frame[column].isna() | ~frame[column].between(low, high)]
        if len(outside):
            raise RuntimeError(
                f"{len(outside)} rows with {column} outside [{low}, {high}]: "
                f"{sorted(outside.name)[:5]}"
            )


def read_csvs(directory: Path = CACHE_DIR) -> DataFrame[LocatedSubstations]:
    """Every cached template's located rows, tidied and validated.

    Rows without coordinates are the ones nobody found; they carry no information a lookup
    can use, so they are dropped here rather than at every call site.
    """
    paths = sorted(directory.glob("*.csv"))
    if not paths:
        raise RuntimeError(f"no locator CSVs in {directory}; run `python -m {__spec__.name} fetch`")
    frame = pd.concat([read_csv(path) for path in paths], ignore_index=True)
    frame = frame.rename(columns={"OSM_id": "osm_id"}).dropna(subset=["x", "y"])
    check_located(frame)
    logger.info("osm locator: %d CSVs, %d located rows", len(paths), len(frame))
    return frame[list(LocatedSubstations.to_schema().columns)].pipe(LocatedSubstations.validate)


def load_aliases(path: Path = ALIASES_FILE) -> dict[str, str]:
    """Published substation names the locator files under a different name.

    Hand-written, because the differences are not spelling rules: `Velke Kapusany` is
    `V. Kapusany` there, and a tap point published as `Y_Mellach` is `Dreibein Mellach`.
    A published name whose site the locator holds under two candidate names is left out —
    picking one is exactly the wrong-location error the table exists to prevent.
    """
    aliases = pd.read_csv(path)
    return dict(zip(aliases.published_name, aliases.locator_name))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    match sys.argv[1:]:
        case ["fetch"]:
            read_csvs(fetch())
        case _:
            sys.exit(f"usage: python -m {__spec__.name} fetch")
