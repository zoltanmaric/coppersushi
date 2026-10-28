# Copper Sushi 🍣
## A Power System Analysis and Visualisation Tool
[![](assets/coppersushi-gif.gif)](https://121gigawatts.org/copper-sushi-power-flow-european-grid/)

A simple Plotly/Dash web app for visualising power flow optimisation
solutions  from [`pypsa-eur`](https://github.com/PyPSA/pypsa-eur).

The web app is deployed
[**here**](https://121gigawatts.org/copper-sushi-power-flow-european-grid/),
along with an explanation of the main features.

The app has two views: `/opf-2024` (29 August 2024, hourly, on the 2025 grid)
and `/cnec` (prices and binding constraints). `/embed/opf-2024` shows the OPF map
and time controls without navigation. Both OPF layouts use the same solved network.

For the first rollout, `/` also shows the embed, preserving the article's existing
iframe. `ROOT_VIEW=embed` is the default; set `ROOT_VIEW=full` only after the article
uses `/embed/opf-2024`. Model details: [power-flow architecture](wiki/sushi-2.md).

Networks are versioned with [Git LFS](https://git-lfs.com). Install `git-lfs` system-wide (`brew install git-lfs`)
so git works from any shell or IDE, run `git lfs install` once to register the filters that turn pointers into
files, then `git lfs pull`. The Pixi environment also includes `git-lfs` for commands run through `pixi run`.
Clone with `GIT_LFS_SKIP_SMUDGE=1` to skip the files, e.g. to run only the tests.

## Working with Agents
The repository is developed with coding agents (Claude Code and Codex), and the tooling for that is
part of the repository:

- [`AGENTS.md`](AGENTS.md) holds the rules the agents follow here. Every directory with rules of its own
  has one.
- [`.agents/skills/`](.agents/skills/) holds the skills those rules invoke.
- [`wiki/`](wiki/) is an LLM-maintained wiki of domain knowledge, design decisions and specs.

Install the checkout base guard once per clone:

```sh
python3 scripts/install-checkout-guard.py
```

New worktree checkouts fetch `origin/main` and fail unless `HEAD` contains that commit.
The worktree remains created; rebase it before starting work. A failed fetch also fails
the command. Ordinary branch switches are unaffected, and the existing checkout hook
(including Git LFS) is preserved. `git worktree add --no-checkout` does not run checkout
hooks. Clones with a custom `core.hooksPath` need to integrate the guard there manually.

## Local Installation
Install [Pixi](https://pixi.sh) 0.77.1 and Git LFS (for Git outside Pixi, including the IDE).
Supported development platforms are Apple Silicon macOS 15+ and Linux x86-64 (glibc 2.28+).
The default interpreter is Python 3.14.10. From the repository root, one command installs the locked environment:

```sh
pixi run --locked setup
```

Repeat the same command after pulling dependency changes. No credentials, solver runs,
cloud resources or large datasets are needed for setup or tests.
`pyproject.toml` defines Python packages and Pixi tools; `pixi.lock` pins both platforms.
Use `pixi add` / `pixi add --pypi` to change dependencies and commit both files.

In PyCharm, select an **existing local Python interpreter** at
`<checkout>/.pixi/envs/default/bin/python`. No Conda executable or Pixi plugin is needed.
Exclude `.pixi` from indexing. The default environment covers the app and forecasts;
the package is installed editable, so imports also work outside the repository directory.
Use Pixi to change packages, rather than the IDE's package installer.

`pixi run --locked <command>` supplies the environment's tools and activation variables.
Direct IDE Python runs use the interpreter's packages; external tools invoked by name
may also need the Pixi environment's `bin` directory on the run configuration's `PATH`.

### Mapbox Token
A Mapbox access token is required to run the app. Tokenless startup is unsupported.
Register for a free token at [mapbox.com](https://www.mapbox.com/), then paste it into
`.secrets/.mapbox_token`, or export it as `MAPBOX_TOKEN`.

Then you can start the server by running
```bash
pixi run --locked dev
```

Once the server starts, the web app will be available at http://localhost:8050

### Market Data

The CNEC view uses JAO's public active flow-based constraints and Electricity Maps' published day-ahead
prices. Put an Electricity Maps key in `.secrets/.electricity_maps_api_key`, or export
`ELECTRICITY_MAPS_API_KEY`. Fetch one delivery day into the gitignored local cache with:

```bash
pixi run --locked python -m coppersushi.data_sources.jao fetch-active 2026-09-11
pixi run --locked python -m coppersushi.data_sources.electricity_maps fetch 2026-09-11
```

The map places JAO's elements by their published substation names on the OSM-locator substation
list in [core-tso-data](https://github.com/fneum/core-tso-data), which is unlicensed and therefore
fetched locally rather than committed. Fetch it once, plus at least one day's final domain, which
names each element's substations:

```bash
pixi run --locked python -m coppersushi.data_sources.osm_locator fetch
pixi run --locked python -m coppersushi.data_sources.jao fetch 2026-09-11
pixi run --locked python -m coppersushi.data_sources.jao seed 2026-09-11
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
pixi run --locked test
```
This runs app tests, forecast tests and forecast type checks.
The tests run against small checked-in fixtures under `tests/fixtures/`, never against the
networks. Tests require no Mapbox token; they build figures without fetching map tiles.

GitHub Actions runs this suite on non-draft pull requests, including when a draft is
marked ready. Draft updates skip it. The suite includes the existing architecture checks.

## Solving a day with PyPSA-Eur
The networks in `networks/` are produced by [PyPSA-Eur](https://github.com/PyPSA/pypsa-eur),
run from a **sibling checkout** at `../pypsa-eur` pinned by `pypsa-eur.pin` (repository URL and
commit) with the configuration in `config/coppersushi.yaml`. Set it up once:
```bash
git clone https://github.com/PyPSA/pypsa-eur.git ../pypsa-eur  # the runner fetches the pinned commit from the URL in pypsa-eur.pin
(cd ../pypsa-eur && pixi install)
```
Then, from this repository:
```bash
pixi run --locked python -m coppersushi.data_sources.pypsa_eur solve
```
checks the sibling out at the pinned commit, runs the workflow (a first run downloads about
20 GB and takes an hour on a fast connection; later runs take minutes) and writes the solved
network to the gitignored `networks/candidates/opf-<day>-<pin>.nc`, viewable in the app at
`/candidates/<file stem>` (after an app restart). Iterate as often as you like; when a solve is the one to keep,
```bash
pixi run --locked python -m coppersushi.data_sources.pypsa_eur promote networks/candidates/opf-<day>-<pin>.nc
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
The container installs the runtime subset of the same Pixi lock; it does not resolve
a separate production dependency set.
