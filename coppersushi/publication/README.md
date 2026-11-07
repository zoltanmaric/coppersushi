# Market-day publication

[System overview](../../README.md) · [Browser](../../frontend/README.md) · [Deployment](../../infra/lambda/README.md) · [Grid catalog](../grid_catalog/README.md)

Prepares complete market days as immutable browser data. JAO receipt evidence and
complete prices/context are required before the manifest exposes a generation.
There is no serving process in this component. `bundle.py` and `models.py` define
pure conversion and the wire contract; `data_sources/` owns fetching and writing.

```mermaid
flowchart TB
    schedule["15:50 Brussels scheduler"] --> workflow["Step Functions retry loop"]
    workflow -->|Scheduled timestamp| handler["Native Lambda handler"]
    handler --> ready
    sources["JAO and Electricity Maps"] --> ready["Receipt and completeness validation"]
    catalog["Grid catalog"] --> bundle["Typed complete-day bundle"]
    ready --> bundle
    bundle --> files["Immutable metadata and intervals"]
    files --> manifest["Atomic day manifest"]
    click catalog "https://github.com/zoltanmaric/coppersushi/blob/main/coppersushi/grid_catalog/README.md" "Grid catalog architecture"
```

Run `python -m coppersushi.publication.data_sources.bundles YYYY-MM-DD --directory data/browser`
for local files, or use `--bucket` to publish to S3. `--refresh` requests upstream
corrections. Publication rejects partial days; metadata and every interval are
written before the manifest. Old generations remain readable by in-flight clients.

`job.py` pins tomorrow's delivery day to the original scheduled instant. `handler.py`
validates the Lambda event; `data_sources/scheduled.py` makes one attempt. The
workflow waits two minutes between incomplete publications, for at most five hours.
A complete manifest skips re-publication. Unexpected errors remain visible failures.
The `publisher` image includes catalog inputs and outlines, without solved networks,
OPF figures or a web server. It uses AWS's official Runtime Interface Client.
