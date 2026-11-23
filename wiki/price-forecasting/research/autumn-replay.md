# Frozen model on October and November 2026

Selected November 23 at the user's request. Test whether the existing system retains its WIS advantage over its distributional reference on later dates. The [baseline review](baseline-review.md) motivates this check. Keep settings fixed and defer calibration and model changes until after scoring. Prospective issuance is a separate check.

Predict October 1 through November 23 inclusive at each preceding Berlin 11:00 cutoff. Fit October from eligible labels before October 1 and reuse the saved November fit. Use the November 23 input snapshot. Keep missing demand and missing outcomes visible. Score both methods on identical observed quarters. Report pooled and monthly WIS, median MAE, central 95% width, coverage and lower/upper miss rates. Lower pooled system WIS supports the hypothesis for this period. Report reversals by month. Cost is one monthly fit and 54 daily predictions. This is a historical reconstruction under the recorded source timing assumptions.

## Invalid experiment — collection omitted demand

The run completed computationally but failed to test the intended system. The refresh script requested prices and weather only. An unsuccessful REST probe did not establish that the historical country demand forecast was unavailable for the entire period. The November fit also used that incomplete October history. The scores below describe a weather-only diagnostic. Withdraw the conclusion about the intended system.

| Period | Scored quarters | System WIS | Reference WIS | System 95% coverage | Reference 95% coverage | System width | Reference width |
|---|---:|---:|---:|---:|---:|---:|---:|
| October | 2,980 | 23.35 | 31.98 | 58.5% | 82.0% | 90.76 | 175.80 |
| November | 2,016 | 26.97 | 35.89 | 47.5% | 78.8% | 62.12 | 188.92 |
| Pooled | 4,996 | 24.81 | 33.56 | 54.0% | 80.7% | 79.20 | 181.10 |

System WIS was 26.1% lower than the reference. Median MAE was 35.17 versus 53.36 €/MWh. Actuals fell below the system interval on 16.6% of scored quarters and above it on 29.3%.

The system used the weather fallback on all 54 days. November 20 and 21 each lack all 96 realised prices. See MLflow execution `1f3699041bea421680bc01cbb18f39df` for the snapshot and fit manifests, daily forecasts, and scores. Historical availability is assumed. This replay supplies no prospective evidence.

Repeat the input audit, fit from corrected eligible training inputs and rerun the full replay. Stop on unexpected gaps or model failures. Record evidence and obtain a specific decision for any upstream exception before scoring.

### Deferred full-input rerun

The [selected baseline](prices-only-baseline.md) has a different scope. The steps below apply if the full-input experiment resumes.

- **Step 1, collection.** Verify the required price, weather and German country demand versions across training, warmup and evaluation. Record exact missing dates, fields, cutoffs and retrieval evidence. A failed HTTP request is insufficient evidence for an upstream exception.
- **Step 2, earlier baseline.** Reproducing stored predictions establishes computational parity. The strict full-input baseline needs new fits: each of its nine training windows included missing demand, and 28 evaluation days selected weather. Historical results retain their original missing-input policy.
- **Step 3, daily forecast.** Retire the November fit and November 24 reconstruction as evidence for the intended system. Refit after repairing October and earlier training history, then repeat the known-day and November checks. The November 24 issue deadline has passed.
- **Step 4, autumn replay.** Retain the frozen model settings, dates and metrics. Rebuild the October and November fits. Require the intended inputs and successful models for every forecast, and observed truth for scoring. Stop before reporting metrics when a requirement fails. Any exception needs source evidence, an explicit scope and a separate decision.

The saved September demand file and the autumn extension contain the same demand Parquet bytes. The October fit used 33,696 training quarters, including 5,472 missing demand values. The November fit used 36,676, including 8,452 missing demand values. All 2,980 new October quarters lacked demand. Exact agreement with the old November reconstruction does not validate those inputs.
