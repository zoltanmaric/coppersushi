from pathlib import Path

import pandas as pd

from pipeline import flows, grid
from pipeline.sources import osm

OSM_TINY = Path(__file__).parent / "fixtures" / "osm-tiny"


def test_zero_placeholder():
    n = flows.zero_placeholder(grid.build_network(osm.load_tables(OSM_TINY)))

    assert len(n.snapshots) == 1
    # Noon Brussels (CEST) as a PyPSA-forced naive snapshot meaning UTC
    assert n.snapshots[0] == pd.Timestamp("2026-08-12 10:00")
    assert (n.buses_t.p.columns == n.buses.index).all()
    assert (n.buses_t.p == 0).all().all()
    assert (n.lines_t.p0 == 0).all().all()
    assert (n.links_t.p0 == 0).all().all()
    assert (n.transformers_t.p0 == 0).all().all()
