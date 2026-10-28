# Forecast diagnostic evidence

Recorded findings from the completed 2026-10-07–08 investigations. [Data findings](../../wiki/price-forecasting/data-sources.md) explain their scope.

This folder contains historical experiment designs and JSON/CSV results. For maintained inputs and baseline checks, see the [forecast setup](../README.md).

## Historical reproduction

The scripts are preserved at revision `155627ea6a8cc2bf542a48fea7aad59253f59de6`:

- [Price/weather collection](https://github.com/zoltanmaric/coppersushi/blob/155627ea6a8cc2bf542a48fea7aad59253f59de6/forecasts/evidence/forecast-bounded-evidence-20261007/collect.py).
- [Point-model measurement](https://github.com/zoltanmaric/coppersushi/blob/155627ea6a8cc2bf542a48fea7aad59253f59de6/forecasts/evidence/forecast-bounded-evidence-20261007/measure.py).
- [Demand timing audit](https://github.com/zoltanmaric/coppersushi/blob/155627ea6a8cc2bf542a48fea7aad59253f59de6/forecasts/evidence/demand-recovery-evidence-20261008/audit.py).
- [Weather compatibility check](https://github.com/zoltanmaric/coppersushi/blob/155627ea6a8cc2bf542a48fea7aad59253f59de6/forecasts/evidence/weather-compatibility-evidence-20261008/check.py).

Historical reproduction: [instructions](https://github.com/zoltanmaric/coppersushi/blob/155627ea6a8cc2bf542a48fea7aad59253f59de6/forecasts/evidence/README.md) and [payload manifest](https://github.com/zoltanmaric/coppersushi/blob/155627ea6a8cc2bf542a48fea7aad59253f59de6/forecasts/evidence/payload-manifest.json). Downloaded inputs remain outside Git; a source re-download can differ from the recorded archive.
