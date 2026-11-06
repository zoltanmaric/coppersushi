# Market arithmetic

[Browser architecture](../../README.md)

Pure signed contributions for physical constraints and country caps. The real-data reconciliation tests run here without importing Plotly or React.

```mermaid
flowchart LR
    interval["Validated interval"] --> contribution["Contribution calculation"]
    reference["Reference country"] --> contribution
    contribution --> values["Signed contributions by zone"]
```

[data](../data/README.md) · [map](../map/README.md) · [controls](../controls/README.md)
