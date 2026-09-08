# How Core's cross-zonal capacity is computed

Who produces the flow-based domain that [EUPHEMIA](literature/euphemia-public-description.md) clears against, and when. The maths of the domain (PTDF, RAM, shadow prices) is in [flow-based-market-coupling](flow-based-market-coupling.md); the source is the TSOs' [explanatory note](literature/core-da-ccm-explanatory-note.md) and JAO's [handbook](literature/jao-core-publication-handbook.md).

## Neither siloed nor a master solver

Each TSO models only its own grid, and nobody co-optimises the grid Europe-wide; the one Europe-wide optimisation, EUPHEMIA, sees only the zonal constraints it is handed. In between sits one central computation on a merged model, run on the TSOs' behalf by two regional coordination centres, Coreso and TSCNET ([ENTSO-E's Core page](https://www.entsoe.eu/bites/ccr-core/day-ahead/)). ENTSO-E sets the standards and runs the alignment of net positions; it computes no capacity. The auction itself belongs to the power exchanges.

```mermaid
flowchart LR
    TSO["Each Core TSO<br>own grid only"]
    MA["Merging agent<br>a regional coordination centre"]
    CCC["Coordinated capacity calculator<br>Coreso and TSCNET"]
    VAL["Each Core TSO<br>validates own elements"]
    JAO["JAO publication tool"]
    EUP["EUPHEMIA<br>run by the power exchanges"]
    TSO -- "hourly D-2 grid model" --> MA
    MA -- "one Continental Europe model per hour" --> CCC
    TSO -- "monitored elements, contingencies, limits, shift key, remedial actions, zone caps" --> CCC
    CCC -- "PTDF and margin per element" --> VAL
    VAL -- "reductions" --> CCC
    CCC -- "final presolved domain" --> EUP
    CCC -- "domain and inputs" --> JAO
    EUP -- "prices, net positions, shadow prices" --> JAO
```

## Who does what

| Actor | Does | Decides alone |
|---|---|---|
| Each Core TSO (16) | Builds an hourly grid model of its own area for the day after tomorrow: topology, outages, forecast load, generation and DC flows | Which elements are monitored and under which outages; each element's current limit (fixed, seasonal or dynamic); whether to cut its elements' centrally computed reliability margin, down to 5 to 20 % of the limit; how an extra exported MW is spread over its plants (the generation shift key); which remedial actions it offers; caps on its zone's net position |
| Merging agent (a regional coordination centre) | Checks each model, substitutes a fallback for a late or broken one, merges all of Continental Europe into one model per hour | Nothing about capacity |
| Coordinated capacity calculator (Coreso with TSCNET) | DC load flow with contingency analysis on the merged model: nodal sensitivities by perturbing each node, zonal PTDFs through the shift keys, reference flows, remedial-action optimisation, minimum-margin adjustment, long-term-rights inclusion, presolve; computes the reliability margins once a year from a year of forecast-versus-realised flows | The redundant constraints it drops |
| Each Core TSO again | Validates the domain against its own security analysis | May only reduce, on its own elements, with a published justification |
| JAO | Publishes the domain at 10:30 D-1 and the shadow prices at 13:00, local time | Nothing |
| Power exchanges (NEMOs) | Run EUPHEMIA against the presolved constraints | The clearing, within a 12-minute limit |

## What this means for this project

Our solved network stands in for the merged model, and a nodal solve needs no shift key: the optimiser decides which plants move. What we cannot reproduce is everything in the "decides alone" column: element selection, limits, margins, remedial actions and validation cuts are sixteen operators' judgement, published only as outcomes. Two of those outcomes are usable inputs. JAO's final domain names the elements and their limits, which [specs/jao-grid](specs/jao-grid.md) maps onto our grid; and the D2CF page gives the TSOs' own D-2 forecast of load, generation and net position per hub, a direct comparison point for the Electricity Maps forecasts that [specs/core-congestion-forecast](specs/core-congestion-forecast.md) pins.
