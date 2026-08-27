# Copper Sushi 🍣
## A Power System Analysis and Visualisation Tool
[![](assets/coppersushi-gif.gif)](https://121gigawatts.org/copper-sushi-power-flow-european-grid/)

A simple Plotly/Dash web app for visualising power flow optimisation
solutions  from [`pypsa-eur`](https://github.com/PyPSA/pypsa-eur).

The web app is deployed
[**here**](https://121gigawatts.org/copper-sushi-power-flow-european-grid/),
along with an explanation of the main features.

The `pypsa-eur` configuration used for the network plotted here can be
found in my fork of the `pypsa-eur` repo:
[`zoltanmaric/pypsa-eur`](https://github.com/zoltanmaric/pypsa-eur)


## Local Installation
Two supported ways to install the pinned dependencies; both give the same
versions.

### With `uv`
[`uv`](https://docs.astral.sh/uv/) manages the interpreter, the virtual
environment and the packages in one tool, no Conda needed:
```bash
./scripts/uv-install.sh
source .venv/bin/activate
```
The script reads the interpreter and the pins out of `environment.yml`, which
stays the single source of dependency versions. It is idempotent, so re-run it
after a dependency change.

### With Conda / Mamba
Installing this way requires Conda, but I recommend installing
[`Mamba`](https://mamba.readthedocs.io/en/latest/installation.html)
(a fully compatible, but better implementation of Conda).

After having installed `mamba`, just create and activate the Conda
environment by running
```bash
conda env create -f environment.yml
conda activate coppersushi
```

### `direnv` (optional)
The repo ships an `.envrc` that puts `.venv/` on your `PATH` when you enter the
directory, so the `uv` environment activates itself. With
[`direnv`](https://direnv.net/) installed, run `direnv allow` once. It does
nothing when there is no `.venv/`, so Conda users are unaffected.

### Mapbox Token
The map background requires a (free) Mapbox access token.
Register at [mapbox.com](https://www.mapbox.com/), then paste your token into
a file at `.secrets/.mapbox_token` (no trailing newline). The app will not
start without it.

Then you can start the server by running
```bash
python app.py
```

Once the server starts, the web app will be available at http://localhost:8050

## Running the Tests
```bash
pytest
```
The tests run against the bundled solved network in `networks/`.

## Installation on Heroku
After creating the Heroku app, run the following to deploy it:
```bash
heroku container:push web
heroku container:release web
```
(based on https://github.com/heroku-examples/python-miniconda)


## Performance Profiling
Run the following to show a [`snakeviz`](https://jiffyclub.github.io/snakeviz/) chart
of function call durations in your browser.
```bash
PYTHONPATH=. python profiling/profiling.py
snakeviz profiling/plot.prof
```
![](assets/Profiling.png)