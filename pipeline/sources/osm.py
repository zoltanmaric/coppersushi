"""Source adapter for osm-prebuilt European grid data.

Data: https://zenodo.org/records/18619025 (v0.7, 220-750 kV, ODbL).
The CSVs contain precomputed electrical parameters; ``pipeline.grid`` only
assembles their in-memory representation.
"""

import logging
from pathlib import Path

import pandas as pd

from pipeline.grid import GridTables
from pipeline.sources.download import download as fetch

logger = logging.getLogger(__name__)

OSM_PREBUILT_DIR = Path(__file__).parents[2] / "data" / "osm-prebuilt-v0.7"
ZENODO_URL = "https://zenodo.org/records/18619025/files/{}?download=1"
CSV_NAMES = ["buses", "lines", "links", "converters", "transformers"]


def download(data_dir: Path = OSM_PREBUILT_DIR) -> Path:
    """Download missing CSVs atomically and return their directory."""
    data_dir.mkdir(parents=True, exist_ok=True)
    missing = [name for name in CSV_NAMES if not (data_dir / f"{name}.csv").exists()]
    if missing:
        logger.info("osm-prebuilt: fetching %s from Zenodo into %s", ", ".join(missing), data_dir)
    for name in missing:
        fetch(ZENODO_URL.format(f"{name}.csv"), data_dir / f"{name}.csv")
    if missing:
        logger.info("osm-prebuilt: all %d files present in %s", len(CSV_NAMES), data_dir)
    return data_dir


def load_tables(data_dir: Path = OSM_PREBUILT_DIR) -> GridTables:
    """Load osm-prebuilt CSVs into the grid transformation's input contract."""
    # Geometry fields are single-quote-quoted and span multiple lines.
    def read(name: str) -> pd.DataFrame:
        return pd.read_csv(data_dir / f"{name}.csv", index_col=0, quotechar="'")

    return GridTables(
        buses=read("buses"),
        lines=read("lines"),
        links=read("links"),
        converters=read("converters"),
        transformers=read("transformers"),
    )
