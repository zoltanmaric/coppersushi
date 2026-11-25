# Market data

[Data pipelines](../README.md)

An **edition** is the validated price or border-spread table from one publisher response. For a delivery day and cutoff, the archive returns every eligible edition, including zero-row tables and earlier versions later corrected.

Suppose a response arrives at 10:58 and its edition reaches S3 at 11:04. An 11:00 replay returns nothing. An 11:05 replay returns that edition. If a correction reaches S3 at noon, a 12:01 replay returns both.

```mermaid
flowchart TB
    Publishers["Market publishers<br/>e.g. ENTSO-E, SMARD"]
    Runtime["Scheduled collector · AWS Lambda"] -->|Publisher, day and zones| Caller
    Runtime -->|Failed invocation record after retries| Alerts["Operator alerts · SNS"]
    Consumer["Price consumer"]
    subgraph Market["Market data · Python library"]
        Caller["Publisher collector"]
        Writer["Archive writer"]
        Resolver["Price resolver"]
    end
    Archive[("Private S3 archive")]
    Caller -->|Poll for delivery day| Publishers
    Publishers -->|HTTP response| Caller
    Caller -->|Publisher retry time| Archive
    Archive -->|Saved cooldown| Caller
    Caller -->|Response bytes, parsed rows or failure details| Writer
    Writer -->|Raw attempts, validated editions and diagnostics| Archive
    Consumer -->|Delivery day, zones, cutoff and source policy| Resolver
    Archive -->|Receipts, eligible editions and diagnostics| Resolver
    Resolver -->|Quarter-hour prices and evidence, or failure reasons| Consumer
```

The [collector](data_sources/collect_market_editions.py) checks the publisher’s saved cooldown before each request. An active cooldown defers the poll.

## Write and read an edition

1. Save the response with [`save_response`](data_sources/responses.py). It returns the receipt once the raw bytes are durable. A transport error goes through `save_failure`.
2. Parse the bytes held by the caller. Pass the receipt and rows to [`publish_edition`](data_sources/editions.py). It validates the [price or spread schema](edition_models.py) and writes one immutable Parquet object. A retry with identical evidence preserves the original publication time.

Use `read_editions(client, bucket, day, cutoff)` for the validated tables. S3 reports publication to the second, so the reader excludes objects written during the cutoff second.

## Inspect an attempt

[`read_response`](data_sources/responses.py) returns the receipt and exact archived bytes, including an empty body or an HTTP error page. A transport failure raises `NoResponseBody` with the recorded reason. A parse failure leaves the raw bytes available for inspection.

[`read_day_diagnostics`](data_sources/responses.py) returns failures recorded by cutoff. A raw receipt alone means the outcome is still unknown.

Each [publisher client](data_sources/collect_market_editions.py) handles one feed. An empty auction series records zero observations. A failed request retains its diagnostics. The collector stores a publisher’s retry time before reading the response body. If the body stalls, the failure receipt retains the HTTP status and safe headers. If a response echoes a credential, the collector redacts it and records a failure.

## Price selection

Pass a delivery day, zones, cutoff and source policy to [`resolve_day`](data_sources/prices.py). The [resolver](resolution.py) selects revisions per publisher and quarter. The reader checks the raw receipt’s publisher before opening a Parquet file for a policy. Full-day audits skip this receipt lookup and read every eligible edition. A row qualifies once its edition is available and its reported publisher update time, if present, has passed or equals the cutoff. A derived price becomes available with its last qualifying input. A correction to one quarter preserves earlier quotes for the others. Each selected price carries the policy ID, edition key and raw attempt ID for each contributing observation.

Critical Elements ⚡️ accepts Electricity Maps quotes. The free-source forecast excludes them, including as anchors for signed JAO border spreads. Disagreeing eligible direct quotes raise a conflict. If Electricity Maps and another eligible direct publisher agree for the same zone and quarter, the resolver accepts the direct price. If Electricity Maps is the only eligible direct publisher for that zone and quarter, the resolver checks its quote against prices implied by eligible anchors and spreads. A disagreement stops resolution with both evidence chains. A missing quarter carries the attempt IDs of eligible empty direct editions for its zone and its reachable anchors. Only when a quarter is missing does the resolver read the day’s failure diagnostics. It attaches direct-publisher failures in the requested zone or a zone reachable through eligible spreads that quarter. The day audit retains all failure diagnostics.
