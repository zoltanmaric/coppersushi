import json

import pandera.pandas as pa
import pytest

from coppersushi import REPO, market
from coppersushi.market_day import MarketDay

FIXTURES = REPO / "tests" / "fixtures" / "synthetic-electricity-maps"


def payloads() -> list[dict]:
    return json.loads((FIXTURES / "day-ahead-prices-hour.json").read_text())["responses"]


def hourly_day() -> list[dict]:
    return [json.loads((FIXTURES / "day-ahead-prices-day.json").read_text())]


def quarter_hourly_day() -> list[dict]:
    return [json.loads((FIXTURES / "day-ahead-prices-quarter-hour-day.json").read_text())]


def test_day_ahead_prices_are_tidy_and_keep_provenance():
    prices = market.day_ahead_prices(payloads())
    assert list(prices.zone) == ["AT", "BE"]
    assert list(prices.price) == [50.0, 70.0]
    assert prices.unit.eq("EUR/MWh").all()
    assert str(prices.interval.dt.tz) == "UTC"
    assert str(prices.updated_at.dt.tz) == "UTC"


def test_duplicate_zone_and_interval_is_refused():
    with pytest.raises(pa.errors.SchemaError, match="unique"):
        market.day_ahead_prices(payloads() + payloads())


def test_a_whole_day_at_its_market_time_unit_is_complete():
    market.check_complete(market.day_ahead_prices(hourly_day()), MarketDay.on("2024-08-29"), ("AT",))
    market.check_complete(market.day_ahead_prices(quarter_hourly_day()), MarketDay.on("2026-09-10"), ("AT",))


def test_a_missing_market_time_unit_is_refused():
    prices = market.day_ahead_prices(hourly_day()).iloc[:-1]
    with pytest.raises(ValueError, match="1 zone market time units missing"):
        market.check_complete(prices, MarketDay.on("2024-08-29"), ("AT",))


def test_hourly_prices_for_a_quarter_hourly_day_are_refused_whole():
    prices = market.day_ahead_prices(quarter_hourly_day())
    with pytest.raises(ValueError, match="72 zone market time units missing"):
        market.check_complete(prices[prices.interval.dt.minute.eq(0)], MarketDay.on("2026-09-10"), ("AT",))


def test_a_zone_that_was_not_asked_for_is_refused():
    with pytest.raises(ValueError, match="24 outside"):
        market.check_complete(market.day_ahead_prices(hourly_day()), MarketDay.on("2024-08-29"), ("BE",))
