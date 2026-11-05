"""Validate the external boundaries without network requests or rate-limit sleeps."""

import json

import pandas as pd
import pytest
from pandera.errors import SchemaError
from pydantic import ValidationError

from coppersushi.market_day import MarketDay
from coppersushi import REPO
from coppersushi.data_model.cnec_attribution import AlphaFactor, AttributionContext, AttributionPayload, AttributionRequest, attribution_to_browser, attribution_from_browser
from coppersushi.data_sources import cnec_attribution as source

FIXTURE = REPO / "tests/fixtures/cnec-attribution"
CASES = json.loads((FIXTURE / "alpha-records.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_api_fields_are_required_numbers(case):
    if case["valid"]:
        assert AlphaFactor.model_validate(case["record"]).alphaFactor == case["record"]["alphaFactor"]
    else:
        with pytest.raises(ValidationError):
            AlphaFactor.model_validate(case["record"])


@pytest.mark.parametrize("case", [c for c in CASES if not c["valid"]], ids=lambda c: c["name"])
def test_invalid_feed_raises(monkeypatch, tmp_path, case):
    feeds = json.loads((FIXTURE / "inputs.json").read_text())["feeds"]
    responses = dict(zip(["alphaFactor", "allocationConstraint", "netPos", "DA_PL_AC"], feeds.values()))
    responses["alphaFactor"] = [case["record"]]
    monkeypatch.setattr(source.jao, "day_dir", lambda _: tmp_path)
    monkeypatch.setattr(source.jao, "_get", lambda endpoint, *args, **kwargs: responses[endpoint])
    monkeypatch.setattr(source.time, "sleep", lambda _: None)
    monkeypatch.setattr(source.cache, "publish", lambda *args: pytest.fail("incomplete cache published"))
    with pytest.raises(ValidationError):
        source.load_day(MarketDay.on("2026-09-12"), refresh=True)


def test_empty_feeds_are_supported_missing_data(monkeypatch, tmp_path):
    monkeypatch.setattr(source.jao, "day_dir", lambda _: tmp_path)
    monkeypatch.setattr(source.jao, "_get", lambda *args, **kwargs: [])
    monkeypatch.setattr(source.time, "sleep", lambda _: None)
    frame = source.load_day(MarketDay.on("2026-09-12"), refresh=True)
    assert len(frame) == 96
    assert frame.drop(columns="interval").isna().all().all()


def test_browser_nulls_become_numeric_missing_values():
    frame = pd.read_csv(FIXTURE / "missing-context.csv")
    payload = AttributionPayload.model_validate({
        "day": "2024-08-29", "complete": False,
        "rows": json.loads(frame.to_json(orient="records")),
    })
    restored = attribution_from_browser(payload)
    assert attribution_to_browser(restored, MarketDay.on(payload.day)) == payload
    assert restored.drop(columns="interval").dtypes.eq("float64").all()
    assert restored.drop(columns="interval").isna().all().all()
    with pytest.raises(ValidationError):
        AttributionPayload.model_validate({**payload.model_dump(), "unexpected": "0"})
    with pytest.raises(SchemaError):
        AttributionContext.validate(pd.concat([restored, restored]))


def test_invalid_cached_table_raises(monkeypatch, tmp_path):
    frame = pd.read_csv(FIXTURE / "missing-context.csv").drop(columns="alpha")
    frame.to_csv(tmp_path / "attribution.csv", index=False)
    calls = []
    monkeypatch.setattr(source.jao, "day_dir", lambda _: tmp_path)
    monkeypatch.setattr(source.jao, "_get", lambda endpoint, *args, **kwargs: calls.append(endpoint) or [])
    monkeypatch.setattr(source.time, "sleep", lambda _: None)
    with pytest.raises(SchemaError):
        source.load_day(MarketDay.on("2026-09-12"))
    assert not calls


@pytest.mark.parametrize("stage", ["request", "transformation"])
def test_loader_does_not_hide_failures(monkeypatch, tmp_path, stage):
    def broken(*args, **kwargs):
        raise RuntimeError("unexpected failure")
    monkeypatch.setattr(source.jao, "day_dir", lambda _: tmp_path)
    monkeypatch.setattr(source.jao, "_get", broken if stage == "request" else lambda *args, **kwargs: [])
    monkeypatch.setattr(source.time, "sleep", lambda _: None)
    if stage == "transformation":
        monkeypatch.setattr(source.cnec_attribution, "context", broken)
    with pytest.raises(RuntimeError, match="unexpected failure"):
        source.load_day(MarketDay.on("2026-09-12"), refresh=True)


def test_browser_delivery_date_is_typed_and_serializes_as_iso():
    from datetime import date
    failure = AttributionRequest.model_validate({
        "day": "2026-11-03",
    })
    assert failure.day == date(2026, 11, 3)
    assert failure.model_dump(mode="json")["day"] == "2026-11-03"
    with pytest.raises(ValidationError):
        AttributionRequest.model_validate({**failure.model_dump(), "day": "2026-02-30"})


def test_loader_uses_market_day_boundaries_on_clock_change(monkeypatch, tmp_path):
    day = MarketDay.on("2026-10-25")
    windows = []
    def fetch(endpoint, start, end, **kwargs):
        windows.append((start, end))
        return []
    monkeypatch.setattr(source.jao, "day_dir", lambda _: tmp_path)
    monkeypatch.setattr(source.jao, "_get", fetch)
    monkeypatch.setattr(source.time, "sleep", lambda _: None)
    frame = source.load_day(day, refresh=True)
    assert len(frame) == 100
    assert windows == [(day.start_time_utc, day.end_time_utc)] * 4
    assert (windows[0][1] - windows[0][0]).total_seconds() == 25 * 3600
