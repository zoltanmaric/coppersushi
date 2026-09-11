"""Line Outage Distribution Factors: what one branch going out does to every other.

N-1 security is the rule that no single outage may overload anything. Stated as a blanket
30% headroom it is a guess; stated as LODFs it is arithmetic — if branch `l` is switched off,
the fraction of its flow that appears on branch `k` is `LODF_kl`, and the constraint on `k` is
`|f_k + LODF_kl · f_l| ≤ rating_k`, one inequality per (monitored branch, contingency).

Three things shape how it is computed here:

1. **By column, not by matrix.** PyPSA's `calculate_BODF` inverts the whole susceptance matrix
   and forms a dense branch × branch array. Contingency lists name a few dozen branches out of
   thousands, so this takes one sparse solve per outaged branch instead:
   `PTDF_branch[:, l] = H · B⁻¹ · K[:, l]`. The slack handling mirrors `calculate_PTDF`
   exactly — `B` with its first row and column struck out, the solution padded back with a
   zero at the slack — because the two must agree to the last bit, and they do.

2. **A bridge has no factor at all.** Take out a branch whose removal disconnects the network
   and every unit of its flow has nowhere to go: `d = 1`, `1 − d = 0`, and the factor is
   infinite. PyPSA's `BODF` emits `NaN` down that column. Bridges are found topologically,
   before any arithmetic, and excluded — a radial line's outage is load shedding, not a
   redistribution, and belongs to a different constraint. `bridges` names them so a caller can
   report what was dropped.

3. **A partial outage is not an outage.** Our network folds a corridor's parallel circuits
   into one component, so a contingency naming two of three circuits is a reactance change,
   not a removal. With `s = circuits_out / num_parallel` the factor is `s·p / (1 − s·d)`,
   which is the full formula at `s = 1` and is finite on a bridge for any `s < 1` — losing one
   of two circuits disconnects nobody.

Design: `wiki/specs/jao-grid.md`.
"""

import logging

import networkx as nx
import numpy as np
import pandas as pd
import pypsa
from pandera.typing import DataFrame
from scipy.sparse import csc_matrix
from scipy.sparse.linalg import spsolve

from coppersushi.data_model.security import OutageFactors, Outages

logger = logging.getLogger(__name__)

FACTOR_COLUMNS = ["outaged_type", "outaged_id", "circuits_out", "branch_type", "branch_id", "factor"]

SELF_FACTOR = -1.0  # a branch fully out carries none of its own flow, as `BODF`'s diagonal says


def _prepare(n: pypsa.Network) -> None:
    """Give every sub-network the `B`, `H` and `K` matrices the factors are built from.

    This mutates `n` the way PyPSA's own power-flow calls do — it fills in dependent values,
    bus controls and the susceptance matrices — and touches nothing outside the network.
    """
    n.determine_network_topology()
    for sub_network in n.sub_networks.obj:
        sub_network.calculate_B_H()


def _branch_column(sub_network, position: int) -> np.ndarray:
    """`H · B⁻¹ · K[:, position]`: how a unit transfer across one branch loads all of them.

    The slack is `buses_o[0]`, so `B` loses its first row and column before the solve and the
    solution is padded with a zero back in its place — `calculate_PTDF`'s handling, which this
    has to match exactly.
    """
    incidence = np.asarray(sub_network.K[:, position].todense()).ravel()
    solved = spsolve(csc_matrix(sub_network.B[1:, 1:]), incidence[1:])
    angles = np.concatenate([[0.0], np.atleast_1d(solved)])
    return np.asarray(sub_network.H @ angles).ravel()


def bridges(n: pypsa.Network) -> set[tuple[str, str]]:
    """The branches as (type, name) whose removal would split the network into two.

    Topological, so `num_parallel` does not enter: a component of two parallel circuits is one
    edge of the graph, and taking the whole component out disconnects whatever hangs off it.
    A partial outage of such a component is not a removal and stays computable.
    """
    graph = nx.MultiGraph()
    graph.add_nodes_from(n.buses.index)
    for branch_type, static in (("Line", n.lines), ("Transformer", n.transformers)):
        for branch_id, branch in static.iterrows():
            graph.add_edge(branch.bus0, branch.bus1, key=(branch_type, branch_id))
    # A bridge has no parallel edge by definition, so each one names exactly one branch.
    return {key for bus0, bus1 in nx.bridges(graph) for key in graph[bus0][bus1]}


def lodf(n: pypsa.Network, outages: DataFrame[Outages]) -> DataFrame[OutageFactors]:
    """One row per (outaged branch, branch it moves) with the fraction of flow that transfers.

    Outages of a bridge are dropped rather than returned as infinities; `bridges` says which.
    Branches outside the outaged branch's sub-network are left out, their factor being zero.
    """
    _prepare(n)
    spanning = bridges(n)
    parallel = {
        (branch_type, branch_id): circuits
        for branch_type, static in (("Line", n.lines), ("Transformer", n.transformers))
        for branch_id, circuits in static.num_parallel.items()
    }

    rows = []
    dropped = []
    for sub_network in n.sub_networks.obj:
        branches = list(sub_network.branches_i())
        if len(branches) != sub_network.K.shape[1]:
            # `calculate_B_H` builds K from the *active* branches only; a mismatch would
            # silently shift every column onto the wrong branch.
            raise ValueError(f"sub-network {sub_network.name} has inactive branches; K does not line up")
        positions = {branch: position for position, branch in enumerate(branches)}
        for outage in outages.itertuples():
            branch = (outage.branch_type, outage.branch_id)
            if branch not in positions:
                continue
            circuits = parallel[branch]
            share = min(outage.circuits_out / circuits, 1.0) if circuits > 0 else 1.0
            if share >= 1.0 and branch in spanning:
                dropped.append(outage.branch_id)
                continue
            position = positions[branch]
            column = _branch_column(sub_network, position)
            factors = share * column / (1.0 - share * column[position])
            if share >= 1.0:
                factors[position] = SELF_FACTOR
            rows.extend(
                {
                    "outaged_type": outage.branch_type,
                    "outaged_id": outage.branch_id,
                    "circuits_out": outage.circuits_out,
                    "branch_type": branch_type,
                    "branch_id": branch_id,
                    "factor": factor,
                }
                for (branch_type, branch_id), factor in zip(branches, factors)
            )
    if dropped:
        logger.info("%d outages dropped as bridges: %s", len(dropped), ", ".join(sorted(set(dropped))))
    return pd.DataFrame(rows, columns=FACTOR_COLUMNS).pipe(OutageFactors.validate)
