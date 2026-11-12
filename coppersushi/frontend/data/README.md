# Publication loading

[Browser architecture](../README.md)

Validates the generated Python contract at entry. Shared query keys keep selected-interval and background loading on the same requests. Immutable generation URLs prevent mixed revisions.

```mermaid
flowchart LR
    manifest["Day manifest"] --> metadata["Shared metadata"]
    manifest --> intervals["Interval files"]
    metadata --> validation["Contract validation"]
    intervals --> validation
    validation --> cache["TanStack Query cache"]
```

[market](../pages/cnec/market/README.md) · [map](../map/README.md) · [controls](../controls/README.md)
