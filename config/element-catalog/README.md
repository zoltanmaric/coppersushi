# Physical-element catalog

Four CSVs form one snapshot: `sites`, `site_names`, `elements`, and
`element_endpoints`. `schema.sql` defines their columns and constraints. Empty cells
mean NULL. Names may identify multiple sites. A publication is identified by source,
publisher, EIC and name, preserving distinct Y-line legs with a shared EIC.

`element_catalog.load` validates all four tables in one in-memory SQLite transaction.
The CLI, CI and geometry projection share that loader. It rejects wrong headers,
duplicate keys, dangling references, invalid coordinates, invalid endpoint states,
and missing from/to rows. Site IDs are joined exactly; they are never name-matched.

```sh
python -m coppersushi.data_sources.element_catalog tests/fixtures/element-catalog
```

CI uses synthetic data. Real JAO-derived snapshots remain in ignored `data/`.
Relational integrity cannot prove geographic correctness. Unknown and conflicting
endpoints remain explicit. The tables describe a snapshot, not topology history.
