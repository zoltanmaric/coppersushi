"""Require complete inputs for registered historical forecasts."""
from collections.abc import Iterable, Mapping
from datetime import date, datetime, timedelta
from functools import cache

from pandera.typing.polars import DataFrame
import polars as pl

from forecasts.dataset import BERLIN, quarters
from forecasts.input_config import WEATHER_FIELDS
from forecasts.prices import PRICE_FEATURES
from forecasts.tables import Features, MISSING_FIELDS, Predictions, SOURCE_FLAGS


STATIC_INPUT_POLICY = "complete_historical_inputs_v1"


def require_quarters(actual: Iterable[datetime], start: date, end: date, evidence: str) -> None:
    """Require exactly the physical Berlin delivery quarters in the period."""
    observed = list(actual)
    expected = set(quarters(start, end))
    actual_set = set(observed)
    missing = expected - actual_set
    unexpected = actual_set - expected
    duplicates = len(observed) - len(actual_set)
    if missing or unexpected or duplicates or not expected:
        raise ValueError(
            f"{evidence} for {start} through {end - timedelta(days=1)}: "
            f"{len(missing)} missing quarters{_example(missing)}, "
            f"{len(unexpected)} unexpected quarters{_example(unexpected)}, {duplicates} duplicates"
        )


def require_realised_prices(truth: Mapping[datetime, float | None], start: date, end: date) -> None:
    """Check that a registered scoring period has every realised price."""
    require_quarters((timestamp for timestamp in quarters(start, end) if truth.get(timestamp) is not None),
                     start, end, "Realised SMARD prices for scoring")


def require_static_features(rows: DataFrame[Features], start: date, end: date) -> None:
    """Require price lags, weather and demand, allowing nonexistent DST clocks."""
    require_quarters(rows["delivery_utc"], start, end, "Historical feature delivery grid")
    required = [*PRICE_FEATURES, *WEATHER_FIELDS, "demand_mw"]
    missing = rows.filter(pl.any_horizontal(pl.col(required).is_null()))
    for row in missing.select("delivery_utc", "delivery_date", "quarter_of_day", "demand_screen", *required).iter_rows(named=True):
        for name in required:
            if row[name] is not None:
                continue
            if _structural_lag_gap(name, row["delivery_date"], row["quarter_of_day"]):
                continue
            if name == "demand_mw":
                source = "demand archive"
            else:
                source = "ICON-EU weather" if name in WEATHER_FIELDS else "SMARD prices"
            evidence = f"; demand screen={row['demand_screen']}" if name == "demand_mw" else ""
            raise ValueError(
                f"Missing eligible {source} input {name} for {row['delivery_date']} "
                f"at {row['delivery_utc'].isoformat()} (UTC delivery){evidence}"
            )
    for flag in SOURCE_FLAGS:
        unavailable = rows.filter(pl.col(flag) == 1)
        if not unavailable.is_empty():
            raise ValueError(f"Historical source unavailable: {flag} for {unavailable['delivery_date'][0]}")


def require_recorded_inputs(rows: DataFrame[Predictions]) -> None:
    """Reject missing inputs recorded during prediction before starting scoring."""
    flags = [*MISSING_FIELDS, "demand_missing", *SOURCE_FLAGS]
    missing = rows.filter(pl.any_horizontal(pl.col(flags) == 1) | (pl.col("demand_available") == 0))
    for row in missing.select("delivery_date", "delivery_utc", "demand_available", *flags).iter_rows(named=True):
        local = row["delivery_utc"].astimezone(BERLIN)
        day = row["delivery_date"]
        quarter = local.hour * 4 + local.minute // 15
        for flag in flags:
            name = flag.removesuffix("_missing")
            if row[flag] and not _structural_lag_gap(name, day, quarter):
                raise ValueError(f"Static scoring rejects missing input {name} on {day} at {row['delivery_utc']}")
        if not row["demand_available"]:
            raise ValueError(f"Static scoring rejects unavailable demand on {day} at {row['delivery_utc']}")


def _structural_lag_gap(name: str, day: date, quarter: int) -> bool:
    if not name.startswith("price_lag_"):
        return False
    lag_day = day - timedelta(days=int(name.removeprefix("price_lag_")))
    return quarter not in _local_quarters(lag_day)


@cache
def _local_quarters(day: date) -> set[int]:
    local = (timestamp.astimezone(BERLIN) for timestamp in quarters(day, day + timedelta(days=1)))
    return {timestamp.hour * 4 + timestamp.minute // 15 for timestamp in local}


def _example(timestamps: set[datetime]) -> str:
    return f" (first {min(timestamps).isoformat()} UTC)" if timestamps else ""
