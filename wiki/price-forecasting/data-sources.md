# Day-ahead forecast data

Data contract for the [price forecast](germany-luxembourg.md). Checks below were completed on 2026-10-01–08. Small scripts and results are in [forecast evidence](../../forecasts/evidence/README.md); downloaded inputs are local under ignored `data/forecasts/`.

### Prices

[SMARD's Germany–Luxembourg price feed](https://www.smard.de/app/chart_data/4169/DE/index_quarterhour.json), filter `4169`, provides the weekly quarter-hour series. The diagnostic collector records the exact requests. October 2025–September 2026 contains 35,040 quarter-hours with native market resolution. Attribute Bundesnetzagentur | SMARD.de.

Keep negative prices. Use only auction results already available at forecast issue time. Candidate lags from the diagnostic: the same local-clock quarter 1, 2, 7 and 14 days earlier; previous-day/week mean, minimum and maximum. Publication latency of the public price feed was not independently audited. Define clock-change lag handling rather than assuming each local day has 96 rows.

### Weather

Provider: [Open-Meteo Previous Runs](https://open-meteo.com/en/docs/previous-runs-api), German Weather Service `icon_eu`, explicit model selection. Historical and upcoming delivery dates use **the same endpoint and fields**:

```text
https://previous-runs-api.open-meteo.com/v1/forecast
models=icon_eu
hourly=temperature_2m_previous_day2,wind_speed_120m_previous_day2,shortwave_radiation_previous_day2
timezone=UTC
timeformat=unixtime
```

Add latitude/longitude lists and an inclusive UTC `start_date`/`end_date` wide enough to enclose the German local delivery day. Temperature is °C, wind is km/h at 120 metres, radiation is W/m². Hourly weather is repeated over delivery quarters. Radiation timestamps describe the preceding hour: shift them back one hour and fetch the additional ending timestamp.

`previous_day2` is documented as a fixed 48-hour lead for each valid hour. Do not replace it with latest-run weather for live inference or observed/reanalysis weather for training. It provides substantial normal-delivery margin before the preceding-day 11:00 deadline, but original historical publication times have not been recovered. Snapshot actual daily retrieval times before the deadline.

The 2026-10-08 compatibility check returned all 24 aligned October 9 delivery hours for every field at every point, with identical historical/future units, grid coordinates and elevations. The historical year has 8,760 hourly timestamps at each point; temperature is complete, while wind and radiation each lack 95 hours during April 7–11. All 158,112 overlapping field values matched the earlier saved snapshot. The request occurred at 17:39 UTC, so this is not a witnessed pre-11:00 fetch. [Counts](../../forecasts/evidence/weather-compatibility-evidence-20261008/summary.json), [replay script](../../forecasts/evidence/weather-compatibility-evidence-20261008/check.py).

### Locations

Starting coordinates, from the [diagnostic design](../../forecasts/evidence/forecast-bounded-evidence-20261007/design.json):

| Location | Latitude | Longitude |
|---|---:|---:|
| Hamburg | 53.55 | 9.99 |
| Essen | 51.45 | 7.01 |
| Munich | 48.14 | 11.58 |
| Emden | 53.37 | 7.21 |
| Husum | 54.48 | 9.05 |
| Rostock | 54.09 | 12.14 |
| Magdeburg | 52.13 | 11.63 |
| Berlin | 52.52 | 13.41 |
| Leipzig | 51.34 | 12.37 |
| Frankfurt | 50.11 | 8.68 |
| Stuttgart | 48.78 | 9.18 |
| Nuremberg | 49.45 | 11.08 |

All select distinct grid cells. Nearest selected neighbours are about 104–188 km apart. This is broad manual coverage, not generation-capacity weighting; offshore points are absent. More points increase geographical detail but also correlated features. Twelve-location superiority over a larger set has not been tested.

### Demand

Source: ENTSO-E File Library monthly `DayAheadTotalLoadForecast_6.1.B_r3` extracts. Use **Germany country `10Y1001A1001A83F`**, not Germany–Luxembourg zone `10Y1001A1001A82H`. This is a country-demand feature for a zonal-price target, not a claim that the areas are identical. The [extract schema](https://transparencyplatform.zendesk.com/hc/en-us/articles/36492900251281-DayAheadTotalLoadForecast-6-1-B-r3) includes `DateTime(UTC)`, `UpdateTime(UTC)`, `TotalLoad[MW]`, `AreaCode` and `ResolutionCode`. Login is needed for the [File Library](https://transparencyplatform.zendesk.com/hc/en-us/articles/35960137882129-File-Library-Guide).

For each delivery date, compute the preceding date's **11:00 Europe/Berlin**, then convert to UTC. A value is usable only when it exists and `UpdateTime(UTC)` is no later than that cutoff. A later update does not reveal its earlier value. This screen is conditional on the timestamp's meaning; it is not a complete audit of original public availability.

Full-year result: 35,040 country values, no duplicate/missing target rows; 28,224 (80.55%) pass the screen. All 71 affected days fail for the entire day: October 1–November 11, then 29 later dates. From November 12, 294/323 days pass (91.03%). The four control-area series cannot repair any country gap under the same screen. [Audit](../../forecasts/evidence/demand-recovery-evidence-20261008/audit.py), [summary](../../forecasts/evidence/demand-recovery-evidence-20261008/summary.json), [daily counts](../../forecasts/evidence/demand-recovery-evidence-20261008/daily-coverage.csv).

Bounded attempts through documented requests, legacy exports, an Amprion CSV and signed-in value history did not recover usable earlier versions for the checked problematic samples. This is not proof that no earlier version exists. Do not repeat broad archive/provider research before fitting the agreed missing-demand model.

Retain the price rows and represent unusable demand as missing plus its availability indicator. In daily operation, save the forecast actually retrieved before the cutoff; later revisions must not overwrite that input snapshot.

### Availability

The historical inputs do not establish a fully verified 11:00 replay. Weather publication times and price-feed latency are unaudited; the demand update-time screen depends on the timestamp's meaning. Reports must distinguish documented timing assumptions from witnessed availability. A proposed next check is to save inputs retrieved before 11:00 while the historical experiment is built.

A rejected demand value does not prove that no forecast was available on time: a later revision may have replaced it in the archive. The missing-demand indicator can therefore reflect archive behaviour or a calendar period. Using identical missing-value code in replay and daily operation does not remove that difference. The [feature comparisons](evaluation.md#controls) measure whether demand helps under this historical screen; they do not prove that the same gain will hold live.

### Diagnostics

The October 7 point-model experiment evaluated 126 days, June–October 5, with expanding monthly training and three seeds. Average absolute error was €24.24/MWh for fixed-lead weather versus €24.07 for preceding-morning weather: 0.68%, inconsistent across seeds, with every paired uncertainty interval including zero. In the one-seed matched comparison, twelve versus three locations reduced error 6.1% with older weather and 4.8% with fresher weather. [Results](../../forecasts/evidence/forecast-bounded-evidence-20261007/measurement.json), [averages](../../forecasts/evidence/forecast-bounded-evidence-20261007/aggregate.json).

Limits: no winter evaluation; August–September had already been inspected; point forecasts and absolute-error training, not the agreed quantile model. Complete-day filtering removed weather/clock-lag gaps; its bootstrap could bridge the missing June 12. Those choices are historical experiment details, **not** the new [all-date evaluation contract](evaluation.md). No commercial comparison or new quantile accuracy result exists.
