# OPF

[System overview](../../README.md) · [Domain model](../../wiki/sushi-2.md)

Owns solved-network loading, snapshot extraction, hourly figure preparation and
power-flow rendering. The root Dash application serves these figures. External
I/O lives in `data_sources/`; the remaining modules transform in-memory values.

```mermaid
flowchart LR
    solver["PyPSA-Eur solve"] -->|Solved network| networks["Network loader"]
    networks --> snapshot["Typed snapshot"]
    snapshot --> figures["Plotly figure construction"]
    figures --> bundle["Hourly OPF bundle"]
    bundle --> server["Dash application"]
    bundle --> publish["Versioned static publication"]
    publish --> browser["Static OPF browser preview"]
```

`data_sources/pypsa_eur.py` runs and promotes solves; `networks.py` loads them.
`snapshot.py`, `shedding.py` and `power_flow.py` derive the view.
`data_sources/opf_bundle.py` prepares the serving bundle. Its image contains only this precomputed data; OPF startup does not load or validate
the [grid catalog](../grid_catalog/README.md).

`frontend/opf_data.py` publishes the same token-free hours and a timestamp manifest.
The standalone [browser](../../frontend/README.md) consumes these files without Dash.
