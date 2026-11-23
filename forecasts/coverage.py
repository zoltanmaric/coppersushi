"""Require complete inputs for registered historical forecasts."""
from collections.abc import Iterable, Mapping
from datetime import date, datetime, timedelta
from functools import cache

from pandera.typing.polars import DataFrame
import polars as pl

from forecasts.dataset import BERLIN, quarters
from forecasts.prices import PRICE_FEATURES
from forecasts.tables import Features, PRICE_MISSING_FIELDS, PRICE_UNAVAILABLE, Predictions


STATIC_INPUT_POLICY = "complete_price_inputs_v1"


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
    """Require eligible price features except nonexistent spring clock quarters."""
    require_quarters(rows["delivery_utc"], start, end, "Historical feature delivery grid")
    missing = rows.filter(pl.any_horizontal(pl.col(PRICE_FEATURES).is_null()) | (pl.col(PRICE_UNAVAILABLE) == 1))
    for row in missing.iter_rows(named=True):
        day, quarter = row["delivery_date"], row["quarter_of_day"]
        for name in PRICE_FEATURES:
            if row[name] is None and not _structural_lag_gap(name, day, quarter):
                raise ValueError(
                    f"Missing eligible SMARD prices input {name} for {day} "
                    f"at {row['delivery_utc'].isoformat()} (UTC delivery)"
                )
        if row[PRICE_UNAVAILABLE]:
            raise ValueError(f"Historical source unavailable: {PRICE_UNAVAILABLE} for {day}")


def require_recorded_inputs(rows: DataFrame[Predictions]) -> None:
    """Reject missing inputs recorded during prediction before starting scoring."""
    flags = [*PRICE_MISSING_FIELDS, PRICE_UNAVAILABLE]
    missing = rows.filter(pl.any_horizontal(pl.col(flags) == 1))
    for row in missing.select("delivery_date", "delivery_utc", *flags).iter_rows(named=True):
        local = row["delivery_utc"].astimezone(BERLIN)
        day = row["delivery_date"]
        quarter = local.hour * 4 + local.minute // 15
        for flag in flags:
            name = flag.removesuffix("_missing")
            if row[flag] and not _structural_lag_gap(name, day, quarter):
                raise ValueError(f"Static scoring rejects missing input {name} on {day} at {row['delivery_utc']}")


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
