"""Read one precomputed OPF hour; build the token-free shelf when packaging the image."""
import gzip
import json
from pathlib import Path

import pandas as pd
import plotly.io as pio

from coppersushi import REPO, map_style, power_flow
from coppersushi.data_sources import networks

DIRECTORY = REPO / 'data' / 'opf-2024'


def snapshots(directory: Path = DIRECTORY) -> pd.DatetimeIndex | None:
    path = directory / 'snapshots.json'
    if not path.exists():
        return None
    return pd.DatetimeIndex(pd.to_datetime(json.loads(path.read_text()), utc=True), tz='UTC')


def write(fig, times: pd.DatetimeIndex, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    # PyPSA stores naive UTC snapshots; normalize them at the bundle boundary.
    times = pd.DatetimeIndex(pd.to_datetime(times, utc=True), tz='UTC')
    for index in range(len(times)):
        hour = power_flow.show_snapshot(fig, index)
        hour.update_layout(mapbox_accesstoken=None)
        with gzip.open(directory / f'{index}.json.gz', 'wt') as output:
            output.write(hour.to_json())
    (directory / 'snapshots.json').write_text(json.dumps([t.isoformat() for t in times]))


def load(index: int, token: str, directory: Path = DIRECTORY):
    with gzip.open(directory / f'{index}.json.gz', 'rt') as source:
        fig = pio.from_json(source.read())
    fig.update_layout(mapbox_accesstoken=token)
    return fig


def build() -> None:
    network = networks.load(networks.solved('2024-08-29'))
    fig = power_flow.colored_network_figure(network, 'net_power')
    fig.update_layout(mapbox=map_style.OPF_CAMERA)
    write(fig, network.snapshots, DIRECTORY)
