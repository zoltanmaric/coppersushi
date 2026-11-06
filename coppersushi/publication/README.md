# Market-day publication

[System overview](../../README.md) · [Grid catalog](../grid_catalog/README.md)

Prepares complete market days as immutable browser data. JAO receipt evidence and
complete prices/context are required before the manifest exposes a generation.
There is no serving process in this component. `bundle.py` and `models.py` define
pure conversion and the wire contract; `data_sources/` owns fetching and writing.

```mermaid
flowchart LR
    sources["JAO and Electricity Maps"] --> ready["Receipt and completeness validation"]
    catalog["Grid catalog"] --> bundle["Typed complete-day bundle"]
    ready --> bundle
    bundle --> files["Immutable metadata and intervals"]
    files --> manifest["Atomic day manifest"]
    click catalog "../grid_catalog/README.md" "Grid catalog architecture"
```

Run `python -m coppersushi.publication.data_sources.bundles YYYY-MM-DD --directory data/browser`
for local files, or use `--bucket` to publish to S3. `--refresh` requests upstream
corrections. Publication rejects partial days; metadata and every interval are
written before the manifest. Old generations remain readable by in-flight clients.
