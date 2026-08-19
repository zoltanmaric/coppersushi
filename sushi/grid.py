"""Build a PyPSA network from the osm-prebuilt European grid (Xiong et al. 2025).

Data: https://zenodo.org/records/18619025 (v0.7, 220-750 kV, ODbL).
The CSVs ship with electrical parameters (r, x, b, s_nom) precomputed,
so this is assembly, not parameter estimation.
"""

from pathlib import Path

import pandas as pd
import pypsa

OSM_PREBUILT_DIR = Path(__file__).parent.parent / "data" / "osm-prebuilt-v0.7"
ZENODO_URL = "https://zenodo.org/records/18619025/files/{}?download=1"
CSV_NAMES = ["buses", "lines", "links", "converters", "transformers"]

# osm-prebuilt has no transformer impedances; PyPSA-Eur's default
TRANSFORMER_X = 0.1


def download(data_dir: Path = OSM_PREBUILT_DIR) -> None:
    import urllib.request

    data_dir.mkdir(parents=True, exist_ok=True)
    for name in CSV_NAMES:
        target = data_dir / f"{name}.csv"
        if not target.exists():
            urllib.request.urlretrieve(ZENODO_URL.format(f"{name}.csv"), target)


def build_network(data_dir: Path = OSM_PREBUILT_DIR) -> pypsa.Network:
    # geometry fields are single-quote-quoted and span multiple lines
    read = lambda name: pd.read_csv(data_dir / f"{name}.csv", index_col=0, quotechar="'")
    buses, lines, links, converters, transformers = map(read, CSV_NAMES)

    n = pypsa.Network()
    n.add(
        "Bus",
        buses.index,
        v_nom=buses.voltage,
        x=buses.x,
        y=buses.y,
        country=buses.country,
        carrier=buses.dc.map({"t": "DC", "f": "AC"}),
    )
    n.add(
        "Line",
        lines.index,
        bus0=lines.bus0,
        bus1=lines.bus1,
        r=lines.r,
        x=lines.x,
        b=lines.b,
        s_nom=lines.s_nom,
        length=lines.length / 1e3,
        type="",  # explicit parameters above take precedence
    )
    # HVDC links and AC/DC converters are both controllable, bidirectional Links
    n.add(
        "Link",
        links.index,
        bus0=links.bus0,
        bus1=links.bus1,
        p_nom=links.p_nom,
        p_min_pu=-1,
        length=links.length / 1e3,
        carrier="DC",
    )
    n.add(
        "Link",
        converters.index,
        bus0=converters.bus0,
        bus1=converters.bus1,
        p_nom=converters.p_nom,
        p_min_pu=-1,
        carrier="converter",
    )
    n.add(
        "Transformer",
        transformers.index,
        bus0=transformers.bus0,
        bus1=transformers.bus1,
        s_nom=transformers.s_nom,
        x=TRANSFORMER_X,
    )
    return n


def cross_border(n: pypsa.Network, component: str, country0: str, country1: str) -> pd.DataFrame:
    """Branches of `component` ("Line" or "Link") crossing the country0-country1 border."""
    df = n.components[component].static
    c0 = df.bus0.map(n.buses.country)
    c1 = df.bus1.map(n.buses.country)
    forward = (c0 == country0) & (c1 == country1)
    backward = (c0 == country1) & (c1 == country0)
    return df[forward | backward]


if __name__ == "__main__":
    download()
    n = build_network()
    print(n)
