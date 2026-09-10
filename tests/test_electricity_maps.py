import json
from pathlib import Path

import pandas as pd
import pytest

from coppersushi import REPO, market
from coppersushi.data_sources import electricity_maps
from coppersushi.market_day import MarketDay

FIXTURES = REPO / "tests" / "fixtures" / "synthetic-electricity-maps"


def full_day() -> dict:
    return json.loads((FIXTURES / "day-ahead-prices-day.json").read_text())


def one_hour() -> list[dict]:
    return json.loads((FIXTURES / "day-ahead-prices-hour.json").read_text())["responses"]


def test_fetch_day_uses_the_market_day_window_and_does_not_put_the_token_in_data(monkeypatch):
    calls = []

    def fake_get(zone, day, token):
        calls.append((zone, day, token))
        return full_day()

    monkeypatch.setattr(electricity_maps, "_get", fake_get)
    prices = electricity_maps.fetch_day("2024-08-29", zones=("AT",), token="secret")
    assert set(prices.zone) == {"AT"}
    assert all(call[1].start_time_utc.isoformat() == "2024-08-28T22:00:00+00:00" for call in calls)
    assert "secret" not in prices.to_string()


def test_price_cache_round_trip_restores_aware_timestamps(tmp_path, monkeypatch):
    monkeypatch.setattr(electricity_maps, "CACHE_DIR", tmp_path)
    prices = market.day_ahead_prices(one_hour())
    path = electricity_maps.write_day("2024-08-29", prices)
    restored = electricity_maps.read_day(Path(path))
    assert str(restored.interval.dt.tz) == "UTC"
    assert str(restored.updated_at.dt.tz) == "UTC"
    assert restored.price.tolist() == [50.0, 70.0]


def test_stamp_is_utc_api_format():
    assert electricity_maps._stamp(pd.Timestamp("2024-08-28T22:00:00Z")) == "2024-08-28T22:00:00Z"


def test_a_partial_price_day_is_refused_before_it_can_be_cached():
    payload = full_day()
    payload["data"] = payload["data"][:-1]
    with pytest.raises(RuntimeError, match="1 missing"):
        electricity_maps.check_complete("AT", MarketDay.on("2024-08-29"), payload)


def test_a_repeated_price_interval_is_refused():
    payload = full_day()
    payload["data"].append(payload["data"][0])
    with pytest.raises(RuntimeError, match="repeated"):
        electricity_maps.check_complete("AT", MarketDay.on("2024-08-29"), payload)
