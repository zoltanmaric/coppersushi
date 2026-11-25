# Price model

[Forecasts](../README.md) · [Inputs](../inputs/README.md) · [Evaluation](../evaluation/README.md)

[build_features() and build_day_features()](features.py) use the same transforms for historical fitting and daily issuance. They turn eligible DE–LU auction prices into same-clock price lags, daily price summaries, fixed Berlin calendar fields, and flags for missing inputs. [Price lags](price_features.py) average repeat quarters when the clocks change in autumn. A spring lag quarter that did not occur stays empty.

[fit_month()](training.py) fits the CatBoost quantile model and [seasonal reference](reference.py) with labels available at that month’s first issue. [predict_day()](prediction.py) uses the saved fit to produce five price quantiles from each method and records raw model quantile crossings.

[Fit and issue from the command line](../README.md#on-demand-day-ahead-forecast). See the [evaluation contract](../../wiki/price-forecasting/evaluation.md#defaults) for the completeness checks applied before fit and issuance.
