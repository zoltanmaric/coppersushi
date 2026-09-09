# Core day-ahead capacity calculation: from the TSOs' grid models to the auction's shadow prices

How the numbers that limit tomorrow's cross-zonal trade in Core come about. This is the reference for the process the [congestion forecast](specs/core-congestion-forecast.md) emulates; what that project substitutes for each step lives in the spec, not here. Vocabulary first, then one row of the published result read column by column, then the chain that produces it, then who acts and who decides. The maths of PTDF, RAM and shadow price is in [flow-based-market-coupling](flow-based-market-coupling.md); the sources are the TSOs' [explanatory note](literature/core-da-ccm-explanatory-note.md), JAO's [handbook](literature/jao-core-publication-handbook.md) and the [EUPHEMIA description](literature/euphemia-public-description.md). Every number below is from JAO's web service for 2024-08-28 and 2024-08-29 unless said otherwise.

## Vocabulary

- **D, D-1, D-2.** D is the delivery day. The auction for D clears on D-1 at noon. The grid models for D are built on D-2. "D-2 evening" is the last moment before anything about D is published, and the cutoff a forecast is measured against.
- **Net position.** A zone's exports minus imports in an hour, in MW. The auction's decision variables, one per hub and hour.
- **Hub.** JAO's word for anything with a net position: the twelve Core zones, and two virtual hubs at the ends of ALEGrO, the direct-current cable between Belgium and Germany (`ALBE` at Lixhe, `ALDE` at Oberzier). A cable inside a meshed grid carries whatever it is told to, so the auction trades it like a border of its own. PTDF columns are named per hub.
- **The domain.** The set of linear constraints the auction must respect: one row per monitored element under an assumed outage, reading "PTDF · net positions ≤ RAM", plus rows that cap a hub's net position. JAO publishes three versions for D on D-1: initial at 01:15, pre-final at 08:00, final at 10:30. JAO's publication tool is a website with one table per dataset and a web service behind it; "page" below means one of those tables.
- **Critical network element, with contingency.** A line or transformer a TSO monitors is a critical network element. Paired with a contingency, the assumed outage of some other element, it is a critical network element with contingency, one row of the domain. About 105 of 116 presolved rows in a sampled hour were such pairs; the rest are the element alone or an external constraint.
- **External constraint.** JAO's name for a row that is no network element: a cap on a hub's import or export, one PTDF of ±1 on that hub. On 2024-08-29 the only ones were ALEGrO's four, ±1,000 MW on each virtual hub.
- **Rating and margins.** `fmax` is the element's maximum flow in MW, from its current rating in amperes and its voltage; fixed, seasonal, or dynamic, changing hour by hour with the weather. The reliability margin `frm` is held back for forecast error. `ram`, the remaining available margin, is what is left for cross-zonal trade after the base flow and the margins are deducted: the right-hand side of the row.
- **Presolve.** Dropping every row the other rows already imply. About 120 of some 11,500 rows an hour survive, flagged `presolved`; only they reach the auction.
- **Shadow price.** After the auction, for each row that bound, the welfare one more MW of RAM on it would have bought, in €/MW. Published per binding row and hour.
- **Price spread.** The difference between two zones' day-ahead prices in an hour, published per border.
- **Vertical load.** The load the transmission grid sees at its substations: consumption minus the generation connected below it, in distribution grids, called embedded generation (rooftop solar, small wind and hydro). Not total consumption: for Germany at noon it is a tenth of it.
- **Phase-shifting transformer.** A transformer whose tap changer shifts the voltage angle and so steers power between parallel paths. Its tap position is an hourly operational setting, like a valve.
- **Generation shift key.** For each zone, the shares by which a change in the zone's net position is spread over its plants. It turns nodal sensitivities into zonal PTDFs and is the auction's only notion of what happens inside a zone.
- **Remedial action.** A measure a TSO can take to relieve an element: a phase-shifter tap or a topology change, which cost nothing, or redispatching plants, which costs money. The domain computation uses only the costless kind.
- **D2CF and RefProg.** Two JAO pages published with the final domain. D2CF, the D-2 congestion forecast, gives per zone the vertical load, generation and net position from the TSOs' grid models. RefProg, the reference programme, gives the cross-border exchanges assumed when the models were merged.

## One row of the domain

The whole chain exists to produce rows like this one. Elia monitors Lixhe–Gramme, a 380 kV line inside Belgium, under the loss of the three-legged line Van Eyck–André Dumont–Gramme, whose three branches meet at Zuttendaal. The row reached the auction on both days at the first hour (00:00 CEST). The step column points into the chain below.

| Column | 28 Aug | 29 Aug | What it is | Set in step |
|---|---|---|---|---|
| `tso` | ELIA | ELIA | The TSO that monitors the element | 4 |
| `cneName`, `substationFrom`, `substationTo`, `elementType`, `hubFrom`, `hubTo` | Lixhe - Gramme 380.11, Gramme, Lixhe, Line, BE, BE | same | Which element, between which substations, in which zones; both ends in Belgium, so an internal line | 4 |
| `direction` | DIRECT | DIRECT | Each element gets two rows, one per flow direction | 4 |
| `contName`, `contingencies` | the tripod's three branches | same | The assumed outage, as free text and as a list of branches with their substations | 4 |
| `fmaxType`, `imax`, `u` | SEASONAL, 2174 A, 380 kV | SEASONAL, 2051 A, 380 kV | The rating's kind, the current rating, the voltage level | 4 |
| `fmax` | 1506 MW | 1421 MW | √3 · 400 kV · `imax`: the operating voltage of the 380 kV level, on all 10,080 such rows | 4 |
| `frm` | 151 | 142 | Reliability margin, ten per cent of `fmax` here | 4 |
| `minRamFactor` | 70 | 70 | The share of `fmax` that must stay open to trade | 7 |
| `frefInit` | 506 | 217 | Flow in the D-2 base case, at the aligned net positions | 5 |
| `fnrao` | 3 | 0 | Flow relieved by costless remedial actions | 6 |
| `fref` | 503 | 217 | `frefInit − fnrao`, the base flow the auction starts from | 6 |
| `fall` | 499 | 424 | Flow if every Continental exchange were zero | 5 |
| `fuaf` | 169 | 144 | Flow caused by the exchanges of zones outside Core | 5 |
| `fcore` | 668 | 568 | `fall + fuaf`: the flow when only Core exchange is zero | 5 |
| `amr` | 198 | 140 | Margin added to reach the minimum share: max(0, 0.7 · 1421 − (1421 − 142 − 424)) = 140 | 7 |
| `ltaMargin`, `fltn` | 0, 0 | 0, 0 | Long-term rights: extra margin, and the flow from their nominations | 8 |
| `cva`, `iva` | 0, 0 | 0, 0 | Validation cuts, coordinated and individual | 9 |
| `ram` | 885 | 851 | `fmax − frm − (fcore + fltn) + amr − iva` = 1421 − 142 − 568 + 140 = 851 | 10 |
| `presolved` | true | true | Handed to the auction | 10 |
| `ptdf_BE`, `ptdf_FR`, `ptdf_NL`, `ptdf_ALBE` | 0.119, 0.072, −0.004, −0.398 | 0.102, 0.051, −0.018, −0.421 | MW on the line per MW of that hub's net position; the other hubs are below 0.03; hubs outside Core are empty | 5 |

Read as the auction reads it: 0.102 · NP_BE + 0.051 · NP_FR − 0.018 · NP_NL − 0.421 · NP_ALBE + … ≤ 851. The 568 MW that flow with no Core exchange are already inside the right-hand side, so the row says the net positions may add 851 MW before the line reaches its limit less its margin plus the minimum-margin lift. The Belgian end of ALEGrO sits at Lixhe, hence the large ALEGrO coefficient on a line that never crosses a border. The line is monitored because a Belgian–Dutch trade puts 0.102 + 0.018 = 12 % of its volume on it, above the 5 % threshold of step 4. And the lift in `amr` is the 70 % rule at work: after margin and the zero-exchange flow only 855 MW of 1421 would have been open to trade, short of 995.

What changed overnight is the flows (`frefInit` 506 to 217, `fcore` 668 to 568), the PTDFs by a few hundredths, and this time the seasonal rating. The element, its contingency, its margin share and its factor did not. That is the pattern across the hour: of the 487 elements monitored on 29 Aug, 479 were monitored on 28 Aug; 97 % of the rows are the same element under the same contingency; of the 109 rows that reached the auction on 29 Aug, 108 were in the previous day's list and 90 had reached the auction the day before as well.

## The chain, step by step

Each step names who acts, what it consumes, and what of that JAO publishes for D and when. Identities marked *verified* were checked on JAO's rows for 2024-08-29.

1. **Aligning net positions (D-2, an ENTSO-E process).** Each TSO forecasts its zone's net position for every hour of D and a Europe-wide alignment makes them consistent, so that every TSO builds its grid model against the same exchanges. Published at 10:30 D-1 as D2CF and RefProg.

2. **Individual grid models (D-2, each TSO).** Each TSO builds an hourly model of its own grid for D: topology with planned outages, phase-shifter taps, forecast load per node, forecast output per plant, HVDC flows. None of it is published; D2CF gives only the per-zone totals, and planned outages appear on ENTSO-E's transparency platform as they become known.

3. **Merged model (D-2, the merging agent, a regional coordination centre).** The individual models are checked and merged into one model of Continental Europe per hour; a late or broken one is replaced by a fallback. Not published.

4. **The TSOs' inputs (each TSO).** Each TSO supplies its list of monitored elements with their contingencies, the rating type and current rating of each, the reliability margins (computed centrally once a year from forecast-versus-realised flows; a TSO may reduce its own within 5 to 20 % of the rating), its generation shift key, its external constraints, the remedial actions it offers, and the long-term rights already sold. How the list is decided: cross-zonal lines are always in; an internal element is in when a trade between some pair of Core zones would push at least 5 % of its volume over it, checked on the merged model, or when the TSO wants it in from its own security studies; the contingencies are the outages it plans against, hypothetical single failures, not the planned outages of step 2. It is a maintained list, not the result of an optimisation, and it changes little from day to day, as the row above shows. Published: per row of the domain pages the element name, the contingency's branches, `imax`, `u`, `fmax`, `fmaxType`, `frm` and `minRamFactor`; remedial actions and long-term rights on their own pages at 10:30; external constraints as domain rows. The shift key is never published as numbers; the explanatory note gives each TSO's recipe, such as pro rata to the D-2 output of its dispatchable plants.

5. **Load flow (the coordinated capacity calculator, Coreso with TSCNET).** A DC load flow with contingency analysis on the merged model gives, per row, the flow at the aligned net positions (`frefInit`), the nodal sensitivities, and through the shift key the zonal PTDFs (`ptdf_<hub>`). The flow under a contingency is the base flow plus the outaged branches' flows redistributed by their outage factors; where a contingency has several branches, as in the tripod above, the factors are the multi-branch form. Two more flows per row: `fall`, the flow if every Continental exchange were zero, and `fuaf`, the flow caused by the assumed exchanges of zones outside Core; their sum `fcore` is the flow without Core exchanges, and it is the base flow minus what the aligned net positions add through the PTDFs, with ALEGrO's reference flow counted as a hub (*verified* within 5 MW on half the presolved rows and 58 MW at worst, D2CF's net positions being rounded to the MW). Rows under the 5 % threshold stay listed but never reach the auction. Published on the three domain pages.

6. **Remedial-action optimisation (calculator).** Costless actions, phase-shifter taps and switching, are chosen to enlarge the domain in the expected direction of trade; the flow relieved per row is `fnrao`, and the base flow becomes `fref = frefInit − fnrao` (*verified* on all 7,019 rows with a non-zero `fnrao`). Published with the domain, the chosen actions on their own page.

7. **Minimum margin (calculator).** Regulation (EU) 2019/943 requires at least 70 % of an element's capacity to be available to cross-zonal trade; elements under a derogation have lower factors. Where `fmax − frm − fall` falls short of `minRamFactor · fmax`, the shortfall `amr` is added to the margin: capacity the TSO promises to make real with redispatch after the auction. *Verified*: `amr = max(0, minRamFactor · fmax − (fmax − frm − fall))` on all 459 lifted rows of the first hour; the factor was 70 for about half the presolved rows and 20 to 62 for the rest.

8. **Long-term rights (D-1, calculator).** Capacity sold months ahead must remain feasible, so the domain is enlarged where needed (`ltaMargin`) and shifted by the long-term nominations (`fltn`). Published on the `lta` and `ltn` pages at 10:30.

9. **Validation (D-1, each TSO).** Each TSO checks the domain against its own security analysis and may only reduce, on its own elements, with a published justification: `cva` when coordinated, `iva` when individual.

10. **Final computation and presolve (calculator).** RAM per row, *verified*: `ram = fmax − frm − (fcore + fltn) + amr − iva` on all 116 presolved rows of the first hour. Presolve then drops every row the others already imply; about 120 rows per hour out of some 11,500 remain, flagged `presolved`, and only those are handed to the auction. Which rows survive shifts a little overnight, 90 of 109 in the sample above, while the list they are drawn from barely moves. Published at 10:30 D-1.

11. **Clearing (12:00 to 13:00 D-1, the power exchanges).** EUPHEMIA maximises welfare over the bids, subject to the presolved rows, the allocation constraints it receives outside the domain, and the ATC borders elsewhere in Europe. Its variables are the hubs' net positions; nothing inside a zone is visible to it, and a zone's change lands on the grid through the shift key baked into the PTDFs, never through re-optimising plants against a line. Out come zonal prices, net positions and, for each binding row, its shadow price. Published: shadow prices with the rows' PTDFs at 13:00; net positions and price spreads at 15:50; prices by the exchanges. The bids only as aggregated curves per zone, sold under internal-use licences ([flow-based-market-coupling](flow-based-market-coupling.md)).

## Who acts, and who decides alone

Each TSO models only its own grid, and nobody co-optimises the grid Europe-wide; the one Europe-wide optimisation, EUPHEMIA, sees only the zonal constraints it is handed. In between sits one central computation on a merged model, run on the TSOs' behalf by two regional coordination centres, Coreso and TSCNET ([ENTSO-E's Core page](https://www.entsoe.eu/bites/ccr-core/day-ahead/)). ENTSO-E sets the standards and runs the alignment of net positions; it computes no capacity. JAO publishes; it computes nothing. The auction belongs to the power exchanges.

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
    TSO -- "monitored elements, contingencies, limits, shift key, remedial actions, external constraints" --> CCC
    CCC -- "PTDF and margin per element" --> VAL
    VAL -- "reductions" --> CCC
    CCC -- "final presolved domain" --> EUP
    CCC -- "domain and inputs" --> JAO
    EUP -- "prices, net positions, shadow prices" --> JAO
```

| Actor | Does | Decides alone |
|---|---|---|
| Each Core TSO (16) | Builds an hourly grid model of its own area for the day after tomorrow: topology, outages, forecast load, generation and DC flows | Which elements are monitored and under which outages; each element's current limit (fixed, seasonal or dynamic); whether to cut its elements' centrally computed reliability margin, down to 5 to 20 % of the limit; how an extra exported MW is spread over its plants (the generation shift key); which remedial actions it offers; caps on its hubs' net positions |
| Merging agent (a regional coordination centre) | Checks each model, substitutes a fallback for a late or broken one, merges all of Continental Europe into one model per hour | Nothing about capacity |
| Coordinated capacity calculator (Coreso with TSCNET) | DC load flow with contingency analysis on the merged model: nodal sensitivities by perturbing each node, zonal PTDFs through the shift keys, reference flows, remedial-action optimisation, minimum-margin adjustment, long-term-rights inclusion, presolve; computes the reliability margins once a year from a year of forecast-versus-realised flows | The redundant constraints it drops |
| Each Core TSO again | Validates the domain against its own security analysis | May only reduce, on its own elements, with a published justification |
| JAO | Publishes the domain at 10:30 D-1 and the shadow prices at 13:00, local time | Nothing |
| Power exchanges (NEMOs) | Run EUPHEMIA against the presolved constraints | The clearing, within a 12-minute limit |
