from datetime import UTC, date, datetime

import pandas as pd

from coppersushi.market_day import MARKET_TZ, MarketDay


def test_a_summer_day_starts_at_22z_the_day_before():
    day = MarketDay.on("2024-08-29")
    assert day.start_time_utc == datetime(2024, 8, 28, 22, tzinfo=UTC)
    assert day.end_time_utc == datetime(2024, 8, 29, 22, tzinfo=UTC)


def test_a_winter_day_starts_at_23z_the_day_before():
    day = MarketDay.on("2024-01-15")
    assert day.start_time_utc == datetime(2024, 1, 14, 23, tzinfo=UTC)
    assert day.end_time_utc == datetime(2024, 1, 15, 23, tzinfo=UTC)


def test_a_normal_day_has_24_hours():
    assert len(MarketDay.on("2024-08-29").hours()) == 24


def test_the_spring_forward_day_has_23_hours():
    assert len(MarketDay.on("2024-03-31").hours()) == 23


def test_the_autumn_back_day_has_25_hours():
    assert len(MarketDay.on("2024-10-27").hours()) == 25


def test_hours_are_utc_aware_and_span_the_window():
    day = MarketDay.on("2024-08-29")
    hours = day.hours()
    assert str(hours.tz) == "UTC"
    assert hours[0] == day.start_time_utc
    assert hours[-1] < day.end_time_utc


def test_a_normal_day_has_96_quarter_hours():
    intervals = MarketDay.on("2024-08-29").intervals()
    assert len(intervals) == 96
    assert intervals[1] - intervals[0] == pd.Timedelta(minutes=15)


def test_quarter_hours_follow_the_clock_change():
    assert len(MarketDay.on("2024-03-31").intervals()) == 92
    assert len(MarketDay.on("2024-10-27").intervals()) == 100


def test_market_time_units_follow_the_sdac_transition():
    assert len(MarketDay.on("2024-08-29").market_time_units()) == 24
    assert len(MarketDay.on("2025-09-30").market_time_units()) == 24
    assert len(MarketDay.on("2025-10-01").market_time_units()) == 96
    assert len(MarketDay.on("2026-09-10").market_time_units()) == 96


def test_both_start_times_are_aware_and_name_the_same_instant():
    day = MarketDay.on("2024-08-29")
    assert day.start_time_local.tzinfo is MARKET_TZ
    assert day.start_time_utc.tzinfo is UTC
    assert day.start_time_local == day.start_time_utc
    assert day.start_time_local.hour == 0 and day.end_time_local.hour == 0


def test_a_date_constructs_the_same_day_as_its_iso_string():
    assert MarketDay.on(date(2024, 8, 29)) == MarketDay.on("2024-08-29")


def test_the_day_containing_a_window_start_is_that_day():
    for iso in ("2024-08-29", "2024-01-15", "2024-03-31", "2024-10-27", "2013-07-17"):
        day = MarketDay.on(iso)
        assert MarketDay.containing(day.start_time_utc) == day


def test_an_hour_inside_the_day_still_names_the_day():
    assert MarketDay.containing(datetime(2024, 8, 29, 12, tzinfo=UTC)).date == date(2024, 8, 29)
    assert MarketDay.containing(datetime(2024, 8, 29, 21, 59, tzinfo=UTC)).date == date(2024, 8, 29)
    assert MarketDay.containing(datetime(2024, 8, 29, 22, tzinfo=UTC)).date == date(2024, 8, 30)


def test_containing_reads_a_naive_instant_as_utc():
    assert MarketDay.containing(datetime.fromisoformat("2024-08-28 22:00")).date == date(2024, 8, 29)
