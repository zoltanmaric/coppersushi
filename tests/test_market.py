import pandas as pd
import pytest

from coppersushi import market


def payload(zone: str, price: float, hour: int = 0) -> dict:
    return {
        "zone": zone,
        "temporalGranularity": "hourly",
        "data": [
            {
                "zone": zone,
                "datetime": f"2024-08-29T{hour:02d}:00:00Z",
                "createdAt": "2024-08-28T12:00:00Z",
                "updatedAt": "2024-08-28T12:05:00Z",
                "value": price,
                "unit": "EUR/MWh",
                "source": "example.test",
            }
        ],
    }


def test_day_ahead_prices_keep_source_resolution_and_provenance():
    prices = market.day_ahead_prices([payload("AT", 50.0), payload("BE", 70.0)])
    assert list(prices.zone) == ["AT", "BE"]
    assert list(prices.price) == [50.0, 70.0]
    assert prices.unit.eq("EUR/MWh").all()
    assert str(prices.interval.dt.tz) == "UTC"
    assert str(prices.updated_at.dt.tz) == "UTC"


def test_hourly_price_is_used_inside_its_quarter_hour_without_interpolation():
    prices = market.day_ahead_prices(
        [payload("AT", 50.0, 0), payload("AT", 80.0, 1), payload("BE", 70.0, 0)]
    )
    at_quarter_past = market.prices_at(prices, pd.Timestamp("2024-08-29T00:15:00Z"))
    assert at_quarter_past.set_index("zone").price.to_dict() == {"AT": 50.0, "BE": 70.0}


def test_price_lookup_rejects_a_naive_interval():
    prices = market.day_ahead_prices([payload("AT", 50.0)])
    with pytest.raises(ValueError, match="timezone-aware"):
        market.prices_at(prices, pd.Timestamp("2024-08-29 00:15"))


def test_duplicate_zone_and_interval_is_refused():
    with pytest.raises(ValueError, match="several day-ahead prices"):
        market.day_ahead_prices([payload("AT", 50.0), payload("AT", 55.0)])
