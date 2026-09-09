import pandas as pd

from coppersushi import market_day


def test_a_summer_day_starts_at_22z_the_day_before():
    start, end = market_day.window("2024-08-29")
    assert start == pd.Timestamp("2024-08-28T22:00:00Z")
    assert end == pd.Timestamp("2024-08-29T22:00:00Z")


def test_a_winter_day_starts_at_23z_the_day_before():
    start, end = market_day.window("2024-01-15")
    assert start == pd.Timestamp("2024-01-14T23:00:00Z")
    assert end == pd.Timestamp("2024-01-15T23:00:00Z")


def test_a_normal_day_has_24_hours():
    assert len(market_day.hours("2024-08-29")) == 24


def test_the_spring_forward_day_has_23_hours():
    assert len(market_day.hours("2024-03-31")) == 23


def test_the_autumn_back_day_has_25_hours():
    assert len(market_day.hours("2024-10-27")) == 25


def test_hours_are_utc_aware_and_start_at_the_window():
    hours = market_day.hours("2024-08-29")
    assert str(hours.tz) == "UTC"
    assert hours[0] == market_day.window("2024-08-29")[0]
    assert hours[-1] < market_day.window("2024-08-29")[1]


def test_snapshots_are_naive_utc_matching_the_hours():
    hours, snapshots = market_day.hours("2024-08-29"), market_day.snapshots("2024-08-29")
    assert snapshots.tz is None
    assert list(snapshots) == list(hours.tz_convert("UTC").tz_localize(None))


def test_the_config_window_is_the_market_day():
    """What config/coppersushi.yaml must carry: PyPSA-Eur snapshots are naive UTC."""
    assert market_day.config_window("2024-08-29") == ("2024-08-28 22:00", "2024-08-29 22:00")
    assert market_day.config_window("2013-07-17") == ("2013-07-16 22:00", "2013-07-17 22:00")


def test_the_market_day_containing_a_window_start_is_the_inverse_of_config_window():
    """The runner names candidates from snapshots.start, which is a window start, not a day."""
    for day in ("2024-08-29", "2024-01-15", "2024-03-31", "2024-10-27", "2013-07-17"):
        start, _ = market_day.config_window(day)
        assert market_day.containing(start) == day


def test_containing_reads_a_naive_start_as_utc():
    assert market_day.containing("2024-08-28 22:00") == "2024-08-29"


def test_containing_accepts_an_aware_timestamp_too():
    assert market_day.containing(pd.Timestamp("2024-08-28T22:00:00Z")) == "2024-08-29"


def test_an_hour_inside_the_day_still_names_the_day():
    assert market_day.containing("2024-08-29 12:00") == "2024-08-29"
    assert market_day.containing("2024-08-29 21:59") == "2024-08-29"
    assert market_day.containing("2024-08-29 22:00") == "2024-08-30"
