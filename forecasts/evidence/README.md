# Forecast diagnostic evidence

Recorded findings from the completed 2026-10-07–08 investigations. [Data findings](../../wiki/price-forecasting/data-sources.md) explain their scope. Maintained code does not read this directory.

The experiment design and JSON/CSV results remain historical evidence. Operational weather coordinates live in [input configuration](../input_config.py); the three source archives are pinned in the [baseline input inventory](../data/baseline-inputs.json). Baseline coverage expectations belong to the [regression fixture](../tests/fixtures/baseline-coverage.json), checked only against its named snapshot.

## Historical reproduction

The scripts are preserved at revision `155627ea6a8cc2bf542a48fea7aad59253f59de6`:

- [Price/weather collection](https://github.com/zoltanmaric/coppersushi/blob/155627ea6a8cc2bf542a48fea7aad59253f59de6/forecasts/evidence/forecast-bounded-evidence-20261007/collect.py).
- [Point-model measurement](https://github.com/zoltanmaric/coppersushi/blob/155627ea6a8cc2bf542a48fea7aad59253f59de6/forecasts/evidence/forecast-bounded-evidence-20261007/measure.py).
- [Demand timing audit](https://github.com/zoltanmaric/coppersushi/blob/155627ea6a8cc2bf542a48fea7aad59253f59de6/forecasts/evidence/demand-recovery-evidence-20261008/audit.py).
- [Weather compatibility check](https://github.com/zoltanmaric/coppersushi/blob/155627ea6a8cc2bf542a48fea7aad59253f59de6/forecasts/evidence/weather-compatibility-evidence-20261008/check.py).

Use that revision's [instructions](https://github.com/zoltanmaric/coppersushi/blob/155627ea6a8cc2bf542a48fea7aad59253f59de6/forecasts/evidence/README.md) and [payload manifest](https://github.com/zoltanmaric/coppersushi/blob/155627ea6a8cc2bf542a48fea7aad59253f59de6/forecasts/evidence/payload-manifest.json) to reproduce those investigations. Downloaded inputs remain outside Git; a source re-download can differ from the recorded archive. The old point-model filtering and scoring are not the [five-quantile evaluation contract](../../wiki/price-forecasting/evaluation.md).
