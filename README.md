# Copper Sushi 🍣
## A Power System Analysis and Visualisation Tool
![](assets/coppersushi-gif.gif)

A simple Plotly/Dash web app for visualising power flow optimisation
solutions  from [`pypsa-eur`](https://github.com/PyPSA/pypsa-eur).

The web app is deployed
[**here**](https://121gigawatts.org/copper-sushi-power-flow-european-grid/),
along with an explanation of the main features.

The `pypsa-eur` configuration used for the network plotted here can be
found in my fork of the `pypsa-eur` repo:
[`zoltanmaric/pypsa-eur`](https://github.com/PyPSA/pypsa-eur)


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

Then you can start the server by running
```bash
python app.py
```

Once the server starts, the web app will be available at http://localhost:8050

## Installation on Heroku
After creating the Heroku app, run the following to deploy it:
```bash
heroku container:push web
heroku container:release web
```
(based on https://github.com/heroku-examples/python-miniconda)
