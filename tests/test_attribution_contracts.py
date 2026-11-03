"""Validate the external boundaries without network requests or rate-limit sleeps."""

import json

import pandas as pd
import pytest
from pandera.errors import SchemaError
from pydantic import ValidationError

from coppersushi import REPO
from coppersushi.data_model.cnec_attribution import AlphaFactor, AttributionContext, AttributionPayload
from coppersushi.data_sources import cnec_attribution as source

FIXTURE = REPO / "tests/fixtures/cnec-attribution"
CASES = json.loads((FIXTURE / "alpha-records.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_api_fields_are_required_but_nullable(case):
    if case["valid"]:
        assert AlphaFactor.model_validate(case["record"]).alphaFactor == case["record"]["alphaFactor"]
    else:
        with pytest.raises(ValidationError):
            AlphaFactor.model_validate(case["record"])


@pytest.mark.parametrize("case", [c for c in CASES if not c["valid"]], ids=lambda c: c["name"])
def test_invalid_feed_preserves_other_inputs(monkeypatch, tmp_path, caplog, case):
    feeds = json.loads((FIXTURE / "inputs.json").read_text())["feeds"]
    responses = dict(zip(["alphaFactor", "allocationConstraint", "netPos", "DA_PL_AC"], feeds.values()))
    responses["alphaFactor"] = [case["record"]]
    monkeypatch.setattr(source.jao, "day_dir", lambda _: tmp_path)
    monkeypatch.setattr(source.jao, "_get", lambda endpoint, *args, **kwargs: responses[endpoint])
    monkeypatch.setattr(source.time, "sleep", lambda _: None)
    monkeypatch.setattr(source.cache, "publish", lambda *args: pytest.fail("incomplete cache published"))
    frame = source.load_day("2026-09-12", refresh=True)
    assert frame.alpha.isna().all()
    assert frame.polish_alt.iloc[:4].tolist() == [120] * 4
    assert "alphaFactor" in caplog.text


def test_empty_feeds_are_supported_missing_data(monkeypatch, tmp_path):
    monkeypatch.setattr(source.jao, "day_dir", lambda _: tmp_path)
    monkeypatch.setattr(source.jao, "_get", lambda *args, **kwargs: [])
    monkeypatch.setattr(source.time, "sleep", lambda _: None)
    frame = source.load_day("2026-09-12", refresh=True)
    assert len(frame) == 96
    assert frame.drop(columns="interval").isna().all().all()


def test_browser_nulls_become_numeric_missing_values():
    frame = pd.read_csv(FIXTURE / "missing-context.csv")
    payload = AttributionPayload.model_validate({
        "day": "2024-08-29", "request": 0, "complete": False,
        "rows": json.loads(frame.to_json(orient="records")),
    })
    restored = pd.DataFrame([row.model_dump() for row in payload.rows])
    restored["interval"] = pd.to_datetime(restored.interval, utc=True)
    restored = AttributionContext.validate(restored)
    assert restored.drop(columns="interval").dtypes.eq("float64").all()
    assert restored.drop(columns="interval").isna().all().all()
    with pytest.raises(ValidationError):
        AttributionPayload.model_validate({**payload.model_dump(), "request": "0"})
    with pytest.raises(SchemaError):
        AttributionContext.validate(pd.concat([restored, restored]))


def test_invalid_cached_table_is_refetched(monkeypatch, tmp_path, caplog):
    frame = pd.read_csv(FIXTURE / "missing-context.csv").drop(columns="alpha")
    frame.to_csv(tmp_path / "attribution.csv", index=False)
    calls = []
    monkeypatch.setattr(source.jao, "day_dir", lambda _: tmp_path)
    monkeypatch.setattr(source.jao, "_get", lambda endpoint, *args, **kwargs: calls.append(endpoint) or [])
    monkeypatch.setattr(source.time, "sleep", lambda _: None)
    restored = source.load_day("2026-09-12")
    assert len(calls) == 4
    assert len(restored) == 96
    assert "Ignoring unusable attribution cache" in caplog.text
