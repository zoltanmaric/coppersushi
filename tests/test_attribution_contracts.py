"""Validate the external boundaries without network requests or rate-limit sleeps."""

import json

import pandas as pd
import pytest
from pandera.errors import SchemaError
from pydantic import ValidationError

from coppersushi.market_day import MarketDay
from coppersushi import REPO
from coppersushi.data_model.cnec_attribution import AlphaFactor
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
    monkeypatch.setattr(source.cache, "publish", lambda *args: pytest.fail("incomplete cache published"))
    with pytest.raises(ValidationError):
        source.load_day(MarketDay.on("2026-09-12"), refresh=True)


def test_empty_feeds_are_supported_missing_data(monkeypatch, tmp_path):
    monkeypatch.setattr(source.jao, "day_dir", lambda _: tmp_path)
    monkeypatch.setattr(source.jao, "_get", lambda *args, **kwargs: [])
    frame = source.load_day(MarketDay.on("2026-09-12"), refresh=True)
    assert len(frame) == 96
    assert frame.drop(columns="interval").isna().all().all()




def test_invalid_cached_table_raises(monkeypatch, tmp_path):
    frame = pd.read_csv(FIXTURE / "missing-context.csv").drop(columns="alpha")
    frame.to_csv(tmp_path / "attribution.csv", index=False)
    calls = []
    monkeypatch.setattr(source.jao, "day_dir", lambda _: tmp_path)
    monkeypatch.setattr(source.jao, "_get", lambda endpoint, *args, **kwargs: calls.append(endpoint) or [])
    with pytest.raises(SchemaError):
        source.load_day(MarketDay.on("2026-09-12"))
    assert not calls


@pytest.mark.parametrize("stage", ["request", "transformation"])
def test_loader_does_not_hide_failures(monkeypatch, tmp_path, stage):
    def broken(*args, **kwargs):
        raise RuntimeError("unexpected failure")
    monkeypatch.setattr(source.jao, "day_dir", lambda _: tmp_path)
    monkeypatch.setattr(source.jao, "_get", broken if stage == "request" else lambda *args, **kwargs: [])
    if stage == "transformation":
        monkeypatch.setattr(source.cnec_attribution, "context", broken)
    with pytest.raises(RuntimeError, match="unexpected failure"):
        source.load_day(MarketDay.on("2026-09-12"), refresh=True)




def test_loader_uses_market_day_boundaries_on_clock_change(monkeypatch, tmp_path):
    day = MarketDay.on("2026-10-25")
    windows = []
    def fetch(endpoint, start, end, **kwargs):
        windows.append((start, end))
        return []
    monkeypatch.setattr(source.jao, "day_dir", lambda _: tmp_path)
    monkeypatch.setattr(source.jao, "_get", fetch)
    frame = source.load_day(day, refresh=True)
    assert len(frame) == 100
    assert windows == [(day.start_time_utc, day.end_time_utc)] * 4
    assert (windows[0][1] - windows[0][0]).total_seconds() == 25 * 3600
