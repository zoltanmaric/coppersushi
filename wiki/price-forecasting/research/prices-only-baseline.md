# Selected price-history baseline

Decision on 23 November 2026, before execution. Can one fixed price-history and Berlin-calendar model improve weighted interval score (WIS) over the existing seasonal reference? This run establishes a reproducible comparison. A negative result is informative.

Use the immutable snapshot and exact CatBoost settings in [the run configuration](../../../forecasts/run-config.json). History starts 1 October 2025. Train from 15 October, refit on expanding history before each evaluation month, and forecast every delivery day from 1 January through 30 September 2026. Use only price versions eligible by 11:00 Europe/Berlin on the previous day and labels available at fit time. Historical price availability is partly assumed. Require complete price inputs, training labels, model predictions and scoring outcomes. Stop on a gap.

Compare the five sorted price quantiles with the seasonal reference on identical delivery quarters. Report pooled and monthly WIS, median error, coverage and interval widths. Keep the result regardless of which method wins. Preserve the frozen plan, snapshot, code, models and scores with the execution.

Defer weather and demand comparisons. To revisit demand, first establish which revisions were available by issue time and preselect matched dates. Moving the issue cutoff or changing the evaluation window defines a new experiment. The invalidated autumn replay supplies no demand-quality evidence.
