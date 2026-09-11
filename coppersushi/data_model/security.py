"""Pandera schemas for the outage sensitivities `security.py` computes.

`Outages` names branches to take out; `OutageFactors` says what that does to every other
branch. Both carry a branch as the (type, name) pair `data_model/elements.py` resolves to, so
a subset of `ContingencyMatches` validates as `Outages` directly.

`strict = False` throughout, matching `data_model/jao.py`.
"""

import pandera.pandas as pa
from pandera.typing import Series


class Outages(pa.DataFrameModel):
    """One row per branch of ours to take out, and how much of it goes."""

    branch_type: Series[str]  # Line or Transformer
    branch_id: Series[str]  # The component's name in the network
    circuits_out: Series[int]  # Circuits removed; at or above `num_parallel` the branch is out

    class Config:
        strict = False
        coerce = True


class OutageFactors(pa.DataFrameModel):
    """One row per (outaged branch, branch it moves): the fraction of flow that transfers.

    `factor` is the LODF: the outaged branch's pre-outage flow times `factor` is the change in
    the affected branch's flow. Only branches sharing the outaged branch's sub-network get a
    row — everywhere else the factor is zero by construction.
    """

    outaged_type: Series[str]
    outaged_id: Series[str]
    circuits_out: Series[int]
    branch_type: Series[str]
    branch_id: Series[str]
    factor: Series[float]

    class Config:
        strict = False
        coerce = True
