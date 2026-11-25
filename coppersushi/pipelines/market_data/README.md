# Market data

[Data pipelines](../README.md)

What did the publisher return, and when did we receive it? For each day-ahead
price request, this package saves the response bytes and their arrival time, or
the reason the request failed. Look up a poll by its attempt ID with
[`read_attempt`](data_sources/poll_receipts.py). A price can still be awaiting
validation at the forecast deadline even though its response has arrived.

## Poll storage

Each poll occupies one immutable object in private S3. `save_response` stores
the bytes, including empty and HTTP error bodies, and returns their checksum in
the receipt. `save_failure` records a transport failure and its redacted reason.
Retry an interrupted write with the same attempt ID and evidence. A new request
gets a new ID even when the publisher returns identical bytes.

```mermaid
flowchart LR
    Poll["Publisher poll"] -->|Response bytes or failure detail + receipt metadata| Receipt["One immutable S3 object per attempt"]
```
