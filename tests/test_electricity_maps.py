from pathlib import Path

import pandas as pd

from coppersushi import market
from coppersushi.data_sources import electricity_maps


def payload(zone: str) -> dict:
    return {
        "zone": zone,
        "temporalGranularity": "hourly",
        "data": [
            {
                "zone": zone,
                "datetime": "2024-08-28T22:00:00Z",
                "createdAt": "2024-08-28T12:00:00Z",
                "updatedAt": "2024-08-28T12:05:00Z",
                "value": 50.0 if zone == "AT" else 60.0,
                "unit": "EUR/MWh",
                "source": "example.test",
            }
        ],
    }


def test_fetch_day_uses_the_market_day_window_and_does_not_put_the_token_in_data(monkeypatch):
    calls = []

    def fake_get(zone, day, token):
        calls.append((zone, day, token))
        return payload(zone)

    monkeypatch.setattr(electricity_maps, "_get", fake_get)
    prices = electricity_maps.fetch_day("2024-08-29", zones=("AT", "BE"), token="secret")
    assert set(prices.zone) == {"AT", "BE"}
    assert all(call[1].start_time_utc.isoformat() == "2024-08-28T22:00:00+00:00" for call in calls)
    assert "secret" not in prices.to_string()


def test_price_cache_round_trip_restores_aware_timestamps(tmp_path, monkeypatch):
    monkeypatch.setattr(electricity_maps, "CACHE_DIR", tmp_path)
    prices = market.day_ahead_prices([payload("AT"), payload("BE")])
    path = electricity_maps.write_day("2024-08-29", prices)
    restored = electricity_maps.read_day(Path(path))
    assert str(restored.interval.dt.tz) == "UTC"
    assert str(restored.updated_at.dt.tz) == "UTC"
    assert restored.price.tolist() == [50.0, 60.0]


def test_stamp_is_utc_api_format():
    assert electricity_maps._stamp(pd.Timestamp("2024-08-28T22:00:00Z")) == "2024-08-28T22:00:00Z"
