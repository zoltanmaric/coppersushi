# Fixtures for `true_up.py`

## The JAO side is synthesised

JAO's terms forbid redistributing its data, so `elements-day.csv` carries **no JAO-derived
bytes**: the EICs, limits and margins are invented and the day is three hours rather than
twenty-four. Substation names are facts about physical infrastructure rather than JAO's
dataset, so they are real. The real measurements these rows stand for are in the PR body.

Six element-directions, each reproducing one thing the module must get right:

| `eic` | `fmax_type` | reproduces |
| --- | --- | --- |
| `SYN-TU-FIXED-MOVER` | `FIXED` | the trap: declared fixed, `fmax` moves 1792 → 2002 MW over the day, so `is_hourly` must come from the data |
| `SYN-TU-CONSTANT` | `DYNAMIC` | the trap the other way round: declared dynamic, never moves |
| `SYN-TU-PARALLEL-1` | `SEASONAL` | two elements folding onto one branch — `relation/3730417-380` — whose rating is their sum, 1100 + 700 = 1800 MW |
| `SYN-TU-PARALLEL-2` | `SEASONAL` | " |
| `SYN-TU-ASYMMETRIC` | `SEASONAL` | a transformer rated 1600 MW one way and 1500 MW the other: the tighter direction binds `s_nom` |
| `SYN-TU-UNMATCHED` | `SEASONAL` | an element that reached no branch, so contributes no rating |

`element-matches.csv` is what `elements.branch_for` returns for those EICs against
`../elements/network-slice.nc`, checked in rather than recomputed so these tests exercise
`true_up` alone.

## The network

`comparison` and `report` run against `../elements/network-slice.nc` — nine buses of the
sanctioned solve plus the synthetic components that slice adds, built by the recipe in
`../elements/README.md`. Its OSM-derived parts are ODbL and real. The branches these fixtures
name are `relation/395087-380`, `relation/3730417-380`,
`synthetic/hagenwerder-mikulowa-220` and `synthetic/hagenwerder-trafo`.
