"""The small Core-zone outline bundle, derived from the sanctioned network at build time."""
import json
from pathlib import Path

import pandas as pd
from shapely.geometry import mapping, shape

from coppersushi import REPO, bidding_zones
from coppersushi.data_model.network_views import BiddingZoneShapes
from coppersushi.data_sources import networks

BUNDLE = REPO / "data" / "core-zone-shapes.geojson"


def write(zones: pd.DataFrame, path: Path) -> None:
    BiddingZoneShapes.validate(zones)
    features = [{"type": "Feature", "properties": {"zone": row.zone},
                 "geometry": mapping(row.geometry)} for row in zones.itertuples()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))


def read(path: Path) -> pd.DataFrame:
    features = json.loads(path.read_text())["features"]
    frame = pd.DataFrame({"zone": [f["properties"]["zone"] for f in features],
                          "geometry": [shape(f["geometry"]) for f in features]})
    return frame.astype({"geometry": object}).pipe(BiddingZoneShapes.validate)


def load() -> pd.DataFrame:
    if BUNDLE.exists():
        return read(BUNDLE)
    # Local checkouts need no additional setup; deploys always build the bundle.
    return bidding_zones.core_zone_shapes(networks.load(networks.solved("2024-08-29")).shapes)


def build() -> None:
    """Derive the outline bundle from the solved network, replacing any old bundle."""
    write(bidding_zones.core_zone_shapes(networks.load(networks.solved("2024-08-29")).shapes), BUNDLE)
