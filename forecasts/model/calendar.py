"""Berlin delivery clocks and calendar inputs for the price model."""
from datetime import date, timedelta

from pandera.typing.polars import DataFrame
import polars as pl

from forecasts.market import BERLIN, cutoff
from forecasts.config import CALENDAR_COLUMNS, LAGS, PRICE_FEATURES, PRICE_UNAVAILABLE
from forecasts.model.price_features import PriceFeatures
from forecasts.model.tables import Features

CLOCK_COLUMNS = ("delivery_utc", "delivery_date", "issue_cutoff_utc", "utc_offset_minutes", "clock_fold")


def assemble_price_calendar(price_features: DataFrame[PriceFeatures]) -> pl.DataFrame:
    """Add Berlin delivery clocks, calendar values and price coverage flags."""
    timestamps = price_features["delivery_utc"].to_list()
    local_times = [timestamp.astimezone(BERLIN) for timestamp in timestamps]
    holiday_dates = set().union(*(holidays(year) for year in {local.year for local in local_times}))
    deadlines = {day: cutoff(day) for day in {local.date() for local in local_times}}
    rows = []
    for local in local_times:
        day = local.date()
        deadline = deadlines[day]
        offset = local.utcoffset()
        assert offset is not None  # local is explicitly Europe/Berlin-aware.
        rows.append({
            "delivery_date": day, "issue_cutoff_utc": deadline, "utc_offset_minutes": int(offset.total_seconds() / 60),
            "clock_fold": local.fold, "quarter_of_day": local.hour * 4 + local.minute // 15,
            "day_of_week": local.weekday(), "month": local.month, "public_holiday": int(day in holiday_dates),
            "price_timing_assumed": 1,
        })
    columns = Features.to_schema().columns
    schema = {name: columns[name].dtype.type for name in (*CLOCK_COLUMNS[1:], *CALENDAR_COLUMNS, "price_timing_assumed")}
    return price_features.hstack(pl.DataFrame(rows, schema=schema)).with_columns(
        *[pl.col(name).is_null().cast(pl.Int64).alias(name + "_missing") for name in PRICE_FEATURES],
        pl.all_horizontal(pl.col([f"price_lag_{day}" for day in LAGS]).is_null())
        .all().over("delivery_date").cast(pl.Int64).alias(PRICE_UNAVAILABLE),
    )


def holidays(year: int) -> set[date]:
    """Return nationwide German holidays for the supplied year."""
    # Gregorian Easter (Meeus/Jones/Butcher).
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    easter = date(year, (h + l - 7 * m + 114) // 31, (h + l - 7 * m + 114) % 31 + 1)
    return {date(year, month, day) for month, day in [(1, 1), (5, 1), (10, 3), (12, 25), (12, 26)]} | {
        easter + timedelta(days=offset) for offset in [-2, 1, 39, 50]
    }
