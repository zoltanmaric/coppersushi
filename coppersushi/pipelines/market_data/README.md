# Market data

[Data pipelines](../README.md)

An **edition** is the validated price or border-spread table from one publisher response. For a delivery day and cutoff, the archive returns every eligible edition, including zero-row tables and earlier versions later corrected.

Suppose a response arrives at 10:58 and its edition reaches S3 at 11:04. An 11:00 replay returns nothing. An 11:05 replay returns that edition. If a correction reaches S3 at noon, a 12:01 replay returns both.

```mermaid
flowchart TD
    Caller["Caller with publisher response or transport error"]
    Caller -->|First write: bytes or failure reason| Raw["Raw attempt in S3"]
    Caller -->|After raw save: receipt and parsed rows| Writer["Validate and publish"]
    Writer -->|One conditional PUT| Table["Edition in S3 · Parquet"]
    Caller -->|Record a diagnosed failure| Fail["Diagnostic in S3"]
    Table -->|Day and cutoff| Read["Read eligible editions"]
    Raw -->|Check publisher for policy reads| Read
    Fail -->|Day and cutoff| Audit["Read failure diagnostics"]
    Read -->|Editions and source policy| Resolve["Resolve a price per quarter"]
    Audit -->|Explain missing quarters| Resolve
```

## Write and read an edition

1. Save the response with [`save_response`](data_sources/responses.py). It returns the receipt once the raw bytes are durable. A transport error goes through `save_failure`.
2. Parse the bytes held by the caller. Pass the receipt and rows to [`publish_edition`](data_sources/editions.py). It validates the [price or spread schema](edition_models.py) and writes one immutable Parquet object. A retry with identical evidence preserves the original publication time.

Use `read_editions(client, bucket, day, cutoff)` for the validated tables. S3 reports publication to the second, so the reader excludes objects written during the cutoff second.

## Inspect an attempt

[`read_response`](data_sources/responses.py) returns the receipt and exact archived bytes, including an empty body or an HTTP error page. A transport failure raises `NoResponseBody` with the recorded reason. A parse failure leaves the raw bytes available for inspection.

[`read_day_diagnostics`](data_sources/responses.py) returns failures recorded by cutoff. A raw receipt alone means the outcome is still unknown.

## Price selection

Pass a delivery day, zones, cutoff and source policy to [`resolve_day`](data_sources/prices.py). The [resolver](resolution.py) selects revisions per publisher and quarter. The reader checks the raw receipt’s publisher before opening a Parquet file for a policy. Full-day audits skip this receipt lookup and read every eligible edition. A row qualifies once its edition is available and its reported publisher update time, if present, has passed or equals the cutoff. A derived price becomes available with its last qualifying input. A correction to one quarter preserves earlier quotes for the others. Each selected price carries the policy ID, edition key and raw attempt ID for each contributing observation.

Critical Elements ⚡️ accepts Electricity Maps quotes. The free-source forecast excludes them, including as anchors for signed JAO border spreads. Disagreeing eligible direct quotes raise a conflict. If Electricity Maps and another eligible direct publisher agree for the same zone and quarter, the resolver accepts the direct price. If Electricity Maps is the only eligible direct publisher for that zone and quarter, the resolver checks its quote against prices implied by eligible anchors and spreads. A disagreement stops resolution with both evidence chains. For a missing quarter, the resolver attaches direct-publisher failures in the requested zone or a zone reachable through eligible spreads that quarter. The day audit retains all failure diagnostics.
