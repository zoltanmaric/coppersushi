"""Require complete inputs for registered historical forecasts."""
from datetime import date, timedelta
from functools import cache

from pandera.typing.polars import DataFrame
import polars as pl

from forecasts.market import BERLIN, quarters, require_quarters
from forecasts.config import PRICE_FEATURES, PRICE_UNAVAILABLE
from forecasts.model.tables import Features


STATIC_INPUT_POLICY = "complete_price_inputs_v1"


def require_static_features(rows: DataFrame[Features], start: date, end: date) -> None:
    """Require eligible price features except nonexistent spring clock quarters."""
    require_quarters(rows["delivery_utc"], start, end, "Historical feature delivery grid")
    missing = rows.filter(pl.any_horizontal(pl.col(PRICE_FEATURES).is_null()) | (pl.col(PRICE_UNAVAILABLE) == 1))
    for row in missing.iter_rows(named=True):
        day, quarter = row["delivery_date"], row["quarter_of_day"]
        for name in PRICE_FEATURES:
            if row[name] is None and not structural_lag_gap(name, day, quarter):
                raise ValueError(
                    f"Missing eligible SMARD prices input {name} for {day} "
                    f"at {row['delivery_utc'].isoformat()} (UTC delivery)"
                )
        if row[PRICE_UNAVAILABLE]:
            raise ValueError(f"Historical source unavailable: {PRICE_UNAVAILABLE} for {day}")


def structural_lag_gap(name: str, day: date, quarter: int) -> bool:
    """Check for a same-clock lag quarter skipped by a daylight-saving transition."""
    if not name.startswith("price_lag_"):
        return False
    lag_day = day - timedelta(days=int(name.removeprefix("price_lag_")))
    return quarter not in _local_quarters(lag_day)


@cache
def _local_quarters(day: date) -> set[int]:
    local = (timestamp.astimezone(BERLIN) for timestamp in quarters(day, day + timedelta(days=1)))
    return {timestamp.hour * 4 + timestamp.minute // 15 for timestamp in local}
