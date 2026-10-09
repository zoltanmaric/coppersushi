# Forecasts

Germany–Luxembourg day-ahead price forecasting. Start with the [wiki handover](../wiki/price-forecasting/germany-luxembourg.md) and [implementation spec](../wiki/specs/day-ahead-price-forecast.md).

As of 2026-10-09 this directory contains diagnostic evidence, not a runnable daily forecasting service. No installation command is claimed yet; the implementation should add its own reproducible dependency setup and commands here.

[Evidence](evidence/README.md) contains reusable collection/audit scripts and compact results. Downloaded inputs are under ignored `data/forecasts/`. The agreed model produces five price quantiles in one CatBoost fit; the wiki owns its design and evaluation contract.
