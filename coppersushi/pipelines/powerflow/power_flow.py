from __future__ import annotations

from typing import TYPE_CHECKING
import pandas as pd
import pyproj
if TYPE_CHECKING:
    import pypsa
from pandera.typing import DataFrame

from coppersushi.pipelines.data_model.network_views import (
    BranchInfo,
    BranchInfoForSnapshot,
    BusCoordinates,
)

def sum_generators_t_attribute_by_bus(n: pypsa.Network, generators_t_attr: pd.DataFrame, technology: str | None = None) -> pd.DataFrame:
    attribute_by_generators = generators_t_attr.filter(like=technology) if technology else generators_t_attr

    # Rename generators columns to their corresponding bus names
    # This may result with multiple columns with the same name,
    # if multiple generators were matched on the same bus for the given technology
    attribute_by_buses = attribute_by_generators.rename(n.generators.bus, axis='columns').\
        rename_axis('Bus', axis='columns')

    # Group and sum by bus, in case there's multiple generators for a tech substring
    # (e.g. offwind and onwind for 'wind')
    attribute_by_buses_sum = attribute_by_buses.T.groupby(level=0).sum().T
    return attribute_by_buses_sum


def get_bus_coordinates(n: pypsa.Network, bus_name: str) -> DataFrame[BusCoordinates]:
    """:return: columns matching `data_model.network_views.BusCoordinates`, renamed to
    `<bus_name>_x`/`<bus_name>_y` — not validated against that model since the column
    names it produces depend on `bus_name`.
    """
    return n.buses.loc[n.branches()[bus_name]][['x', 'y']] \
            .set_index(n.branches().index) \
            .rename(dict(x=bus_name+'_x', y=bus_name+'_y'), axis='columns')


# Mercator projection, as used by MapBox: https://docs.mapbox.com/mapbox-gl-js/example/projections/
epsg3857 = pyproj.Proj('epsg:3857')


def get_branch_midpoint(branch_info: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Project lat/lon of branch buses to x/y coordinates,
    calculate mid-point between them,
    project mid-point back to lat/lon coordinates.
    """

    x0, y0 = epsg3857(longitude=branch_info.bus0_x, latitude=branch_info.bus0_y)
    x1, y1 = epsg3857(longitude=branch_info.bus1_x, latitude=branch_info.bus1_y)
    mid_x = (x0 + x1) / 2
    mid_y = (y0 + y1) / 2
    mid_lon, mid_lat = epsg3857(longitude=mid_x, latitude=mid_y, inverse=True)

    return mid_lon, mid_lat


geodesic = pyproj.Geod(ellps='WGS84')


def get_branch_direction(branch_info: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Branch power flow direction angle (clockwise from North)."""
    [direction, inverse_direction, _] = \
        geodesic.inv(branch_info.bus0_x, branch_info.bus0_y, branch_info.bus1_x, branch_info.bus1_y)
    return direction, inverse_direction


def get_branch_info(n: pypsa.Network) -> DataFrame[BranchInfo]:
    """Builds a DataFrame with edge & middle point coordinates, power flow direction angles for each line."""
    bus0_coordinates = get_bus_coordinates(n, 'bus0')
    bus1_coordinates = get_bus_coordinates(n, 'bus1')
    branch_info = pd.concat([bus0_coordinates, bus1_coordinates], axis='columns')

    branch_info['mid_x'], branch_info['mid_y'] = get_branch_midpoint(branch_info)

    branches = n.branches()
    # Capacities fall back to nominal when no expansion optimization ran
    s_nom = branches.s_nom_opt.where(branches.s_nom_opt > 0, branches.s_nom)
    p_nom = branches.p_nom_opt.where(branches.p_nom_opt > 0, branches.p_nom)
    # Lines have apparent power (s) set
    branch_info['p_max'] = branches.s_max_pu * s_nom
    # Links have real power (p) set
    branch_info['p_max'] = branch_info['p_max'].fillna(branches.p_max_pu * p_nom)

    branch_info['direction'], branch_info['inverse_direction'] = get_branch_direction(branch_info)

    return branch_info.pipe(BranchInfo.validate)


def to_branches_by_component_and_name(
        branches: pd.Series, component: str, quantity: str
) -> pd.DataFrame:
    """Indexes the given series by component (Link or Line) and branch name.
    """
    df = branches.rename(quantity).rename_axis('name').to_frame()
    df['component'] = component
    return df.set_index('component', append=True).reorder_levels(['component', 'name'])


def get_branch_info_for_snapshot(
        n: pypsa.Network, branch_info: DataFrame[BranchInfo], snapshot: pd.Timestamp
) -> DataFrame[BranchInfoForSnapshot]:
    lines_t_p0 = to_branches_by_component_and_name(n.lines_t.p0.loc[snapshot], 'Line', 'p0')
    links_t_p0 = to_branches_by_component_and_name(n.links_t.p0.loc[snapshot], 'Link', 'p0')
    transformers_t_p0 = to_branches_by_component_and_name(n.transformers_t.p0.loc[snapshot], 'Transformer', 'p0')
    branch_info_t = branch_info.join(pd.concat([lines_t_p0, links_t_p0, transformers_t_p0]))

    return branch_info_t.pipe(BranchInfoForSnapshot.validate)
