# CNEC browser

[System overview](../README.md) · [Publication contract](../coppersushi/publication/README.md)

A standalone React application constructs the map and calculates contributions
from prepared market-day files. Selection lives in the URL; query keys share
selected-interval and background requests. No interaction requests a Python figure.

```mermaid
flowchart LR
    files["Prepared publication"] --> data["Data loading and validation"]
    data --> market["Market arithmetic"]
    data --> map["Map rendering"]
    market --> map
    controls["URL and controls"] --> data
    controls --> map
    map -->|Selection intent| controls
    click data "https://github.com/zoltanmaric/coppersushi/blob/main/frontend/src/data/README.md" "Data component"
    click market "https://github.com/zoltanmaric/coppersushi/blob/main/frontend/src/market/README.md" "Market component"
    click map "https://github.com/zoltanmaric/coppersushi/blob/main/frontend/src/map/README.md" "Map component"
    click controls "https://github.com/zoltanmaric/coppersushi/blob/main/frontend/src/controls/README.md" "Controls component"
```

Components: [data](src/data/README.md), [market](src/market/README.md),
[map](src/map/README.md), [controls](src/controls/README.md).
`index.tsx` composes them; `bootstrap.tsx` validates configuration and loads the
basemap. Build with `npm ci && npm run build` in this directory.

## Static site

`index.html` owns the shell. `python -m frontend.publish --bucket <bucket>` embeds
the public Mapbox token and publishes built assets before the shell. It does not
import a web framework. The browser determines the current market date itself.
For local preview, `cnec_server.py` serves the same shell and `data/browser` files.
Production routing and rollback are in the [hosting runbook](../infra/lambda/README.md).
