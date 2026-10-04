import json
from io import BytesIO
from urllib.parse import parse_qs, urlsplit

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


def test_element_ends_round_trip_one_row_per_named_publication(tmp_path):
    day = written(tmp_path)
    assert list(day.element_ends.columns) == cnecs.END_COLUMNS
    assert not day.element_ends.duplicated(["eic", "tso", "name"]).any()


def test_write_rejects_missing_publisher_endpoints(tmp_path):
    day = written(tmp_path / "valid")
    missing = day.elements.iloc[0]
    ends = day.element_ends
    incomplete = day._replace(element_ends=ends[
        ~(ends.eic.eq(missing.eic) & ends.tso.eq(missing.tso) & ends.name.eq(missing["name"]))
    ])
    target = tmp_path / "invalid"
    with pytest.raises(jao.InvalidDomainCache, match=f"{missing.eic}.*{missing.tso}"):
        jao.write_day(target, *incomplete)
    assert not target.exists()


def test_read_rejects_missing_publisher_endpoints(tmp_path):
    written(tmp_path)
    path = tmp_path / "element-ends.csv"
    pd.read_csv(path).iloc[0:0].to_csv(path, index=False)
    with pytest.raises(jao.InvalidDomainCache, match="element ends missing"):
        jao.read_day(tmp_path)



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


def test_the_live_request_includes_the_required_page_size(monkeypatch):
    def urlopen(url, timeout):
        query = parse_qs(urlsplit(url).query)
        assert query == {
            "FromUtc": ["2024-08-28T22:00:00.000Z"],
            "ToUtc": ["2024-08-29T22:00:00.000Z"],
            "Take": ["100000000"],
        }
        return BytesIO((FIXTURES / "active-fb-day.json").read_bytes())

    monkeypatch.setattr(jao.urllib.request, "urlopen", urlopen)
    assert jao._get(
        "activeFbConstraints",
        pd.Timestamp("2024-08-28T22:00:00Z"),
        pd.Timestamp("2024-08-29T22:00:00Z"),
    ) == rows("active-fb-day.json")


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


def test_endpoint_seed_is_validated_and_reused_across_days(tmp_path, monkeypatch):
    monkeypatch.setattr(jao, "JAO_DIR", tmp_path)
    day = written(tmp_path / "2024-08-29")
    jao.seed_element_ends(["2024-08-29"])
    monkeypatch.setattr(jao, "_get", lambda *a, **kw: pytest.fail("seed covers these elements"))
    ends = jao.load_element_ends(pd.Timestamp("2024-09-01T12:00:00Z"), day.elements)
    pd.testing.assert_frame_equal(ends, day.element_ends)
    (tmp_path / "2024-08-29" / "element-ends.csv").unlink()
    with pytest.raises(OSError):
        jao.seed_element_ends(["2024-08-29"])
    pd.testing.assert_frame_equal(jao.read_element_ends(), ends)


@pytest.mark.parametrize("cache_state", ["absent", "old_schema", "empty", "incomplete"])
def test_missing_endpoints_fetch_one_hour_then_survive_a_reload(tmp_path, monkeypatch, cache_state):
    monkeypatch.setattr(jao, "JAO_DIR", tmp_path)
    fc = rows("final-computation-hour.json")
    required = cnecs.elements(fc)
    ends = cnecs.element_ends(fc)
    if cache_state == "old_schema":
        ends.drop(columns="name").to_csv(tmp_path / "element-ends.csv", index=False)
    elif cache_state == "empty":
        (tmp_path / "element-ends.csv").touch()
    elif cache_state == "incomplete":
        jao.write_element_ends(ends.iloc[:1])
    calls = []

    def fetch(endpoint, start, end, timeout):
        calls.append((endpoint, start, end))
        return fc

    monkeypatch.setattr(jao, "_get", fetch)
    interval = pd.Timestamp("2024-08-29T00:15:00+02:00")
    loaded = jao.load_element_ends(interval, required)
    assert calls == [("finalComputation", interval.tz_convert("UTC").floor("h"),
                      pd.Timestamp("2024-08-28T23:00:00Z"))]
    pd.testing.assert_frame_equal(loaded.reset_index(drop=True), ends)
    # A fresh read, including from another process, uses the successfully saved additions.
    pd.testing.assert_frame_equal(jao.load_element_ends(interval, required), jao.read_element_ends())
    assert len(calls) == 1


def test_failed_endpoint_fetch_can_be_retried_without_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(jao, "JAO_DIR", tmp_path)
    fc = rows("final-computation-hour.json")
    ends = cnecs.element_ends(fc)
    jao.write_element_ends(ends.iloc[:1])
    before = (tmp_path / "element-ends.csv").read_bytes()

    def offline(*args, **kwargs):
        raise OSError("upstream unavailable")

    monkeypatch.setattr(jao, "_get", offline)
    interval = pd.Timestamp("2024-08-28T22:00:00Z")
    with pytest.raises(RuntimeError, match="Please retry"):
        jao.load_element_ends(interval, cnecs.elements(fc))
    assert (tmp_path / "element-ends.csv").read_bytes() == before
    monkeypatch.setattr(jao, "_get", lambda *a, **kw: fc)
    assert len(jao.load_element_ends(interval, cnecs.elements(fc))) == len(ends)


def test_incomplete_upstream_endpoints_are_an_error_not_an_unmapped_element(tmp_path, monkeypatch):
    monkeypatch.setattr(jao, "JAO_DIR", tmp_path)
    fc = rows("final-computation-hour.json")
    required = cnecs.elements(fc).assign(name="missing from the publication")
    monkeypatch.setattr(jao, "_get", lambda *a, **kw: fc)
    with pytest.raises(RuntimeError, match="Please retry"):
        jao.load_element_ends(pd.Timestamp("2024-08-28T22:00:00Z"), required)
    assert not (tmp_path / "element-ends.csv").exists()


def test_an_interval_without_binding_elements_does_not_fetch(tmp_path, monkeypatch):
    monkeypatch.setattr(jao, "JAO_DIR", tmp_path)
    monkeypatch.setattr(jao, "_get", lambda *a, **kw: pytest.fail("nothing to locate"))
    required = cnecs.active_constraints(rows("active-fb-day.json")).iloc[:0]
    assert jao.load_element_ends(pd.Timestamp("2024-08-28T22:00:00Z"), required).empty
