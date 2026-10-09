# Energy-Arena forecast benchmarks

API evidence checked 2026-10-09. **`Eiser_et_al_2026`** is the clearest documented fundamentals match for the [forecast contract](germany-luxembourg.md), but its history is short. **`BerriJ`** has the best verified longer coverage among the non-naive candidates checked at 11:00; its model and inputs are undocumented. Retain the [local distributional reference](evaluation.md#reference) for the full backtest.

## Match

Challenge 8 covers Germany–Luxembourg quarter-hour day-ahead prices in EUR/MWh, with our five quantiles and [weighted interval score](evaluation.md#wis). Its deadline is 12:00 German local time; `information_cutoff_offset_minutes_before_deadline=60` selects our 11:00 comparison. [Catalog](https://energy-arena.org/challenges), [API schema](https://api.energy-arena.org/openapi.json).

Eiser's pre-11:00 model uses historical prices, ENTSO-E load forecasts and DWD ICON-D2 weather. Lasso Estimated AutoRegressive point models feed Simple Quantile Regression Averaging. Code and collected weather histories are public. After 11:00 the participant switches to an EXAA-only model using early auction prices: do not use the default leaderboard or latest submission. [Model repository](https://github.com/GitMoritzraab/Operational-Forecasting-Pipeline-for-Day-Ahead-Electricity-Prices), [leaderboard](https://energy-arena.org/leaderboard).

## History

Observed on 2026-10-09:

| Participant | Accessible history | Fit |
|---|---|---|
| `Eiser_et_al_2026` (107) | 39 versions, 22 delivery dates, September 18–October 10; 20 completed dates eligible by 11:00 | Best fundamentals match; only 12 eligible dates overlap our proposed January–September backtest |
| `LeForecastJames` (10) | 189 delivery dates, March 28–October 10; 188 evaluated | EXAA-price proxy; usually submitted after 11:00 |
| `BerriJ` (6) | 170 complete delivery days, April 22–October 9, at 11:00; 16,320 quarter-hours | Longer external comparison; model and inputs undocumented |
| `TelescopeEnergy` (12) | 100 complete delivery days, March 24–October 9, at 11:00; 9,600 quarter-hours | Only three dates before July; sustained coverage is concentrated in July–October |
| `NaiveBenchmark` (1) | 267 complete delivery days, January 15–October 9, at 11:00; 25,628 quarter-hours | Long simple check; reference construction differs from ours |

Eiser's completed eligible dates run September 18–October 8, missing September 25. October 9 has no pre-11:00 version; October 10 has an eligible but unevaluated submission. All 1,920 completed eligible quarter-hours match the API's 11:00 chart selection exactly. This corroborates interpreting the feed's offset-free `submitted_at` as UTC for these records.

The 11:00 leaderboard reports Eiser WIS **16.78 EUR/MWh**, median MAE **27.40 EUR/MWh**, 50% coverage **42.76%**, and 95% coverage **93.44%**, on 20 targets. Its default 12:00 WIS is 9.69 on 21 targets. These are provider scores, not independent recomputations. Compare identical dates locally; participant aggregates have different coverage.

The longer histories were downloaded in ten contiguous chart windows covering January 15–October 9. BerriJ and NaiveBenchmark cover every day between their first and last returned dates except July 12, excluded by Energy-Arena for a platform outage. All returned days have the full physical quarter-hour count and five finite ordered quantiles. The 180-target 11:00 leaderboard gives BerriJ WIS 18.23 on 170 targets and TelescopeEnergy 39.22 on 99 targets; these differing date populations cannot be ranked fairly against Eiser's 20 dates. EPFTeam has 25 eligible days from September 12–October 8; Simon_Electricity only six, May 6–13. Raw windows and counts are retained under ignored `data/forecasts/energy-arena-tenure-20261009/`.

## Retrieval

### Validation

A fresh 2026-10-09 download contains 308,063 bytes, 3,744 quarter-hour rows and 18,720 quantile values across all 39 versions. Every version has the exact five quantile levels, finite ordered values, EUR/MWh units and a complete UTC delivery grid with 15-minute spacing. Selecting one eligible version per day leaves 2,016 rows; 1,920 are evaluated, and 1,152 overlap January–September. Raw response, normalized CSV and validation summary are retained under ignored `data/forecasts/energy-arena-check-20261009/`.

Our five-quantile CatBoost forecast is specified but not implemented as of this check. The saved preliminary diagnostic contains point forecasts, so it cannot yet be compared on weighted interval score. Future quantile outputs can join this benchmark on UTC delivery timestamp and be scored against identical truth.

Base: `https://api.energy-arena.org`; cooperative feed authentication: `X-API-Key`.

```text
GET /api/v1/public-forecasts?challenge_id=8
    &participant_name=Eiser_et_al_2026&history=true&limit=500&offset=0
```

Retains submission IDs, times, target starts, quantile levels and timestamped values, including multiple versions per target. Paginate using `total_count`, `returned_count`, `limit` and `offset`. Select the latest version by the preceding day's 11:00 cutoff. The live feed can select the later EXAA version.

The feed labels data CC BY 4.0. History requires a publicly visible profile set to **Open immediately**; archive versions with retrieval metadata and attribution. Evaluation-only profiles return no cooperative history. [Guide](https://energy-arena.org/participate), [visibility rules](https://energy-arena.org/faq).

A separate chart endpoint exposes evaluated trajectories, including evaluation-only profiles:

```text
GET /api/v1/leaderboard/timeseries?challenge_id=8&area=DE_LU
    &participant_ids=107,1&information_cutoff_offset_minutes_before_deadline=60
    &window_start=<ISO8601>&window_end=<ISO8601>
    &forecast_window_start=<ISO8601>&forecast_window_end=<ISO8601>&forecast_days=30
```

Read `quantile_points`, not just median `points`. Check returned timestamps; chart bounds can differ from the scoring window. The longer-history check joins contiguous windows and counts only timestamps inside each requested delivery range. Coverage before January 15 was not requested. Chart truth is SMARD; official scores use ENTSO-E. Use our identical frozen truth for all comparisons. [Schema](https://api.energy-arena.org/openapi.json), [chart rules](https://energy-arena.org/faq).

This finding does not change first-build acceptance criteria or authorize competition entry.
