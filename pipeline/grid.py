"""Pure PyPSA network transformations for the European grid."""

from dataclasses import dataclass

import pandas as pd
import pypsa

# osm-prebuilt has no transformer impedances; PyPSA-Eur's default (r stays 0,
# same as PyPSA-Eur — harmless for linear power flow, which ignores resistance)
TRANSFORMER_X = 0.1


@dataclass(frozen=True)
class GridTables:
    """In-memory osm-prebuilt tables consumed by the grid transformation."""

    buses: pd.DataFrame
    lines: pd.DataFrame
    links: pd.DataFrame
    converters: pd.DataFrame
    transformers: pd.DataFrame


def build_network(tables: GridTables) -> pypsa.Network:
    """Assemble precomputed electrical tables into a PyPSA network."""
    buses = tables.buses
    lines = tables.lines
    links = tables.links
    converters = tables.converters
    transformers = tables.transformers

    n = pypsa.Network()
    n.add("Carrier", ["AC", "DC", "converter"])
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
        carrier="AC",
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

    for branches in (n.lines, n.links, n.transformers):
        dangling = branches[~branches.bus0.isin(n.buses.index) | ~branches.bus1.isin(n.buses.index)]
        assert dangling.empty, f"branches reference unknown buses: {dangling.index.tolist()[:5]}"
    return n


def cross_border(n: pypsa.Network, component: str, country0: str, country1: str) -> pd.DataFrame:
    """Branches of `component` ("Line" or "Link") crossing the country0-country1 border."""
    df = n.components[component].static
    c0 = df.bus0.map(n.buses.country)
    c1 = df.bus1.map(n.buses.country)
    forward = (c0 == country0) & (c1 == country1)
    backward = (c0 == country1) & (c1 == country0)
    return df[forward | backward]
