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

### Adjacent-validation

As of 2026-10-13, the candidate owner-minus-adjacent reconstruction is:

```
P_owner − P_other = (F_owner − F_Core_hub) + Σ_hub c μ / α
                   + (G_adjacent_hub − G_other) + δ_owner
```

`F` uses normalized Core physical duals; `G` uses Nordic duals without Core α. `δ_owner` is Poland's cap component, zero for other Core owners. For the two non-Nordic AC interfaces, the candidate adjacent outer term is zero. Each interval must independently match observed endpoint prices within €0.02/MWh. The selected row contributes only its own signed `c μ / α`; the check uses all active bounds on that hub.

The [Nordic handbook](https://publicationtool.jao.eu/PublicationHandbook/Nordic_PublicationTool_Handbook_v1.5.pdf), §§3 and 6.3, maps opposite endpoints: `DK1_CO`, `NO2_ND`, `NO2_NK`, `SE4_SP`, `SE4_BC`, `DK1_DE`, `DK2_KO`. Its `fbDomainShadowPrice` feed publishes Nordic coefficients and duals. Compare each hub with its owning Nordic zone; Nordic synchronous groups do not share one balance-price constant.

A paced audit checked first/last binding cases for each sign on September 12 and October 8, 2026, using complete one-interval Nordic responses and quarter-hour endpoint prices. All nine interfaces are represented; 19 of 40 lossless candidate reconstructions pass:

| Interface | Samples passing €0.02 check / sampled | Largest residual, €/MWh |
|---|---:|---:|
| DE–DK1 AC | 2 / 2 | 0.008 |
| LitPol AC | 6 / 6 | 0.007 |
| RO–BG AC | 2 / 2 | <0.001 |
| COBRA | 6 / 8 | 0.257 |
| Kontek / Kriegers Flak | 3 / 4 | 0.100 |
| NorNed | 0 / 6 | 21.297 |
| NordLink | 0 / 6 | 44.907 |
| SwePol | 0 / 5 | 143.066 |
| Baltic Cable | 0 / 1 | 3.006 |

These are empirical checks, not a universal decomposition. Both coefficient signs and α<1 occur in the sample. Missing coefficients, prices, Polish adjusted price, or zero α suppress contributions. Fetch adjacent prices and Nordic rows only for the selected interface/interval; an outage leaves selection available.

[Nord Pool documents implicit losses](https://www.nordpoolgroup.com/en/trading/Day-ahead-trading/loss-functionality/) on NorNed, NordLink and Baltic Cable, so their selected-dual scaling stays unsupported even if a lossless equation happens to match. [Ramping restrictions](https://www.nordpoolgroup.com/en/trading/Day-ahead-trading/Ramping/) include joint NorNed/NordLink limits and hourly flow fixing on SwePol. These mechanisms can add price terms; the audit does not attribute each residual to a specific mechanism. Never widen tolerance to hide them, infer missing duals from the observed spread, or treat a full spread as the selected constraint's contribution.

Loss-aware selected-dual scaling and unreconciled ramping cases remain in [the spec](specs/cnec-constraint-selection.md). The [FB/LTA audit](flow-based-market-coupling.md#attribution-validation) owns the existing Core scaling evidence.
