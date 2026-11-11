"""Prepare token-free hourly OPF figures for static publication."""
import gzip
import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from coppersushi import REPO
from coppersushi import map_style
from coppersushi.opf import power_flow
from coppersushi.opf.data_sources import networks

DIRECTORY = REPO / 'data' / 'opf-2024'


def write(fig: go.Figure, times: pd.Index, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    # PyPSA stores naive UTC snapshots; normalize them at the bundle boundary.
    times = pd.DatetimeIndex(pd.to_datetime(times, utc=True), tz='UTC')
    for index in range(len(times)):
        hour = power_flow.show_snapshot(fig, index)
        hour.update_layout(mapbox_accesstoken=None)
        with gzip.open(directory / f'{index}.json.gz', 'wt') as output:
            output.write(hour.to_json())
    (directory / 'snapshots.json').write_text(json.dumps([t.isoformat() for t in times]))


def build() -> None:
    network = networks.load(networks.solved('2024-08-29'))
    fig = power_flow.colored_network_figure(network, 'net_power')
    fig.update_layout(mapbox=map_style.OPF_CAMERA)
    write(fig, network.snapshots, DIRECTORY)


if __name__ == '__main__':
    build()
