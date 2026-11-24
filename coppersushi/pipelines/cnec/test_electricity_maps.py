import json
from io import BytesIO
from urllib.error import HTTPError

from pydantic import ValidationError
from threading import Barrier
from pathlib import Path

import pandas as pd
import pytest

from coppersushi import REPO
from coppersushi.pipelines.cnec import prices as market
from coppersushi.pipelines.data_model.market import ElectricityMapsPriceResponse
from coppersushi.pipelines.data_sources import electricity_maps_auction_prices
from coppersushi.pipelines.cnec import daily_prices
from coppersushi.pipelines.market_day import MarketDay

FIXTURES = REPO / 'coppersushi/pipelines/cnec/testdata/synthetic-electricity-maps'


def hourly_day() -> ElectricityMapsPriceResponse:
    """AT on 2024-08-29, an hourly market day."""
    return ElectricityMapsPriceResponse.model_validate_json((FIXTURES / "day-ahead-prices-day.json").read_text())


def quarter_hourly_day() -> ElectricityMapsPriceResponse:
    """AT on 2026-09-10, a quarter-hourly market day."""
    return ElectricityMapsPriceResponse.model_validate_json((FIXTURES / "day-ahead-prices-quarter-hour-day.json").read_text())


def one_hour() -> list[ElectricityMapsPriceResponse]:
    return [ElectricityMapsPriceResponse.model_validate(payload) for payload in
            json.loads((FIXTURES / "day-ahead-prices-hour.json").read_text())["responses"]]


def test_the_request_asks_for_the_day_at_its_market_time_unit():
    assert electricity_maps_auction_prices.query("AT", MarketDay.on("2024-08-29")) == {
        "zone": "AT",
        "start": "2024-08-28T22:00:00Z",
        "end": "2024-08-29T22:00:00Z",
        "temporalGranularity": "hourly",
    }
    assert electricity_maps_auction_prices.query("AT", MarketDay.on("2026-09-10"))["temporalGranularity"] == "15_minutes"


def test_fetch_day_uses_the_market_day_window_and_does_not_put_the_token_in_data(monkeypatch):
    calls = []

    def fake_get(zone, day, token):
        calls.append((zone, day, token))
        return hourly_day()

    monkeypatch.setattr(electricity_maps_auction_prices, "fetch_zone", fake_get)
    prices = daily_prices.fetch_day("2024-08-29", zones=("AT",), token="secret")
    assert set(prices.zone) == {"AT"}
    assert all(call[1].start_time_utc.isoformat() == "2024-08-28T22:00:00+00:00" for call in calls)
    assert "secret" not in prices.to_string()


def test_a_quarter_hourly_day_is_fetched_whole(monkeypatch):
    monkeypatch.setattr(electricity_maps_auction_prices, "fetch_zone", lambda zone, day, token: quarter_hourly_day())
    prices = daily_prices.fetch_day("2026-09-10", zones=("AT",), token="secret")
    assert len(prices) == 96
    assert prices.interval.iloc[1] - prices.interval.iloc[0] == pd.Timedelta(minutes=15)


def test_an_answer_at_another_resolution_than_asked_is_refused():
    with pytest.raises(RuntimeError, match="came 'hourly', asked '15_minutes'"):
        electricity_maps_auction_prices.check_answered_as_asked("AT", MarketDay.on("2026-09-10"), hourly_day())


def test_an_answer_for_another_zone_is_refused():
    with pytest.raises(RuntimeError, match="zone 'AT', expected 'BE'"):
        electricity_maps_auction_prices.check_answered_as_asked("BE", MarketDay.on("2024-08-29"), hourly_day())


def test_price_cache_round_trip_restores_aware_timestamps(tmp_path, monkeypatch):
    monkeypatch.setattr(daily_prices, "CACHE_DIR", tmp_path)
    prices = market.day_ahead_prices(one_hour())
    path = daily_prices.write_day("2024-08-29", prices)
    restored = daily_prices.read_day(Path(path))
    assert str(restored.interval.dt.tz) == "UTC"
    assert str(restored.updated_at.dt.tz) == "UTC"
    assert restored.price.tolist() == [50.0, 70.0]


def test_an_hourly_cache_of_a_quarter_hourly_day_is_fetched_again(tmp_path, monkeypatch):
    monkeypatch.setattr(daily_prices, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(market, "CORE_ZONES", ("AT",))  # the fixture's Core is one zone
    day = "2026-09-10"
    current = market.day_ahead_prices([quarter_hourly_day()])
    # What the adapter cached before it asked for the market time unit: the route's hourly default.
    daily_prices.write_day(day, current[current.interval.dt.minute.eq(0)])
    fetched = []
    monkeypatch.setattr(daily_prices, "fetch_day", lambda d: fetched.append(d) or current)
    assert len(daily_prices.load_day(day)) == 96
    assert len(daily_prices.load_day(day)) == 96
    assert fetched == [day]


@pytest.mark.parametrize(
    "damage",
    [lambda prices: prices.drop(index=40), lambda prices: pd.concat([prices, prices.iloc[[40]]])],
    ids=["a row missing", "a row doubled"],
)
def test_a_damaged_cache_is_fetched_again(tmp_path, monkeypatch, damage):
    monkeypatch.setattr(daily_prices, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(market, "CORE_ZONES", ("AT",))
    day = "2026-09-10"
    current = market.day_ahead_prices([quarter_hourly_day()])
    daily_prices.write_day(day, damage(current))
    fetched = []
    monkeypatch.setattr(daily_prices, "fetch_day", lambda d: fetched.append(d) or current)
    assert len(daily_prices.load_day(day)) == 96
    assert fetched == [day]


def test_stamp_is_utc_api_format():
    assert electricity_maps_auction_prices._stamp(pd.Timestamp("2024-08-28T22:00:00Z")) == "2024-08-28T22:00:00Z"


def test_zone_requests_overlap_and_still_return_a_complete_day(monkeypatch):
    payloads = json.loads((FIXTURES / "day-ahead-prices-core-day.json").read_text())
    by_zone = {payload["zone"]: ElectricityMapsPriceResponse.model_validate(payload) for payload in payloads}
    all_started = Barrier(len(by_zone), timeout=5)

    def get(zone, day, token):
        all_started.wait()  # No response arrives until every request has started.
        return by_zone[zone]

    monkeypatch.setattr(electricity_maps_auction_prices, "fetch_zone", get)
    prices = daily_prices.fetch_day("2024-08-29", zones=tuple(by_zone), token="secret")
    assert prices.groupby("zone").size().to_dict() == dict.fromkeys(by_zone, 24)


def test_one_failed_zone_does_not_cache_a_partial_day(tmp_path, monkeypatch):
    payloads = json.loads((FIXTURES / "day-ahead-prices-core-day.json").read_text())
    by_zone = {payload["zone"]: ElectricityMapsPriceResponse.model_validate(payload) for payload in payloads}
    monkeypatch.setattr(daily_prices, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(electricity_maps_auction_prices, "api_token", lambda: "secret")

    def get(zone, day, token):
        if zone == "BE":
            raise OSError("prices unavailable")
        return by_zone[zone]

    monkeypatch.setattr(electricity_maps_auction_prices, "fetch_zone", get)
    with pytest.raises(OSError, match="prices unavailable"):
        daily_prices.load_day("2024-08-29")
    assert not daily_prices.day_path("2024-08-29").exists()


def test_http_boundary_returns_validated_price_records(monkeypatch):
    content = (FIXTURES / "day-ahead-prices-day.json").read_bytes()
    monkeypatch.setattr(electricity_maps_auction_prices.urllib.request, "urlopen",
                        lambda *args, **kwargs: BytesIO(content))
    payload = electricity_maps_auction_prices.fetch_zone("AT", MarketDay.on("2024-08-29"), "secret")
    assert isinstance(payload, ElectricityMapsPriceResponse)
    assert payload.data[0].datetime.utcoffset() is not None
    assert payload.data[0].value == hourly_day().data[0].value


@pytest.mark.parametrize("field,value", [("value", None), ("datetime", "2024-08-28T22:00:00")])
def test_http_boundary_rejects_missing_price_or_timezone(monkeypatch, field, value):
    payload = json.loads((FIXTURES / "day-ahead-prices-day.json").read_text())
    payload["data"][0][field] = value
    monkeypatch.setattr(electricity_maps_auction_prices.urllib.request, "urlopen",
                        lambda *args, **kwargs: BytesIO(json.dumps(payload).encode()))
    with pytest.raises(ValidationError) as failure:
        electricity_maps_auction_prices.fetch_zone("AT", MarketDay.on("2024-08-29"), "secret")
    assert failure.value.errors()[0]["loc"] == ("data", 0, field)


@pytest.mark.parametrize("failure", [None, "conflict", "disconnected"])
def test_fallback_uses_signed_spreads_and_requires_consistent_anchors(monkeypatch, failure):
    from coppersushi.pipelines.cnec.spread_prices import SOURCE
    payload = quarter_hourly_day()

    def get(zone, day, token):
        if zone == "AT":
            return payload
        raise market.IncompletePrices("No data for zone")

    def spreads(day):
        assert day == MarketDay.on("2026-09-10")
        rows = [dict(dateTimeUtc=row.datetime, border_HU_AT=2, border_HU_RO=-3)
                for row in payload.data]
        if failure == "conflict":
            rows[-1]["border_AT_RO"] = 1
        if failure == "disconnected":
            rows[-1]["border_HU_RO"] = None
        return rows

    monkeypatch.setattr(electricity_maps_auction_prices, "fetch_zone", get)
    monkeypatch.setattr(daily_prices.jao, "fetch_price_spreads", spreads)
    zones = ("AT", "HU", "RO")
    if failure:
        with pytest.raises(ValueError if failure == "conflict" else market.IncompletePrices) as caught:
            daily_prices.fetch_day("2026-09-10", zones, token="secret")
        if failure == "conflict":
            assert not isinstance(caught.value, market.IncompletePrices)
        return
    prices = daily_prices.fetch_day("2026-09-10", zones, token="secret")
    assert set(prices[prices.zone.ne("AT")].source) == {SOURCE}
    assert prices[prices.zone.eq("AT")].source.tolist() == [r.source for r in payload.data]
    assert prices[prices.zone.eq("RO")].price.tolist() == pytest.approx([r.value - 5 for r in payload.data])


@pytest.mark.parametrize("second_spread", [3, 4], ids=["agree", "conflict"])
def test_two_neighbors_for_one_missing_quarter_hour(monkeypatch, second_spread):
    from coppersushi.pipelines.cnec.spread_prices import SOURCE

    day = quarter_hourly_day()
    missing = day.data[1].datetime
    prices = {"AT": 10, "HU": 12, "RO": 15}

    def get(zone, market_day, token):
        rows = [row.model_copy(update={"zone": zone, "value": prices[zone]})
                for row in day.data if zone != "HU" or row.datetime != missing]
        return day.model_copy(update={"zone": zone, "data": rows})

    monkeypatch.setattr(electricity_maps_auction_prices, "fetch_zone", get)
    monkeypatch.setattr(daily_prices.jao, "fetch_price_spreads", lambda *args: [
        dict(dateTimeUtc=missing, border_AT_HU=2, border_HU_RO=second_spread)])
    if second_spread != 3:
        with pytest.raises(ValueError, match="Conflicting"):
            daily_prices.fetch_day("2026-09-10", tuple(prices), token="secret")
        return
    result = daily_prices.fetch_day("2026-09-10", tuple(prices), token="secret")
    assert result.price.tolist() == [prices[z] for z in result.zone]
    derived = result[result.source.eq(SOURCE)]
    assert list(zip(derived.interval, derived.zone)) == [(missing, "HU")]

@pytest.mark.parametrize("status,reason", [(404, b"No data for zone"), (404, b"Unknown route"), (503, b"Unavailable")])
def test_source_error_retains_full_diagnostics(monkeypatch, caplog, status, reason):
    body = b"x" * 600 + reason + b": token=secret; upstream trace=abc"

    def fail(request, **kwargs):
        raise HTTPError(request.full_url, status, "failure", {"X-Request-ID": "42"}, BytesIO(body))

    monkeypatch.setattr(electricity_maps_auction_prices.urllib.request, "urlopen", fail)
    unavailable = reason == b"No data for zone"
    with pytest.raises(market.IncompletePrices if unavailable else HTTPError) as caught:
        electricity_maps_auction_prices.fetch_zone("AT", MarketDay.on("2024-08-29"), "secret")
    assert "upstream trace=abc" in caplog.text
    assert "request_id='42'" in caplog.text
    assert "secret" not in caplog.text
    if unavailable:
        assert "upstream trace=abc" in str(caught.value)
    else:
        assert caught.value.read() == body.replace(b"secret", b"[redacted]")
