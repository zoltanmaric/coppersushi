# Fixtures for `security.py`

Both networks are invented outright — no JAO data, no OSM data, no real grid. LODF depends on
nothing but topology and reactance, and a four-bus network with unit reactances gives factors
you can check by hand, which a slice of a real network would not.

`mesh.nc` is a triangle A-B-C with a radial tail C-D. The triangle is the independent cycle
the factors need; `C-D` is the bridge. `A-B` and `C-D` carry two circuits each, so a partial
outage is exercised on both a meshed branch and a bridge.

`tree.nc` is the chain A-B-C-D, in which **every** branch is a bridge and `lodf` must
therefore return nothing at all.

```python
import pypsa

def build(name, lines):
    n = pypsa.Network()
    n.name = name
    for bus in "ABCD":
        n.add("Bus", bus, v_nom=1.0)
    for branch_id, bus0, bus1, num_parallel in lines:
        n.add("Line", branch_id, bus0=bus0, bus1=bus1,
              x=1.0, r=0.0, s_nom=100.0, num_parallel=num_parallel)
    n.determine_network_topology()
    return n

build("lodf triangle with a radial tail", [
    ("A-B", "A", "B", 2.0), ("B-C", "B", "C", 1.0),
    ("A-C", "A", "C", 1.0), ("C-D", "C", "D", 2.0),
]).export_to_netcdf("tests/fixtures/security/mesh.nc")

build("lodf chain, every branch a bridge", [
    ("A-B", "A", "B", 1.0), ("B-C", "B", "C", 1.0), ("C-D", "C", "D", 1.0),
]).export_to_netcdf("tests/fixtures/security/tree.nc")
```

`x = 1.0` is the whole component's reactance either way: PyPSA's `x_pu_eff` for a `Line` is
`x / v_nom²` and does not divide by `num_parallel`, so raising the circuit count changes the
outage arithmetic without changing the flows.
