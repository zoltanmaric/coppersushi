# Grid catalog

[System overview](../../README.md) · [Catalog input schema](../../config/element-catalog/README.md)

Owns physical site and element identity, endpoint resolution and country outlines.
Its output is geographic evidence, independent of the price or rendering model.
External I/O lives in `data_sources/`; geometry matching transforms validated inputs.

```mermaid
flowchart LR
    sources["OSM and JAO source evidence"] --> compile["Catalog compilation"]
    reviewed["Reviewed mappings"] --> compile
    compile --> catalog[("Validated catalog tables")]
    catalog --> resolve["Element endpoint resolution"]
    resolve --> app["CNEC map inputs"]
    zones["Country geometry"] --> outlines["Bidding-zone outlines"]
    outlines --> app
```

`data_sources/element_catalog.py` loads and resolves the catalog;
`catalog_backfill.py` and `catalog_sweep.py` compile source evidence.
`cnec_geometry.py` implements matching; `bidding_zones.py` and `static_grid.py`
handle geography. Country preparation feeds the application build alongside
[OPF preparation](../powerflow/README.md).
