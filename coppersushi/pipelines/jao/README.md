# JAO market data

[Product pipelines](../README.md)

[`data_sources/publication.py`](data_sources/publication.py) retrieves JAO publications and caches validated tables. [`elements.py`](elements.py) converts published constraint records into tabular data. Critical Elements uses these tables for price attribution. Grid preparation uses the element endpoints for its location catalog.
