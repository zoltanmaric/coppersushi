# Physical-element catalog

Four CSVs form one snapshot: `sites`, `site_names`, `elements`, and
`element_endpoints`. `schema.sql` defines their columns and constraints. Empty CSV
cells mean NULL. Names may identify several sites; an element's publisher and name
remain part of its identity because one EIC can identify several Y-line legs.

`element_catalog.load` validates the complete snapshot in an in-memory SQLite
transaction before exposing it. The CLI, CI and map projection use this loader.
It rejects wrong headers, duplicate keys, dangling references, invalid coordinates,
invalid resolution states and missing from/to rows. Integrity does not prove that a
chosen site is geographically correct. The audit retains unresolved and conflicting
source records instead of inventing connections.

## Build and validate

The input cache contains the OSM locator, `osm-prebuilt-v0.7/buses.csv`, JAO endpoint
and domain CSVs, and retained annual `activeFbConstraints` responses. Backfill reads
all physical domain rows, including non-presolved rows. It requests at most one
representative hour per still-missing identity in each pass, with a request budget.
Run long backfills under the project's job-supervision procedure.

```sh
python -m coppersushi.data_sources.catalog_backfill --cache-root data --output data/research/element-catalog --max-requests 40 --fetch-osm
python -m coppersushi.data_sources.catalog_sweep --cache-root data --backfill data/research/element-catalog --output data/element-catalog
python -m coppersushi.data_sources.element_catalog data/element-catalog
```

The sweep also writes coverage, contingency references, source hashes and a summary.
Constraint appearances are deduplicated by UTC timestamp and source row ID. Country
limits and other nonphysical constraints are counted separately; virtual hubs are
not catalog entities. Contingency references do not become guessed physical elements.

Real JAO-derived CSVs remain ignored, as do locator-derived coordinates. CI validates
synthetic fixtures through the same schema. `osm-sites.csv` identifies reviewed OSM
supplements; their tags must be retained and their coordinates present in the cached
OSM bus data. OSM data is © OpenStreetMap contributors, available under
[ODbL](https://www.openstreetmap.org/copyright). `endpoint-bindings.csv` records
reviewed element-specific site selections; the compiler rejects absent target sites.

Site IDs are assigned once from source anchors, then retained by the existing
snapshot's name/location bindings. Rebuilding in the same directory preserves them
across small coordinate corrections. Element IDs encode the exact publisher/name
identity; source renames remain distinct publications. Do not use IDs as display names.

The compiler writes an immutable generation directory and atomically switches
`current`; the loader pins that directory before reading any table. The four CSV
links at the root are for browsing. Readers must use the loader to avoid mixing
versions. Old generations remain available to in-flight readers.

The four tables describe a snapshot, not a history of topology. Conflicting endpoint
publications remain unresolved across that snapshot. Source renames create distinct
element publications; they do not silently rename a physical site or merge Y-line legs.
Overrides include the full element publication name and endpoint label.

## Serve

The app defaults to `data/element-catalog`; set `COPPERSUSHI_ELEMENT_CATALOG` to
select another snapshot. Known publications use validated site connections.
New identities and publications missing endpoint metadata use the viewed-hour JAO
fetch and live locator. Recorded conflicts, ambiguous sites and unresolved site names
remain authoritative. Discovery does not overwrite the reviewed snapshot; rebuild it
to audit and incorporate new observations. A missing or invalid catalog is an error.
The image build validates it before shipping.
