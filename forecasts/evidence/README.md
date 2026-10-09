# Forecast diagnostic evidence

Reusable checks from 2026-10-07–08. These are recorded diagnostics, not the production pipeline or the five-quantile model's results. [Data findings](../../wiki/price-forecasting/data-sources.md) explain their scope.

| Directory | Contents |
|---|---|
| `forecast-bounded-evidence-20261007/` | Collection/measurement scripts, locations/settings, scores and input hashes for the expanded weather comparison |
| `demand-recovery-evidence-20261008/` | Monthly-extract audit, full-year summary and daily/monthly coverage counts |
| `weather-compatibility-evidence-20261008/` | Historical/future compatibility counts and replay check |

The matching downloaded payloads live in ignored `data/forecasts/evidence/`, with the same directory names. The local tree also contains copies of these scripts so their relative paths work. `data/forecasts/entsoe-files.zip` contains the thirteen monthly demand extracts. [Payload manifest](payload-manifest.json) records relative paths, sizes and SHA-256 hashes. A fresh clone needs these public-source downloads; they are not Git assets.

From the repository root, after installing the diagnostic dependencies:

```sh
# Fast replay of saved weather compatibility; Python standard library only.
python data/forecasts/evidence/weather-compatibility-evidence-20261008/check.py

# Demand timing audit; requires pandas.
python forecasts/evidence/demand-recovery-evidence-20261008/audit.py data/forecasts/entsoe-files.zip --output data/forecasts/demand-audit
```

To reproduce the historical weather experiment, extract its `inputs.zip` beside its local `measure.py`, then run that script. Recorded dependencies: NumPy 1.26.4, pandas 2.2.3, CatBoost 1.2.10. Follow the repository's long-job workflow before launching a refit. Its collector can re-download public weather and price inputs, but snapshots remain the authority for the reported results.

Do not transplant the old experiment's complete-day filtering, absolute-error objective or bootstrap across calendar gaps into the new model. The [new evaluation contract](../../wiki/price-forecasting/evaluation.md) requires all dates, five quantiles and contiguous-day comparisons. Aggregate files contain forecast research results, not provider credentials or authenticated forecast values.
