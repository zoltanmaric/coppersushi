"""Pandera schemas for the JAO element → network branch resolution `elements.py` performs.

JAO names an element's two ends and its type; `data_model/substations.py` has already turned
each name into a bus. What is left is the component itself — which `Line` or `Transformer` of
our network the element *is* — and that is what these tables carry, one row per element rather
than per hour and direction: the limit varies through the day, the component does not.

`strict = False` throughout, matching `data_model/jao.py`.
"""

import pandera.pandas as pa
from pandera.typing import Series


class Overrides(pa.DataFrameModel):
    """Hand-made element → branch matches, one per EIC, that win over anything computed."""

    eic: Series[str] = pa.Field(unique=True)  # As JAO publishes it
    branch_id: Series[str]  # The component's name in the network; must exist there
    branch_type: Series[str]  # Line or Transformer
    note: Series[str]  # Why the match needed a human


    class Config:
        strict = False
        coerce = True


class ElementMatches(pa.DataFrameModel):
    """One row per JAO element EIC, resolved to a branch of the network or not.

    An unresolved element keeps its row — coverage needs the denominator — with the branch
    columns null and `bus_source` empty.
    """

    eic: Series[str] = pa.Field(unique=True)
    name: Series[str]  # The TSO's name for the element, as JAO publishes it
    element_type: Series[str]  # JAO's: Line, TieLine, Transformer, PST, or "" where it published none
    branch_id: Series[str] = pa.Field(nullable=True)  # The component's name in the network
    branch_type: Series[str]  # Line or Transformer: the component we looked for, set even when none was found
    bus0: Series[str] = pa.Field(nullable=True)
    bus1: Series[str] = pa.Field(nullable=True)
    match_status: Series[str]  # matched, no_substation, no_branch or no_component_in_network
    bus_source: Series[str]  # exact, nearest, or "" where no branch was found
    score: Series[float]  # The weaker of the two substation matches' scores

    class Config:
        strict = False
        coerce = True


class ContingencyMatches(pa.DataFrameModel):
    """One row per (monitored element, contingency, branch of ours the outage lands on).

    `circuits_out` is the number of JAO branches in that contingency resolving to the one
    branch of ours. Our network folds parallel circuits into a single line, so a contingency
    naming two of three circuits is not that line out: it is a reactance change, and the
    factor computing it needs the count.
    """

    eic: Series[str]  # EIC of the monitored element, not of the outaged branch
    cont_name: Series[str]  # JAO's free-text name for the whole contingency
    branch_name: Series[str]  # The outaged branches' JAO names, "; "-joined where several fold onto one
    branch_id: Series[str] = pa.Field(nullable=True)
    branch_type: Series[str]
    bus0: Series[str] = pa.Field(nullable=True)
    bus1: Series[str] = pa.Field(nullable=True)
    match_status: Series[str]
    bus_source: Series[str]
    circuits_out: Series[int]  # JAO branches of this contingency landing on `branch_id`
    score: Series[float]

    class Config:
        strict = False
        coerce = True
