# OPF

[System overview](../../README.md) · [Domain model](../../wiki/sushi-2.md)

Owns solved-network loading, snapshot extraction, hourly figure preparation and
power-flow rendering. The static browser loads published hourly figures; local candidates render through Dash. External
I/O lives in `data_sources/`; the remaining modules transform in-memory values.

```mermaid
flowchart LR
    solver["PyPSA-Eur solve"] -->|Solved network| networks["Network loader"]
    networks --> snapshot["Typed snapshot"]
    snapshot --> figures["Plotly figure construction"]
    figures --> bundle["Hourly OPF bundle"]
    bundle --> publish["Versioned static publication"]
    publish --> browser["React and Plotly browser"]
```

`data_sources/pypsa_eur.py` runs and promotes solves; `networks.py` loads them.
`snapshot.py`, `shedding.py` and `power_flow.py` derive the view.
`data_sources/opf_bundle.py` prepares token-free hours and UTC timestamps.
`data_sources/publication.py` publishes immutable generations and their manifest to S3.
The [browser](../../frontend/README.md) loads selected hours through CloudFront.
Candidate solves remain local analysis through `app.py`; public page requests
neither load solved networks nor construct figures in Python.
