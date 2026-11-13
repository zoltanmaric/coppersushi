# PSE allocation-constraint assessment Q4 2025

**Source:** PSE, *Analysis of Polish Allocation Constraints: Comparison of historical data and NoAC simulations*, Q4 2025, 11 slides. Embedded PDF in “Annex I – Q4_2025_Allocation constraints.docx” inside [JAO’s quarterly archive](https://www.jao.eu/sites/default/files/2026-03/Core%20DA_CC_Q4_2025_report.zip), listed 24 March 2026. Extracted and read 2026-11-12; slides 6, 7 and 10 visually checked.

### Assessment

PSE reruns market clearing with only Polish [allocation constraints](../core-day-ahead-capacity-calculation.md#allocation-constraint) removed, then compares reserves against thresholds of 1,000 MW upward and 500 MW downward. It values demand curtailment at €3,000/MWh and renewable curtailment at €120/MWh, the quarter’s average compensation.

| No-cap scenario versus historical clearing | PSE result |
|---|---:|
| Core consumer + producer surplus | +€3.91m |
| Polish consumer + producer surplus | +€5.46m |
| Other Core zones combined | −€1.55m |
| Additional renewable curtailment | 118.6 GWh |
| Additional demand curtailment | 0.046 GWh |
| Renewable-curtailment compensation | €14.22m |
| Intervals requiring remedial measures | 12.4% |

PSE reports binding caps in 30.96% of quarter-hour intervals. The simulated security problem is mainly insufficient downward reserves, so this quarter does not by itself explain a particular export cap in November 2026.

### Limits

The counterfactual removes caps; it does not optimise alternative reserve procurement, flexibility or energy–reserve co-optimisation. The deck reports aggregate surplus and a reserve-shortfall plot, rather than a reproducible interval-by-interval calculation of inputs, alternatives and results. Congestion-income changes are handled separately; the surplus table is not a complete account of every welfare component. Compensation is the stated curtailment valuation, not an independently verified estimate of net economic loss. Slide 10 labels the −€1.55m finding “Q4 2024”; slides 6 and 11 establish it belongs to Q4 2025.

See [safeguards and oversight](core-da-ccm-allocation-constraint-safeguards.md#oversight) for what regulatory review is publicly documented.
