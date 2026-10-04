# Copper Sushi 🍣
## A Power System Analysis and Visualisation Tool
[![](assets/coppersushi-gif.gif)](https://121gigawatts.org/copper-sushi-power-flow-european-grid/)

A simple Plotly/Dash web app for visualising power flow optimisation
solutions  from [`pypsa-eur`](https://github.com/PyPSA/pypsa-eur).

The web app is deployed
[**here**](https://121gigawatts.org/copper-sushi-power-flow-european-grid/),
along with an explanation of the main features.

v1's network `networks/opf-2013-07-17-v1.nc` is a solved PyPSA-Eur 0.5.0 optimal power flow (one day, 2013-07-17, 2-hour snapshots,
lines expandable to 1.01× current volume). The exact configuration that
produced it is tagged
[`coppersushi-v1`](https://github.com/zoltanmaric/pypsa-eur/tree/coppersushi-v1)
in my fork of `pypsa-eur`; see its `config.yaml` and README.

Networks are versioned with [Git LFS](https://git-lfs.com). Install `git-lfs` system-wide (`brew install git-lfs`)
so git works from any shell or IDE, run `git lfs install` once to register the filters that turn pointers into
files, then `git lfs pull`. The conda environment ships `git-lfs` too, for shells without it.
Clone with `GIT_LFS_SKIP_SMUDGE=1` to skip the files, e.g. to run only the tests.

## Working with Agents
The repository is developed with coding agents (Claude Code and Codex), and the tooling for that is
part of the repository:

- [`AGENTS.md`](AGENTS.md) holds the rules the agents follow here. Every directory with rules of its own
  has one.
- [`.agents/skills/`](.agents/skills/) holds the skills those rules invoke.
- [`wiki/`](wiki/) is an LLM-maintained wiki of domain knowledge, design decisions and specs.

## Local Installation
Installing the dependencies requires Conda, but I recommend installing
[`Mamba`](https://mamba.readthedocs.io/en/latest/installation.html)
(a fully compatible, but better implementation of Conda).

After having installed `mamba`, just create and activate the Conda
environment by running
```bash
conda env create -f environment.yml
conda activate coppersushi
```

### Mapbox Token
A Mapbox access token is required to run the app. Tokenless startup is unsupported.
Register for a free token at [mapbox.com](https://www.mapbox.com/), then paste it into
`.secrets/.mapbox_token`, or export it as `MAPBOX_TOKEN`.

Then you can start the server by running
```bash
python app.py
```

Once the server starts, the web app will be available at http://localhost:8050

### Market Data

The CNEC view uses JAO's public active flow-based constraints and Electricity Maps' published day-ahead
prices. Put an Electricity Maps key in `.secrets/.electricity_maps_api_key`, or export
`ELECTRICITY_MAPS_API_KEY`. Fetch one delivery day into the gitignored local cache with:

```bash
python -m coppersushi.data_sources.jao fetch-active 2026-09-11
python -m coppersushi.data_sources.electricity_maps fetch 2026-09-11
```

The map places JAO's elements by their published substation names on the OSM-locator substation
list in [core-tso-data](https://github.com/fneum/core-tso-data), which is unlicensed and therefore
fetched locally rather than committed. Fetch it once, plus at least one day's final domain, which
names each element's substations:

```bash
python -m coppersushi.data_sources.osm_locator fetch
python -m coppersushi.data_sources.jao fetch 2026-09-11
python -m coppersushi.data_sources.jao seed 2026-09-11
```

The seed command validates the fetched domain day and writes `data/jao/element-ends.csv`.
Supply several fetched days to combine their coverage; the latest day's endpoints win.
The page reuses these endpoints across delivery days. If the viewed hour needs an element absent
from the cache, it shows the loading indicator while fetching that hour and saves the additions.
Failed fetches show an error: use **Retry** to try again, without restarting the server.
An element whose endpoints are known but whose substations cannot be located remains explicitly
unmapped; downloading the same endpoints again would not locate it.

## Running the Tests
```bash
pytest
```
The tests run against small checked-in fixtures under `tests/fixtures/`, never against the
networks. Tests require no Mapbox token; they build figures without fetching map tiles.

## Solving a day with PyPSA-Eur
The networks in `networks/` are produced by [PyPSA-Eur](https://github.com/PyPSA/pypsa-eur),
run from a **sibling checkout** at `../pypsa-eur` pinned by `pypsa-eur.pin` (repository URL and
commit) with the configuration in `config/coppersushi.yaml`. Set it up once:
```bash
git clone https://github.com/PyPSA/pypsa-eur.git ../pypsa-eur  # the runner fetches the pinned commit from the URL in pypsa-eur.pin
brew install pixi            # PyPSA-Eur's environment manager
(cd ../pypsa-eur && pixi install)
```
Then, from this repository:
```bash
python -m coppersushi.data_sources.pypsa_eur solve
```
checks the sibling out at the pinned commit, runs the workflow (a first run downloads about
20 GB and takes an hour on a fast connection; later runs take minutes) and writes the solved
network to the gitignored `networks/candidates/opf-<day>-<pin>.nc`, viewable in the app at
`/candidates/<file stem>` (after an app restart). Iterate as often as you like; when a solve is the one to keep,
```bash
python -m coppersushi.data_sources.pypsa_eur promote networks/candidates/opf-<day>-<pin>.nc
```
copies it to `networks/opf-<day>.nc` and stages it — committing is the sanction, and each
committed version is a Git LFS object kept forever. Set `PYPSA_EUR_DIR` to use a checkout elsewhere. Design: [`wiki/pypsa-eur-sibling.md`](wiki/pypsa-eur-sibling.md).

## Installation on Heroku
The image is built from your working tree, so `git lfs pull` first: the build refuses LFS
pointers. Prepare the endpoint seed and OSM locator using the [market-data commands](#market-data)
above before building. Docker includes only that seed and the locator CSVs from `data/` and
validates both during the build. They survive dyno restarts as part of the image; runtime cache
additions are disposable and may need another hourly fetch after a restart. Refresh the seed
before subsequent deployments to retain broader coverage.

Tokens travel as config vars, never in the image (`.secrets/` is docker-ignored).
```bash
heroku config:set MAPBOX_TOKEN=<token>
heroku config:set ELECTRICITY_MAPS_API_KEY=<key>
heroku container:push web
heroku container:release web
```
Heroku's router can time out after 30 seconds. Gunicorn allows 90
seconds so a slow request can finish saving its cache; **Retry** can then reuse it. There is no
whole-day runtime fetch, background prefetcher, or additional cache service.
(based on https://github.com/heroku-examples/python-miniconda)
