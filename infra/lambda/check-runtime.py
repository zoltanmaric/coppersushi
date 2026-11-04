"""Smoke-test the installed serving environment without solver dependencies."""
import importlib.util
import json
from pathlib import Path
import sys

for package in ("pypsa", "linopy", "dask"):
    assert importlib.util.find_spec(package) is None, f"{package} leaked into runtime"

# The script lives below the app root; include it to exercise the actual entry point.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import app
import geopandas
import pyarrow
import pyproj
from coppersushi import cnecs

fixtures = Path(sys.argv[1])
rows = json.loads((fixtures / "synthetic-jao/active-fb-day.json").read_text())["data"]
assert not cnecs.active_constraints(rows).empty
assert not cnecs.constraint_ptdfs(rows).empty
assert app.server.test_client().get("/_dash-dependencies").status_code == 200
print("Serving imports, schema validation and Dash dependencies pass without solver packages")
