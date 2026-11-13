"""Data-only Power Flow contract, independent of plotting and delivery."""
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, model_validator

Finite = Annotated[float, Field(allow_inf_nan=False)]


class Contract(BaseModel):
    """Reject unknown fields and non-finite numeric input at publication boundaries."""
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class Node(Contract):
    """A network bus; coordinates are WGS84 degrees and voltage is kV."""
    id: str
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    country: str
    voltage_kv: Finite = Field(gt=0)


class Branch(Contract):
    """A physical branch, identified by component and name, oriented bus0 to bus1."""
    component: Literal['Line', 'Link', 'Transformer']
    name: str
    bus0: str
    bus1: str
    capacity_mw: Finite | None = Field(ge=0)
    midpoint_longitude: float = Field(ge=-180, le=180)
    midpoint_latitude: float = Field(ge=-90, le=90)
    forward_bearing: Finite
    reverse_bearing: Finite


class Generation(Contract):
    """A generator's technology, output and available capacity, in MW."""
    technology: str
    power_mw: Finite
    available_mw: Finite | None


class NodeValues(Contract):
    """One bus's power and tooltip inputs; absent load is distinct from zero."""
    node: str
    net_power_mw: Finite
    load_mw: Finite | None
    generators: list[Generation]


class BranchValues(Contract):
    """Signed bus0-end active flow in MW; positive means bus0 to bus1."""
    component: Literal['Line', 'Link', 'Transformer']
    name: str
    flow_mw: Finite


class Interval(Contract):
    """Complete network values at one timezone-aware solved snapshot."""
    timestamp: AwareDatetime
    nodes: list[NodeValues]
    branches: list[BranchValues]


class Dataset(Contract):
    """Validated producer-side dataset; null denotes unavailable optional values."""
    version: Literal[2]
    nodes: list[Node] = Field(min_length=1)
    branches: list[Branch]
    intervals: list[Interval] = Field(min_length=1)

    @model_validator(mode='after')
    def validate_network(self) -> Self:
        node_ids = [node.id for node in self.nodes]
        branch_ids = [(branch.component, branch.name) for branch in self.branches]
        if len(set(node_ids)) != len(node_ids) or len(set(branch_ids)) != len(branch_ids):
            raise ValueError('Duplicate node or branch identity')
        node_set = set(node_ids)
        if any(branch.bus0 not in node_set or branch.bus1 not in node_set for branch in self.branches):
            raise ValueError('Branch endpoint does not exist')
        previous: datetime | None = None
        for interval in self.intervals:
            if previous is not None and interval.timestamp <= previous:
                raise ValueError('Snapshots must be strictly increasing')
            previous = interval.timestamp
            nodes = [node.node for node in interval.nodes]
            branches = [(branch.component, branch.name) for branch in interval.branches]
            if len(nodes) != len(node_ids) or set(nodes) != set(node_ids):
                raise ValueError('Interval must contain each node exactly once')
            if len(branches) != len(branch_ids) or set(branches) != set(branch_ids):
                raise ValueError('Interval must contain each branch exactly once')
        return self
