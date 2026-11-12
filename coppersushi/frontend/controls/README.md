# Selection and controls

[Browser architecture](../../README.md)

A pure reducer handles intent; URL parsing validates deep links. History replacement keeps interval browsing from flooding browser history. Controls describe the requested view while pending data remains visible.

```mermaid
flowchart LR
    url["URL"] --> selection["Validated selection"]
    gestures["Date, time and reference controls"] --> reducer["Selection reducer"]
    selection --> reducer
    reducer -->|replace| url
```

[market](../market/README.md) · [data](../data/README.md) · [map](../map/README.md)
