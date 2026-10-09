# Virtual-hub interconnectors

### Virtual-hub

A virtual hub represents an interconnector/interface in the market equations. It has its own flow-based position and PTDF column; it is not an aggregate country cap. A country's cleared price is not automatically its virtual hub's price. The [annual audit](jao-constraint-types.md#active-audit) records their observed binding frequency and published coefficient vectors.

### Hub-mapping

Map the actual non-zero `hub_*` coefficient to an explicit interface record. Verify the row is a signed single-hub bound; keep its source ID, coefficient and shadow price. Use the published interface identity, not the first country token in `cnecName` or the active feed's `hubFrom`/`hubTo`.

| Published hub | Core-side bidding zone | Other bidding zone | Physical interface |
|---|---|---|---|
| ALBE / ALDE | BE / DE-LU respectively | DE-LU / BE respectively | Two ends of ALEGrO; one shared asset |
| NL_DK1_COBRA | NL | DK1 | COBRA cable |
| NL_NO2_NorNed | NL | NO2 | NorNed cable |
| DE_NO2_BigHub | DE-LU | NO2 | NordLink cable |
| PL_SE4_SwePol | PL | SE4 | SwePol cable |
| DE_SE4_Baltic | DE-LU | SE4 | Baltic Cable |
| PL_LT_BigHub | PL | LT | LitPol AC interface |
| DE_DK1_VH | DE-LU | DK1 | AC border interface |
| DE_DK2_BigHub | DE-LU | DK2 | Kontek and Kriegers Flak Combined Grid Solution |
| RO_BG_VH | RO | BG | AC border interface |

The [Core AHC report, chapter 3](https://www.jao.eu/sites/default/files/2025-10/Core%20FBE%20PT-AHC%20SPAICC-like%20run%204%20-%20Report_0.pdf) identifies the nine newer interfaces; the [Core handbook, §5.15](https://publicationtool.jao.eu/PublicationHandbook/Core_PublicationTool_Handbook_v2.2.pdf) identifies ALEGrO. Preserve bidding zones such as SE4 and DK1 rather than replacing them with whole-country prices. AC or combined interfaces need an interface identity and suitable geometry, not an invented single cable. This table establishes topology, not flow orientation: check the signed hub position/flow convention before interpreting an `import`/`export` suffix as a country direction.

### Price-decomposition

[N-SIDE's AHC explanation](https://www.n-side.com/en/insights/introduction-of-advanced-hybrid-coupling-in-the-core-region-of-the-european-day-ahead-market/) separates an endpoint-country spread into three terms:

```
P_B − P_A = (P_VA − P_A) + (P_VB − P_VA) + (P_B − P_VB)
```

Regional PTDFs and shadow prices determine the outer terms. The interconnector restriction determines the middle term. A zero Core-country coefficient therefore gives zero direct term in that basis, not proof of zero interconnector contribution in this endpoint decomposition.

### ALEGrO-validation

As of 2026-10-09, the adapter validates each selected interval against independent virtual-hub stationarity and the observed BE–DE price spread. With normalized physical potentials `F_h = −Σ μ_k PTDF_k,h / α`, the middle term is:

```
F_ALDE − F_ALBE = Σ_ALDE μ_k c_k / α − Σ_ALBE μ_k c_k / α
```

Here `c_k` is the published ±1 hub coefficient. The outer terms are `F_ALBE − F_BE` and `F_DE − F_ALDE`. Their sum with the middle term must match `P_DE − P_BE` within €0.02/MWh. Both checks passed in all 114 binding intervals on 2026-09-12 and 2026-10-08, including α<1. A failed check or α=0 leaves attribution unavailable.

Positive virtual injection enters Core. A +1 bound uses the other endpoint as reference; a −1 bound uses its owning Core zone. The selected bound's contribution to `P_owner − P_other` is `c_k μ_k / α`. ALBE and ALDE share one drawn asset but retain distinct published row IDs and dual terms; never discard a term merely because it names the same cable.

The nine newer interfaces remain selectable with capacity and published dual, but numerical endpoint attribution is unavailable. Their adjacent-region terms are not yet validated against observed prices. N-SIDE's illustration omits LTA; the [FB/LTA audit](flow-based-market-coupling.md#attribution-validation) owns the scaling evidence. No interface uses its full observed spread as a substitute contribution.
