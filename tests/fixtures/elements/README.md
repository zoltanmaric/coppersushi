# Fixtures for `elements.py`

## The JAO side is synthesised

JAO's terms forbid redistributing its data, so `elements-day.csv` and `contingencies-day.csv`
carry **no JAO-derived bytes**: the EICs, limits, margins and hours are invented, and each row
exists to reproduce one quirk of the real format. Substation names are facts about physical
infrastructure rather than JAO's dataset, so they are real, as is the OpenStreetMap data (ODbL)
underneath the network slice. The real measurements these stand for are in the PR body.

What each element is for:

| `eic` | reproduces |
| --- | --- |
| `SYN-LINE-380-A` | a plain line, published on four rows (two hours × two directions) that must collapse to one |
| `SYN-LINE-220-B` | the same substation pair at another voltage: only the bus-name suffix tells the two branches apart |
| `SYN-TIE-BOTHWAYS` | one tie-line published as `Etzenricht → Hradec` and `Hradec → Etzenricht` |
| `SYN-TRAFO-HAGENWERDER` | a transformer: one substation, not a pair |
| `SYN-PST-ETZENRICHT` | a phase shifter, which resolves the same way |
| `SYN-LINE-ABSENT` | an element whose substation never matched a bus |
| `SYN-UNTYPED-LINE` | JAO's rows with no `elementType` and no hubs, which are lines |
| `SYN-LINE-NOBRANCH` | two matched substations with no branch of ours between them |
| `SYN-LINE-NEAREST` | an end whose matched bus carries no branch, resolved from a bus 4.6 km away that belongs to no substation JAO named |
| `SYN-TRAFO-ABSENT` | a transformer at an unmatched site: a matching failure, not a missing component class |

`substation-matches.csv` is what `substations.match` returns for those names, including the
unmatched `MOSTAR` row: the matcher keeps its misses, and so must this fixture.

## The network slices

`network-slice.nc` is nine buses of the sanctioned solve `networks/opf-2024-08-29.nc`, plus the
synthetic components the real network cannot supply: it has **no transformers at all** (the
upstream simplification removed them) and no substation appearing at two voltages, and both are
needed to exercise the transformer path and the voltage pick. Everything named `synthetic/…` is
ours; every `way/…` bus, its coordinates and every `relation/…` line are OSM-derived and real.
`network-slice-no-transformers.nc` is the same slice with the transformers removed, standing for
the network as it is today, where a transformer element is `no_component_in_network`.

Branches are removed **before** buses: `n.remove("Bus", …)` on its own leaves branches pointing
at buses that no longer exist, and `determine_network_topology` then raises. The country shapes
go too — 400 MB of WKT polygons this fixture has no use for.

```python
import pypsa

KEEP = [
    "way/59026005-380",   # Hagenwerder, DE      ─┐ two parallel 380 kV circuits
    "way/111615226-220",  # Mikulowa, PL         ─┘
    "way/29084374-380",   # Etzenricht, DE       ─┐ the tie-line published both ways round
    "way/28099187-220",   # Hradec, CZ           ─┘
    "way/693112798-400",  # Vernerov, CZ          — 8.5 km from Hradec: the nearest-bus fallback
    "way/255277953-400",  # Dobrzen, PL          ─┐ the untyped element
    "way/175071712-400",  # Nosovice, CZ         ─┘
    "way/23096966-380",   # Geertruidenberg, NL  ─┐ matched, but nothing between them
    "way/727225348-220",  # Westtirol, AT        ─┘
]

n = pypsa.Network("networks/opf-2024-08-29.nc")
n.remove("Shape", n.shapes.index)
for component in ("Line", "Link", "Transformer"):
    static = n.static(component)
    n.remove(component, static.index[~(static.bus0.isin(KEEP) & static.bus1.isin(KEEP))])
for component in ("Generator", "Load", "StorageUnit", "Store", "ShuntImpedance"):
    static = n.static(component)
    if not static.empty:
        n.remove(component, static.index[~static.bus.isin(KEEP)])
n.remove("Bus", n.buses.index.difference(KEEP))

for bus in ("way/59026005-380", "way/29084374-380"):  # a second voltage level at the same site
    n.add("Bus", bus.replace("-380", "-220"), **n.buses.loc[bus].drop(["sub_network"]).to_dict())
n.add(
    "Line", "synthetic/hagenwerder-mikulowa-220",
    bus0="way/59026005-220", bus1="way/111615226-220",
    s_nom=490.0, x=4.0, r=0.4, length=12.1, s_max_pu=0.7, num_parallel=1.0,
)
n.add("Transformer", "synthetic/hagenwerder-trafo",
      bus0="way/59026005-380", bus1="way/59026005-220", s_nom=600.0, x=0.1, r=0.001)
n.add("Transformer", "synthetic/etzenricht-pst",
      bus0="way/29084374-380", bus1="way/29084374-220", s_nom=600.0, x=0.1, r=0.001)

# An unnamed site 4.6 km from Vernerov carrying the only branch to Etzenricht: the legitimate
# nearest-bus fallback. Vernerov's other neighbour, Hradec 8.5 km away, is a substation JAO
# names in its own right, and widening into it would steal the tie-line's corridor.
nearby = n.buses.loc["way/693112798-400"].drop(["sub_network"]).to_dict()
nearby["x"] = round(nearby["x"] + 0.065, 6)
n.add("Bus", "synthetic/vernerov-nearby-400", **nearby)
n.add(
    "Line", "synthetic/etzenricht-vernerov-380",
    bus0="way/29084374-380", bus1="synthetic/vernerov-nearby-400",
    s_nom=1200.0, x=15.0, r=1.5, length=120.9, s_max_pu=0.7, num_parallel=1.0,
)

n.determine_network_topology()
n.name = "jao elements sample"
n.export_to_netcdf("tests/fixtures/elements/network-slice.nc")

flat = n.copy()
flat.remove("Transformer", flat.transformers.index)
flat.determine_network_topology()
flat.name = "jao elements sample without transformers"
flat.export_to_netcdf("tests/fixtures/elements/network-slice-no-transformers.nc")
```
