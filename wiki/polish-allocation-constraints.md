# Polish allocation constraints

Poland's allocation constraints bound its aggregate Single Day-Ahead Coupling net position. They are not limits on individual Polish interconnectors. The [country-cap page](country-import-export-caps.md#country-cap) owns the general formulation, inventory and price-attribution method; this page owns the Polish feature's source and interpretation.

### Limits

With exports positive, `−import_limit ≤ net_position ≤ export_limit`. A zero export cap still allows net imports. Distinguish a published zero cap, a published positive cap, absent data, and a cap with a binding market effect. A published cap need not bind. The map's binding outline selects market effects; cheaper Polish prices in those selected intervals are not independent evidence of selective cap setting.

JAO Core `allocationConstraint` supplies `limitUp_PL` (export MW) and `limitDown_PL` (import MW), timestamped at UTC delivery-interval starts. Core `netPos.hub_PL` supplies the position. Cross-CCR `DA_PL_AC` supplies the empirically interpreted alternative price used for attribution. See [source responses](country-import-export-caps.md#public-data), [publication coverage](country-import-export-caps.md#publication-coverage) and [adapter validation](country-import-export-caps.md#poland-validation). The May 6, 2026 boundary concerns the alternative-price publication, not the introduction of Polish caps.

The app represents the aggregate constraint as Poland's outline, selected by `cap:PL`. A URL's `interval` is zero-based within `MarketDay`, not a human-numbered quarter-hour. On August 14, 2026, index 85 is 21:15 CEST (zero export cap); index 86 is 21:30 CEST (570 MW). Use UTC interval identity when joining sources, including clock-change days.

### Reserves

PSE's rationale concerns generation and reserve feasibility as well as transmission limits. [Pre-day-ahead procurement](polish-balancing-capacity-procurement.md#procurement) provides a check on that explanation. It does not reproduce the original cap calculation. The [investigation](polish-export-cap-investigation.md) owns case evidence and the unresolved security/welfare questions; [Article 7 safeguards](literature/core-da-ccm-allocation-constraint-safeguards.md) cover effectiveness and alternatives.

Upward requirements and purchases contextualize an **export** cap. They do not explain an import cap's downward-reserve rationale.
