# Sushi 2 pre-registration

Validation criteria for the first full computation of 2026-08-12, stated **before** that computation runs. This page is durable: it survives the spec's burn-down and results are reported against it verbatim.

**Stated prior: <50% expectation that flows reproduce reality on first computation.** Anticipated cause: incomplete/incorrect grid data (topology, capacities, impedances).

## Criteria

- **(a) Plumbing check** (bug detector, *not* reportable success — holds near-by-construction): per-zone hourly energy balances reproduce ENTSO-E zone totals within **1%**.
- **(b) The genuine test** (falsifiable — measured cross-border physical flows are constrained nowhere in the pipeline): simulated vs ENTSO-E measured physical flows on **ES–FR** and **FR–DE**, hourly over the day:
  - mean absolute error ≤ **15%** of the corridor's nominal transfer capacity, and
  - flow direction correct in ≥ **90%** of hours.
- **(c) JAO spot-check** (report-only, no pass/fail): computed base-case flows on ~5 named Core critical branches vs JAO's published values, deviations reported.

## Calibration policy

The validating agent may calibrate the model toward observed ES–FR flows where it identifies plausible modeling gaps. Every adjustment is reported individually: what changed, why it is physically defensible, what it implies about the data. **Calibration is a finding, not a failure.** Criterion (b) is reported both pre- and post-calibration.
