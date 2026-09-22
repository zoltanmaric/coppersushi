import io
import json
import urllib.error

import pandas as pd
import pytest

from coppersushi import REPO, cnecs
from coppersushi.data_sources import jao

FIXTURES = REPO / "tests" / "fixtures" / "synthetic-jao"


def rows(name: str) -> list[dict]:
    return json.loads((FIXTURES / name).read_text())["data"]


def written(directory) -> jao.Day:
    fc, sp = rows("final-computation-hour.json"), rows("shadow-prices-day.json")
    jao.write_day(directory, cnecs.elements(fc), cnecs.contingencies(fc), cnecs.shadow_prices(sp),
                  cnecs.with_constraint_prices(cnecs.external_constraints(fc),
                                               cnecs.external_constraints(sp)),
                  cnecs.element_ends(fc))
    return jao.read_day(directory)


def active_written(directory) -> jao.ActiveDay:
    active = rows("active-fb-day.json")
    jao.write_active_day(
        directory,
        cnecs.active_constraints(active),
        cnecs.constraint_ptdfs(active),
        cnecs.active_external_constraints(active),
    )
    return jao.read_active_day(directory)


def test_write_and_load_round_trip(tmp_path):
    day = written(tmp_path)
    assert str(day.elements.hour.dt.tz) == "UTC"
    assert list(day.elements.columns) == cnecs.ELEMENT_COLUMNS
    assert not day.elements.empty


def test_every_hourly_table_comes_back_with_its_zone(tmp_path):
    day = written(tmp_path)
    hourly = [frame for frame in day if "hour" in frame]
    assert len(hourly) == len(jao.Day._fields) - 1  # element ends have no hour
    assert [str(frame.hour.dt.tz) for frame in hourly] == ["UTC"] * len(hourly)


def test_element_ends_round_trip_one_row_per_publisher_and_element(tmp_path):
    day = written(tmp_path)
    assert list(day.element_ends.columns) == cnecs.END_COLUMNS
    assert not day.element_ends.duplicated(["eic", "tso"]).any()


def test_an_old_cache_without_element_ends_is_not_a_complete_day(tmp_path, monkeypatch):
    written(tmp_path)
    monkeypatch.setattr(jao, "day_dir", lambda _: tmp_path)
    assert jao.has_day("any-day")
    (tmp_path / "element-ends.csv").unlink()
    assert not jao.has_day("any-day")


def test_the_disagreement_flag_survives_the_csv(tmp_path):
    """A bool column written as True/False is the round trip's easiest thing to silently invert."""
    day = written(tmp_path)
    shared = day.elements[day.elements.eic == "99T1001C--00101B"]
    assert shared.tso_disagreement.all()
    assert not day.elements.tso_disagreement.all()


def test_a_paginated_response_is_refused():
    with pytest.raises(RuntimeError, match="paginated"):
        jao.check_complete("finalComputation", rows=[{}], total=2)


def test_the_day_fetched_is_the_market_day():
    assert jao.hours_for("2024-08-29")[0] == pd.Timestamp("2024-08-28T22:00:00Z")
    assert len(jao.hours_for("2024-08-29")) == 24


def test_the_request_window_is_stamped_the_way_the_service_wants_it():
    assert jao._stamp(pd.Timestamp("2024-08-28T22:00:00Z")) == "2024-08-28T22:00:00.000Z"


def test_active_fb_tables_round_trip_at_quarter_hour_grain(tmp_path):
    active = active_written(tmp_path)
    assert len(active.constraints) == 2
    assert len(active.ptdfs) == 24
    assert len(active.external_constraints) == 1
    assert [str(frame.interval.dt.tz) for frame in active] == ["UTC"] * 3


def test_a_cache_from_an_older_adapter_is_fetched_again(tmp_path, monkeypatch):
    day = "2026-09-10"
    directory = tmp_path / day
    active_written(directory)
    constraints = directory / "active-constraints.csv"
    pd.read_csv(constraints).drop(columns="source_id").to_csv(constraints, index=False)
    fetched = []
    monkeypatch.setattr(jao, "JAO_DIR", tmp_path)
    monkeypatch.setattr(jao, "fetch_active_day", lambda d: fetched.append(d) or active_written(directory))
    assert jao.load_active_day(day).constraints.source_id.is_unique
    assert fetched == [day]


class TestRetries:
    """A day is 24 sequential requests; one unretried blip throws away every hour before it."""

    @staticmethod
    def _urlopen(failures: list[Exception]):
        """A `urlopen` that raises each of `failures` in turn, then serves an empty page."""
        calls = []

        def urlopen(url, timeout=None):
            calls.append(url)
            if failures:
                raise failures.pop(0)
            return io.BytesIO(json.dumps({"data": [], "totalRows": 0}).encode())

        return urlopen, calls

    def test_a_transient_server_error_is_retried(self, monkeypatch):
        error = urllib.error.HTTPError("http://x", 500, "Internal Server Error", {}, None)
        urlopen, calls = self._urlopen([error, error])
        monkeypatch.setattr(jao.urllib.request, "urlopen", urlopen)
        monkeypatch.setattr(jao.time, "sleep", lambda _: None)
        assert jao._read("http://x") == {"data": [], "totalRows": 0}
        assert len(calls) == 3

    def test_a_bad_request_is_not_retried(self, monkeypatch):
        urlopen, calls = self._urlopen(
            [urllib.error.HTTPError("http://x", 400, "Bad Request", {}, None)]
        )
        monkeypatch.setattr(jao.urllib.request, "urlopen", urlopen)
        with pytest.raises(urllib.error.HTTPError):
            jao._read("http://x")
        assert len(calls) == 1  # our own bad request; re-sending it says the same thing

    def test_an_outage_that_outlasts_every_retry_raises(self, monkeypatch):
        error = urllib.error.HTTPError("http://x", 503, "Service Unavailable", {}, None)
        urlopen, calls = self._urlopen([error] * (jao.RETRIES + 1))
        monkeypatch.setattr(jao.urllib.request, "urlopen", urlopen)
        monkeypatch.setattr(jao.time, "sleep", lambda _: None)
        with pytest.raises(urllib.error.HTTPError):
            jao._read("http://x")
        assert len(calls) == jao.RETRIES + 1
