# The copper plate problem

The domain argument motivating this project. Source: [The Copper Plate Must Die](raw/the-copper-plate-must-die.md) (Jun 2022, originally a Spark 2022 London talk).

## The argument

- Reaching zero emissions = electrify everything + zero-emission electricity 24/7. **Capacity expansion studies** (e.g. PyPSA-Eur-based, TU Berlin 2022) show how: a **co-optimisation of generation, storage & transmission** — each strongly influences where the others should be built.
- But EU market design treats each bidding zone (typically a country) as a **copper plate**: trades clear as if energy moves instantly anywhere within the zone, ignoring congestion.
- Recurring German example: cheap northern wind sells to southern industry → North→South corridors overload (e.g. 900 MW scheduled on an 800 MW line) → grid operators **redispatch**: curtail wind in the North (still paid) *and* pay a southern gas plant at a premium. No disincentive — participants repeat it daily, and new generation keeps siting without regard to congestion.
- Consequence: generation grows wherever, transmission (built by slow regulated monopolies) chases it — more expensive, slower, and the gap = **wasted renewables** covered by fossil plants.
- Proposed fix: **locational price signals** — buying from "far away" must cost more than "close by", nudging generation toward demand and demand (industry, electrolysis, storage) toward generation. Short-term regional price pain could be subsidized from saved redispatch costs.
- Policy context (2022): ACER initiated bidding-zone reconfiguration review; UK National Grid ESO considering locational pricing; EPEX Spot opposed to zone splits.

## Relation to this repo

Copper Sushi is the post's companion visualization: it makes congestion, flow direction, and nodal net power *visible*, showing why "just build more renewables" fails without siting/transmission awareness. Nodal detail (vs. copper-plate aggregation) is the app's whole reason to exist.
