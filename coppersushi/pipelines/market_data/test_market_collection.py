from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from urllib.response import addinfourl
import json
from urllib.error import HTTPError

import pytest

from coppersushi.pipelines.market_data.data_sources import collect_market_editions, electricity_maps_auction_prices, entsoe_auction_prices, jao_border_spreads, smard_auction_prices
from coppersushi.pipelines.market_data.data_sources.editions import read_editions
from coppersushi.pipelines.market_data.data_sources.publisher_cooldown import PublisherCoolingDown, check_ready
from coppersushi.pipelines.market_data.data_sources.responses import read_attempt, read_day_diagnostics, read_response
from coppersushi.pipelines.market_data.test_editions import ArchiveS3, DAY, T, publish
from coppersushi.pipelines.market_data.test_resolution import first
from coppersushi.pipelines.market_data.response_models import FailedAttempt
from coppersushi.pipelines.market_data.resolution import CNEC_POLICY
from coppersushi.pipelines.market_day import MarketDay


class CollectorS3(ArchiveS3):
    def list_objects_v2(self, *, Bucket, Prefix, StartAfter, MaxKeys):
        return {"Contents": [{"Key": key} for key in sorted(self.objects) if key.startswith(Prefix) and key > StartAfter][:MaxKeys]}


def test_entsoe_selects_the_coupled_auction_and_expands_only_a03_points():
    day = MarketDay.on(DAY)
    template = """<TimeSeries>
    <in_Domain.mRID>10Y1001A1001A82H</in_Domain.mRID><out_Domain.mRID>10Y1001A1001A82H</out_Domain.mRID>
    <contract_MarketAgreement.type>A01</contract_MarketAgreement.type><auction.type>A01</auction.type>
    <classificationSequence_AttributeInstanceComponent.position>{seq}</classificationSequence_AttributeInstanceComponent.position>
    <currency_Unit.name>EUR</currency_Unit.name><price_Measure_Unit.name>MWH</price_Measure_Unit.name>
    <curveType>{curve}</curveType><Period><resolution>PT15M</resolution><timeInterval>
    <start>2026-11-19T23:00Z</start><end>2026-11-19T23:45Z</end></timeInterval>
    <Point><position>1</position><price.amount>{price}</price.amount></Point></Period></TimeSeries>"""
    def prices(curve):
        series = template.format(seq=1, curve=curve, price="-1.23") + template.format(seq=2, curve=curve, price="99")
        return entsoe_auction_prices.prices(f"<Document><type>A44</type>{series}</Document>".encode(), "DE-LU", day)
    assert [(row.interval, row.price) for row in prices("A01")] == [(day.start_time_utc, Decimal("-1.23"))]
    assert [row.interval for row in prices("A03")] == [day.start_time_utc + timedelta(minutes=i) for i in (0, 15, 30)]


@pytest.mark.parametrize("omit", [None, "createdAt", "updatedAt"])
def test_electricity_maps_publisher_clocks_survive_archive_replay(omit):
    row = {"zone": "DE", "datetime": "2026-11-19T23:00:00Z", "value": 30.0,
           "unit": "EUR/MWh", "source": "example",
           "createdAt": "2026-11-20T01:15:00+01:00", "updatedAt": "2026-11-21T02:30:00+01:00"}
    if omit:
        del row[omit]
    body = json.dumps({"zone": "DE", "temporalGranularity": "15_minutes", "data": [row]}).encode()
    rows = electricity_maps_auction_prices.prices(body, "DE-LU", MarketDay.on(DAY))
    store = ArchiveS3()
    store.now = datetime(2026, 11, 24, 10, tzinfo=UTC)
    publish(store, "electricity_maps", "DE-LU", rows)
    evidence, = first(store, store.now + timedelta(seconds=1), policy=CNEC_POLICY).evidence
    assert evidence.source_created_at == (None if omit == "createdAt" else datetime(2026, 11, 20, 0, 15, tzinfo=UTC))
    assert evidence.source_updated_at == (None if omit == "updatedAt" else datetime(2026, 11, 21, 1, 30, tzinfo=UTC))
    assert evidence.received_at == store.now


def test_smard_day_contains_only_reported_intervals():
    day = MarketDay.on(DAY)
    start = int(day.start_time_utc.timestamp()) * 1000
    data = {"series": [[start - 900000, 0], [start, None], [start + 900000, -2.35]]}
    rows = smard_auction_prices.prices(json.dumps(data).encode(), "DE-LU", day)
    assert [(r.price, r.interval) for r in rows] == [(Decimal("-2.35"), day.start_time_utc + timedelta(minutes=15))]


def test_jao_partial_days_preserve_signed_edges_and_reject_truncated_pages():
    data = {"rejected": False, "data": [{"dateTimeUtc": "2026-11-19T23:00Z", "border_AT_DE": -2.11, "border_DE_AT": None}]}
    rows = jao_border_spreads.spreads(json.dumps(data).encode(), "CORE", MarketDay.on(DAY))
    assert [(r.origin, r.destination, r.difference) for r in rows] == [("AT", "DE-LU", Decimal("-2.11"))]
    with pytest.raises(ValueError, match="Incomplete"):
        jao_border_spreads.spreads(json.dumps(dict(data, totalRows=2)).encode(), "CORE", MarketDay.on(DAY))


def test_collect_retains_failed_raw_body_and_retry_details_without_credentials(monkeypatch):
    monkeypatch.setenv("ENTSOE_API_TOKEN", "synthetic-token")
    store = CollectorS3()
    def throttled(req, timeout):
        raise HTTPError(req.full_url, 429, "throttled", {"Retry-After": "900"},
                        BytesIO(b"upstream detail " + b"e"*600 + b" synthetic-token"))
    monkeypatch.setattr(collect_market_editions, "urlopen", throttled)
    attempt, = collect_market_editions.collect_day(store, "test", "entsoe", DAY, clock=lambda: T)
    assert attempt.outcome == "failed"
    assert read_day_diagnostics(store, "test", DAY, T) == []
    assert read_day_diagnostics(store, "test", DAY, T + timedelta(seconds=1)) == [attempt]
    receipt = read_attempt(store, "test", attempt.attempt_id)
    assert receipt.http_status == 429 and receipt.headers["Retry-After"] == "900"
    with pytest.raises(PublisherCoolingDown) as caught:
        check_ready(store, "test", "entsoe", T + timedelta(seconds=899))
    assert caught.value.attempt == attempt.attempt_id
    check_ready(store, "test", "entsoe", T + timedelta(seconds=900))
    check_ready(store, "test", "jao", T)
    assert all(b"synthetic-token" not in obj for obj in store.objects.values())
    assert store.objects[f"market-data/attempts/{receipt.attempt_id}"].endswith(b" [redacted]")


@pytest.mark.parametrize(("status", "headers", "delay"), [
    (429, {"Retry-After": "900"}, 900),
    (429, {}, 60),
    (503, {"Retry-After": "900"}, 900),
])
def test_retry_after_survives_response_read_timeout(monkeypatch, status, headers, delay):
    monkeypatch.setenv("ENTSOE_API_TOKEN", "test-key")
    store = CollectorS3()
    cooldowns_before_read = []
    now = T

    class StalledBody(BytesIO):
        def read(self, *args):
            nonlocal now
            cooldowns_before_read.extend(key for key in store.objects if "/cooldowns/" in key)
            now += timedelta(seconds=30)
            raise TimeoutError("publisher body timed out")

    def stalled_response(req, timeout):
        raise HTTPError(req.full_url, status, "Unavailable", headers, StalledBody())

    monkeypatch.setattr(collect_market_editions, "urlopen", stalled_response)
    attempt, = collect_market_editions.collect_day(store, "test", "entsoe", DAY,
                                                   zones=("DE-LU", "FR"), clock=lambda: now)
    cooldown, = cooldowns_before_read
    assert cooldown.endswith(f"/{attempt.attempt_id}")
    assert attempt.outcome == "failed"
    assert attempt.completed_at == T + timedelta(seconds=30)
    assert f"HTTP {status}" in attempt.diagnostic
    assert "TimeoutError: publisher body timed out" in attempt.diagnostic
    assert read_day_diagnostics(store, "test", DAY, now) == [attempt]
    receipt = read_attempt(store, "test", attempt.attempt_id)
    assert isinstance(receipt, FailedAttempt)
    assert receipt.http_status == status and receipt.headers == headers
    assert store.objects[f"market-data/attempts/{attempt.attempt_id}"] == receipt.reason.encode()

    with pytest.raises(PublisherCoolingDown) as pause:
        collect_market_editions.collect_day(store, "test", "entsoe", DAY, clock=lambda: now)
    assert pause.value.attempt == attempt.attempt_id
    assert pause.value.until == T + timedelta(seconds=delay)
    check_ready(store, "test", "entsoe", pause.value.until)
    check_ready(store, "test", "jao", now)


@pytest.mark.parametrize(("reason", "expected"), [
    ("No matching data found", "empty"),
    ("No matching data for test-key", "failed"),
    ("Invalid request", "failed"),
])
def test_entsoe_400_keeps_provider_acknowledgement_and_distinguishes_no_data(monkeypatch, reason, expected):
    monkeypatch.setenv("ENTSOE_API_TOKEN", "test-key")
    store = CollectorS3()
    body = f"<Acknowledgement_MarketDocument><Reason><text>{reason}</text></Reason></Acknowledgement_MarketDocument>".encode()

    def acknowledge(req, timeout):
        raise HTTPError(req.full_url, 400, "Bad Request", {}, BytesIO(body))

    monkeypatch.setattr(collect_market_editions, "urlopen", acknowledge)
    attempt, = collect_market_editions.collect_day(store, "test", "entsoe", DAY, clock=lambda: T)
    assert attempt.outcome == expected
    archived = read_response(store, "test", attempt.attempt_id)
    assert archived.receipt.http_status == 400
    assert archived.body == body.replace(b"test-key", b"[redacted]")
    cutoff = T + timedelta(seconds=1)
    editions = read_editions(store, "test", DAY, cutoff)
    if expected == "empty":
        (edition, rows), = editions
        assert edition.receipt == archived.receipt and rows == []
    else:
        assert editions == []
        assert read_day_diagnostics(store, "test", DAY, cutoff) == [attempt]
        if "test-key" in reason:
            assert "redacted" in attempt.diagnostic and "test-key" not in attempt.diagnostic


def test_publication_error_correlates_raw_receipt_without_leaking_token(monkeypatch, caplog):
    monkeypatch.setenv("ENTSOE_API_TOKEN", "private-test-token")
    store = CollectorS3()
    body = b"<Acknowledgement_MarketDocument><Reason><text>No matching data found</text></Reason></Acknowledgement_MarketDocument>"

    def empty(req, timeout):
        raise HTTPError(req.full_url, 400, "Bad Request", {}, BytesIO(body))

    def fail(*args):
        raise OSError("write rejected private-test-token")

    monkeypatch.setattr(collect_market_editions, "urlopen", empty)
    monkeypatch.setattr(collect_market_editions, "publish_edition", fail)
    with pytest.raises(RuntimeError, match="publish_edition failed") as caught:
        collect_market_editions.collect_day(store, "test", "entsoe", DAY, clock=lambda: T)
    key, = store.objects
    attempt = key.split("/")[-1]
    scope = f"attempt_id={attempt} publisher=entsoe zone=DE-LU delivery_day={DAY}"
    assert f"poll_started {scope}" in caplog.text
    assert f"raw_saved {scope}" in caplog.text
    assert scope in str(caught.value) and "write rejected [redacted]" in str(caught.value)
    assert "private-test-token" not in caplog.text
    assert "edition_published" not in caplog.text


@pytest.mark.parametrize(("publisher", "fixture", "detail"), [
    ("entsoe", "entsoe_missing_resolution.xml", "resolution"),
    ("smard", "smard_nanosecond_epoch.json", "1795129200000000000"),
])
def test_malformed_price_response_preserves_evidence(monkeypatch, publisher, fixture, detail) -> None:
    body = (Path(__file__).parent / "fixtures" / fixture).read_bytes()
    monkeypatch.setenv("ENTSOE_API_TOKEN", "test-key")
    monkeypatch.setattr(collect_market_editions, "urlopen",
                        lambda req, timeout: addinfourl(BytesIO(body), {}, req.full_url, 200))
    store = CollectorS3()
    attempt, = collect_market_editions.collect_day(store, "test", publisher, DAY, clock=lambda: T)
    assert attempt.outcome == "failed" and detail in attempt.diagnostic
    assert read_response(store, "test", attempt.attempt_id).body == body
    cutoff = T + timedelta(seconds=1)
    assert read_day_diagnostics(store, "test", DAY, cutoff) == [attempt]
    assert read_editions(store, "test", DAY, cutoff) == []
