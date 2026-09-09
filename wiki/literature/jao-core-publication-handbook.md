# Core publication tool handbook

**Issued by** JAO, the Joint Allocation Office, as the handbook Article 25 of the Core day-ahead capacity calculation methodology requires alongside the publication platform. Version 1.8, December 2022: [PDF, 29 pages](https://publicationtool.jao.eu/PublicationHandbook/Core_PublicationTool_Handbook_v1.8.pdf). It is the data dictionary for [publicationtool.jao.eu/core](https://publicationtool.jao.eu/core/) and its web service at `/core/api`. An intraday counterpart exists ([Core IDCC handbook v1.6, October 2025](https://www.jao.eu/sites/default/files/2025-10/Core_IDCC_PublicationTool_Handbook_v1.6.pdf)).

**Draws on it:** [specs/jao-grid](../specs/jao-grid.md), [specs/core-congestion-forecast](../specs/core-congestion-forecast.md), [core-day-ahead-capacity-calculation](../core-day-ahead-capacity-calculation.md).

## What it settles

**Publication times, D-1, local time.** The site shows Central European Summer Time and downloads are in UTC. Initial computation 01:15; pre-final 08:00; final computation, maximum net positions, maximum bilateral exchanges, validation reductions, remedial actions, long-term allocations and nominations, D2CF, RefProg and external-border ATCs 10:30; shadow prices 13:00; congestion income 15:00; net positions, scheduled exchanges, intraday ATCs and price spreads 15:50. Download less than 30 days at a time.

**Three domain pages, one schema.** Initial (virgin, balanced to the reference program), pre-final (zero-balanced, before long-term nominations) and final (shifted to long-term nominations) share the columns. Per row: the element (TSO, name, EIC code, direction, hub from and to, substation from and to, element type, maximum-flow type), the contingency (same fields; a multi-branch contingency is one row per branch), and the margin breakdown: `presolved`, `ram`, `imax` in A, `u` in kV, `fmax`, `frm`, initial reference flow, flow change from non-costly remedial actions, flow without Core exchanges, flow without any Continental European exchanges, flow from assumed non-Core exchanges, adjustment for minimum RAM, long-term-allocation margin, coordinated and individual validation adjustments, flow after long-term nominations, and one PTDF column per hub including the two ALEGrO virtual hubs. Pre-final and final add the 70 % target per element and its justification.

**Element types:** busbar, DC link, generation, line, load, PST, tie-line, transformer. **Maximum-flow types:** fixed, seasonal, dynamic.

**`presolved`** is true when the row bounds the domain handed to the market; false rows are redundant. The shadow-prices page has the final page's schema with `presolved` replaced by the shadow price, defined as the welfare gain of one more MW on that element.

**Not every row is a CNEC.** Domain pages also carry elements filtered out by the 5 % rule (monitored, never presolved), duplicate-looking rows with `imax` 9999 for Core-to-non-Core borders (kept for a KPI), rows with the same name and slightly different margins (with and without remedial actions, both valid), four ALEGrO external constraints and four equality constraints.

**Validation reductions** list the element, the TSO, the reduction and a TSO-written justification; six TSOs (50Hertz, Amprion, APG, TenneT DE, TransnetBW, TenneT NL) validate jointly with one tool and share justifications. Individual reductions are capped so RAM stays non-negative.

**D2CF** publishes, per hub and TSO, the vertical load, generation and net position of the D-2 individual grid models. These are AC load-flow solved, so generation minus load differs from net position by losses.

**RefProg** gives the exchanges assumed when merging: Core-to-Core from the merged model's net positions, DC links from the individual models, Core-to-Swiss and Core-to-Italian from a forecast tool, all others from a reference day.

**External constraints** appear inside the domain when they cap the Core net position (Netherlands) and as a separate allocation-constraints feed when they cap the whole-market net position (Belgium import, Poland both ways).

**Naming.** Lines as `SUBSTATION-SUBSTATION voltage.circuit`, e.g. `AVELGEM-HORTA 380.101`; phase shifters as `PST NAME n`; tripods with a leading `Y-`. Remedial actions as `TOP_OPEN_`, `TOP_CLOSE_`, `TOP_2N_`, `PST_`, `SPS`, `AT_` prefixes, optionally suffixed `_PRA` or `_CRA`.

**Fallbacks** show on a spanning page; when the backup tool runs, only default parameters, allocation constraints and long-term pages are populated.

## What it leaves open

The handbook documents the pages. The web service, `/core/api/data/<page>?FromUtc=…&ToUtc=…`, public and keyless, differs from them in ways checked against 2024-08-29:

- Pages are `initialComputation`, `preFinalComputation`, `finalComputation`, `shadowPrices`, `d2CF`, `netPos`, `maxNetPos`, `priceSpread`; columns are lower camel case (`fmaxType`, `contName`; `amr` is the adjustment for minimum RAM).
- A multi-branch contingency is not one row per branch: every row carries a `contingencies` list, one entry per branch with its own substations, EIC code and element type, beside the free-text `contName`. All 116 presolved rows of the sampled hour have it.
- PTDFs are `ptdf_<hub>` columns on the domain pages and `hub_<hub>` columns on the shadow-price page.
- `priceSpread` reports `border_<A>_<B>` as the price of B minus the price of A.
- `d2CF` and `netPos` are one row per hour with one column per hub.

Nothing in it ties an element to coordinates; substations are names only.
