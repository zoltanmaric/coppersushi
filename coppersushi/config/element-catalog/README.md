# Physical-element catalog

Four CSVs form one snapshot: `sites`, `site_names`, `elements`, and
`element_endpoints`. `schema.sql` defines their columns and constraints. Empty CSV
cells mean NULL. Names may identify several sites; an element's publisher and name
remain part of its identity because one EIC can identify several Y-line legs.

`element_catalog.load` validates the complete snapshot in an in-memory SQLite
transaction before exposing it. The CLI, CI and map projection use this loader.
It rejects wrong headers, duplicate keys, dangling references, invalid coordinates,
invalid resolution states and missing A/B terminal rows. Integrity does not prove that a
chosen site is geographically correct. The audit retains unresolved and conflicting
source records instead of inventing connections.

## Build and validate

For a new developer checkout or deployment build context, run
`pixi run --locked setup-app` from the repository root. It installs the environment
and prepares all required tables. Reuse cached inputs with `pixi run --locked setup-data`;
check readiness offline with `pixi run --locked check-data`. The commands below extend
the catalog with research observations; they are not prerequisites for local startup.

The input cache contains the OSM locator, `osm-prebuilt-v0.7/buses.csv`, JAO endpoint
and domain CSVs, and retained annual `activeFbConstraints` responses. Backfill reads
all physical domain rows, including non-presolved rows. It requests at most one
representative hour per still-missing identity in each pass, with a request budget.
Run long backfills under the project's job-supervision procedure.

```sh
python -m coppersushi.pipelines.grid.data_sources.catalog_backfill --cache-root data --output data/research/element-catalog --max-requests 40 --fetch-osm
python -m coppersushi.pipelines.grid.data_sources.catalog_sweep --cache-root data --backfill data/research/element-catalog --output data/element-catalog
python -m coppersushi.pipelines.grid.data_sources.element_catalog data/element-catalog
```

The sweep also writes coverage, contingency references, source hashes and a summary.
Constraint appearances are deduplicated by UTC timestamp and source row ID. Country
limits and other nonphysical constraints are counted separately; virtual hubs are
not catalog entities. Contingency references do not become guessed physical elements.

Bulk JAO endpoint tables and generated catalog snapshots remain ignored, as do
locator-derived coordinates. Reviewed project mappings in this directory and the
substation alias files are tracked inputs. Reviewed element assessments seed their
own identities even when the bootstrap day did not publish them; their inferred
basis and evidence remain explicit. CI validates
synthetic fixtures through the same schema. `osm-sites.csv` identifies reviewed OSM
supplements by object type and ID; their tags must be retained. Coordinates come from the cached OSM bus data,
or from the centroid of a retained complete, valid substation polygon when that
older cache lacks the site. A substation site relation uses the union of its
complete, closed member boundaries. Way and relation IDs occupy separate namespaces. Partial geometry and non-substation objects are rejected. OSM data is © OpenStreetMap contributors, available under
[ODbL](https://www.openstreetmap.org/copyright). `endpoint-bindings.csv` records
reviewed element-specific site selections; the compiler rejects absent target sites.

Site IDs are assigned once from source anchors, then retained by the existing
snapshot's name/location bindings. Rebuilding in the same directory preserves them
across small coordinate corrections. An invalid prior catalog is rebuilt from inputs;
only a fully validated prior snapshot contributes retained IDs or source hashes. Element IDs encode the exact publisher/name
identity; source renames remain distinct publications. Do not use IDs as display names.

The compiler writes an immutable generation directory and atomically switches
`current`; the loader pins that directory before reading any table. The four CSV
links at the root are for browsing. Readers must use the loader to avoid mixing
versions. Old generations remain available to in-flight readers.

The four tables describe a snapshot, not a history of topology. Conflicting endpoint
publications remain unresolved across that snapshot. Source renames create distinct
element publications; they do not silently rename a physical site or merge Y-line legs.
Overrides include the full element publication name and endpoint label.
The audit reports `orientation_unknown` when both sites are resolved but DIRECT is
unknown. Such rows count as unmapped because the directed map cannot draw them.

Static-grid terminal pairs do not by themselves establish a runtime publication's
DIRECT orientation. Automatic joins must never transfer endpoints using EIC alone.
Reviewed hypotheses may select a pair for an exact publication, with the discrepancy
and evidence recorded explicitly in `element-assessments.csv`.

## Serve

The app defaults to `data/element-catalog`; set `COPPERSUSHI_ELEMENT_CATALOG` to
select another snapshot. Known publications use validated site connections.
New identities and publications missing endpoint metadata use the viewed-hour JAO
fetch and live locator. Recorded conflicts, ambiguous sites and unresolved site names
remain authoritative. Discovery does not overwrite the reviewed snapshot; rebuild it
to audit and incorporate new observations. If endpoint discovery fails or returns a
partial response, the map keeps known locations and leaves only unresolved rows
unmapped. Partial discoveries do not create a complete-hour cache entry, so later
requests can retry. Conflicting endpoint pairs are skipped per publication. A missing or invalid catalog is an error.
The image build validates it before shipping.

## Assessments

Terminals A/B identify the two ends without implying DIRECT. `assignment_basis`
records whether each site assignment is published, inferred or unknown, independently
of its resolution status. A unique resolved site can still be an inferred assignment.
`published_name` retains the original source label and stays empty when none was
published; a hypothesis never fabricates a publisher label.

Each element has `direct_orientation` (`a_to_b`, `b_to_a`, `unknown`),
`orientation_basis` and separate evidence. Unknown orientation is not projected into
the existing directed map contract. Chosen inferred mappings render normally; these
fields are internal provenance and do not add map labels or styling. DIRECT/OPPOSITE
on an active constraint remains the publisher's observation.

`assessed-sites.csv` adds reviewed coordinates for physical terminals absent from the
locator, including real junctions; these are not virtual trading hubs.
`element-assessments.csv` selects sites by unique display name for an exact TSO/EIC/name
publication. All selections in that file are explicitly inferred. Source conflicts
and contradictory complete published mappings fail the build for review. Ordinary
name-to-site lookup is also classified as inferred; published orientation comes from
unambiguous source from/to labels. Assessments preserve the original source labels
and retain observation provenance. Neither source order nor a numeric similarity is
a calibrated confidence probability.

Existing from/to snapshots are read through an explicit legacy-header conversion,
validated against the current relational schema, and rebuilt with A/B columns. Site
and element IDs remain stable. These four tables still describe a snapshot, not
historical validity: evidence dates do not establish validity for every historical
hour. The seven provisional assessments document that limitation in their evidence.

## Sources and educational use

Copper Sushi uses JAO observations and its reviewed mappings to explain electricity
market constraints in a free, noncommercial educational project. This is the
project’s interpretation of Legitimate Use under [JAO’s terms](https://www.jao.eu/terms-conditions),
not written authorization or an open licence for JAO data. Source values and inferred
assignments retain separate provenance. Bulk observations are rebuilt locally.

The downloaded [core-tso-data](https://github.com/fneum/core-tso-data#license) locator
has MIT-licensed code but no stated data licence; it remains ignored. Replacing it
with directly sourced OSM data is deferred. The pinned
[PyPSA-Eur OSM buses v0.7](https://zenodo.org/records/18619025) and direct OSM
geometry are © OpenStreetMap contributors under ODbL. These upstream terms also
apply to derived data; the project does not relicense upstream content.
