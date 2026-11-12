"""Extract browser data from the existing solved-network calculations."""
from typing import TYPE_CHECKING
import pandas as pd
from coppersushi.opf import power_flow
from coppersushi.opf.dataset import Branch, BranchValues, Dataset, Generation, Interval, Node, NodeValues
from coppersushi.opf.snapshot import NetworkSnapshot
if TYPE_CHECKING:
    import pypsa


def optional_number(value: float | None) -> float | None:
    return None if pd.isna(value) else float(value)


def extract(network: 'pypsa.Network') -> Dataset:
    """Reuse existing snapshot calculations; PyPSA's naive timestamps mean UTC."""
    geometry = power_flow.get_branch_info(network)
    topology = network.branches()
    nodes = [Node(id=str(name), longitude=row.x, latitude=row.y,
                  country=row.country, voltage_kv=row.v_nom)
             for name, row in network.buses.iterrows()]
    branches = [Branch(component=row.component, name=str(row['name']),
                       bus0=str(row.bus0), bus1=str(row.bus1),
                       capacity_mw=optional_number(row.p_max),
                       midpoint_longitude=row.mid_x, midpoint_latitude=row.mid_y,
                       forward_bearing=row.direction, reverse_bearing=row.inverse_direction)
                for _, row in geometry.join(topology[['bus0', 'bus1']]).reset_index().iterrows()]
    low, high = power_flow.get_interquartile_range(network.buses_t.p)
    intervals = []
    for timestamp in network.snapshots:
        snapshot = NetworkSnapshot(network, timestamp)
        flows = power_flow.get_branch_info_for_snapshot(network, geometry, timestamp)
        values = []
        for name, row in snapshot.buses.iterrows():
            generators = snapshot.generators[snapshot.generators.index.get_level_values(0) == name]
            values.append(NodeValues(node=str(name), net_power_mw=row.p,
                load_mw=optional_number(snapshot.loads.p_load.get(name)),
                generators=[Generation(technology=str(generator.carrier), power_mw=generator.p,
                                       available_mw=optional_number(generator.p_max))
                            for _, generator in generators.reset_index().iterrows()]))
        intervals.append(Interval(timestamp=pd.to_datetime(timestamp, utc=True).to_pydatetime(), nodes=values,
            branches=[BranchValues(component=row.component, name=str(row['name']), flow_mw=row.p0)
                      for _, row in flows.reset_index().iterrows()]))
    return Dataset(version=2, nodes=nodes, branches=branches, intervals=intervals,
                   net_power_scale_mw=max(abs(low), abs(high)) or 1.0)

