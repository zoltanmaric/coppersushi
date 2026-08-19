"""Source adapter for osm-prebuilt European grid data.

Data: https://zenodo.org/records/18619025 (v0.7, 220-750 kV, ODbL).
The CSVs contain precomputed electrical parameters; ``pipeline.grid`` only
assembles their in-memory representation.
"""

import urllib.request
from pathlib import Path

import pandas as pd

from pipeline.grid import GridTables

OSM_PREBUILT_DIR = Path(__file__).parents[2] / "data" / "osm-prebuilt-v0.7"
ZENODO_URL = "https://zenodo.org/records/18619025/files/{}?download=1"
CSV_NAMES = ["buses", "lines", "links", "converters", "transformers"]


def download(data_dir: Path = OSM_PREBUILT_DIR) -> Path:
    """Download missing CSVs atomically and return their directory."""
    data_dir.mkdir(parents=True, exist_ok=True)
    for name in CSV_NAMES:
        target = data_dir / f"{name}.csv"
        if not target.exists():
            partial = target.with_suffix(".csv.part")
            urllib.request.urlretrieve(ZENODO_URL.format(f"{name}.csv"), partial)
            partial.replace(target)
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
