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

The topology is documented; the numerical mapping from the swept bound duals to the middle term remains to be validated. N-SIDE's illustration omits LTA. Check signs, published-dual scaling and paired-hub representations against observed spreads, including any required adjacent-region terms. Do not add two descriptions of one bound twice or use the full observed spread as its contribution. Display the selected row's published dual separately from its validated price contribution. Unsupported attribution remains unavailable while the constraint stays selectable. The [FB/LTA audit](flow-based-market-coupling.md#attribution-validation) owns the existing scaling evidence.
