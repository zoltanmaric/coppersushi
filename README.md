# Copper Sushi 🍣
## A Power System Analysis and Visualisation Tool
[![](assets/coppersushi-gif.gif)](https://121gigawatts.org/copper-sushi-power-flow-european-grid/)

A simple Plotly/Dash web app for visualising power flow optimisation
solutions  from [`pypsa-eur`](https://github.com/PyPSA/pypsa-eur).

The web app is deployed
[**here**](https://121gigawatts.org/copper-sushi-power-flow-european-grid/),
along with an explanation of the main features.

The bundled network `networks/elec_s_all_ec_lv1.01_2H.nc` is a solved
PyPSA-Eur 0.5.0 optimal power flow (one day, 2013-07-17, 2-hour snapshots,
lines expandable to 1.01× current volume). The exact configuration that
produced it is tagged
[`coppersushi-v1`](https://github.com/zoltanmaric/pypsa-eur/tree/coppersushi-v1)
in my fork of `pypsa-eur`; see its `config.yaml` and README.


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