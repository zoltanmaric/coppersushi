import json
from io import BytesIO
from urllib.parse import parse_qs, urlsplit

import pandas as pd
import pytest

from coppersushi import REPO
from coppersushi.pipelines.cnec import elements as cnecs
from coppersushi.pipelines.cnec.data_sources import jao

FIXTURES = REPO / 'coppersushi/pipelines/cnec/testdata/synthetic-jao'


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
    assert [str(frame.interval.dt.tz) for frame in active] == ["UTC"] * 2


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


@pytest.mark.parametrize("cache_state", ["absent", "old_schema", "empty", "incomplete", "blank_endpoints", "blank_seed_stale_hour"])
def test_missing_endpoints_fetch_one_hour_then_survive_a_reload(tmp_path, monkeypatch, cache_state):
    monkeypatch.setattr(jao, "JAO_DIR", tmp_path)
    fc = rows("final-computation-hour.json")
    required = cnecs.elements(fc)
    ends = cnecs.element_ends(fc)
    if cache_state == "old_schema":
        ends.drop(columns="name").to_csv(tmp_path / "element-ends.csv", index=False)
    elif cache_state == "empty":
        (tmp_path / "element-ends.csv").touch()
    elif cache_state in ("blank_endpoints", "blank_seed_stale_hour"):
        (tmp_path / "element-ends.csv").write_bytes((FIXTURES / "blank-endpoints.csv").read_bytes())
    elif cache_state == "incomplete":
        jao.write_element_ends(ends.iloc[:1])
    if cache_state == "blank_seed_stale_hour":
        hour = tmp_path / "endpoints/20240828T22Z"
        hour.mkdir(parents=True)
        ends.iloc[:1].to_csv(hour / "element-ends.csv", index=False)
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
    partial = jao.load_element_ends(interval, cnecs.elements(fc))
    pd.testing.assert_frame_equal(partial.reset_index(drop=True), ends.iloc[:1].reset_index(drop=True))
    assert (tmp_path / "element-ends.csv").read_bytes() == before
    monkeypatch.setattr(jao, "_get", lambda *a, **kw: fc)
    assert len(jao.load_element_ends(interval, cnecs.elements(fc))) == len(ends)


def test_partial_endpoint_response_keeps_known_lines_and_retries_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(jao, "JAO_DIR", tmp_path)
    fc = rows("final-computation-hour.json")
    required = cnecs.elements(fc)
    calls = []
    def partial(*args, **kwargs):
        calls.append(1)
        return fc[:1]
    monkeypatch.setattr(jao, "_get", partial)
    interval = pd.Timestamp("2024-08-28T22:00:00Z")
    found = jao.load_element_ends(interval, required)
    assert len(found) == len(cnecs.element_ends(fc[:1])) > 0
    assert not (tmp_path / "endpoints/20240828T22Z/element-ends.csv").exists()
    jao.load_element_ends(interval, required)
    assert len(calls) == 2


def test_an_interval_without_binding_elements_does_not_fetch(tmp_path, monkeypatch):
    monkeypatch.setattr(jao, "JAO_DIR", tmp_path)
    monkeypatch.setattr(jao, "_get", lambda *a, **kw: pytest.fail("nothing to locate"))
    required = cnecs.active_constraints(rows("active-fb-day.json")).iloc[:0]
    assert jao.load_element_ends(pd.Timestamp("2024-08-28T22:00:00Z"), required).empty


def test_geometry_discovery_skips_only_conflicting_publication(tmp_path, monkeypatch):
    monkeypatch.setattr(jao, 'JAO_DIR', tmp_path)
    fc = rows('final-computation-hour.json')
    conflict = {**fc[0], 'substationFrom': 'Different synthetic station'}
    monkeypatch.setattr(jao, '_get', lambda *a, **kw: [*fc, conflict])
    interval = pd.Timestamp('2024-08-28T22:00:00Z')
    required = cnecs.elements(fc)
    found = jao.load_element_ends(interval, required)
    assert not ((found.eic == fc[0]['cneEic']) & (found.tso == fc[0]['tso'])).any()
    assert fc[0]['cneEic'] in set(found.eic)  # Another TSO's publication remains usable.
    assert len(found) > 0
    with pytest.raises(ValueError, match='more than one substation pair'):
        cnecs.element_ends([*fc, conflict])


@pytest.mark.parametrize("failed_stage", ["restore", "publish", "local_save", "hourly_save"])
def test_endpoint_discovery_and_persistence_fail_independently(tmp_path, monkeypatch, failed_stage):
    from botocore.exceptions import ClientError
    monkeypatch.setattr(jao, 'JAO_DIR', tmp_path)
    fc = rows('final-computation-hour.json')
    ends = cnecs.element_ends(fc)
    jao.write_element_ends(ends.iloc[:1])
    calls = []

    def broken(*args):
        raise ClientError({'Error': {'Code': '503', 'Message': 'unavailable'}}, 'GetObject')

    monkeypatch.setattr(jao, '_get', lambda *a, **kw: calls.append('fetch') or fc)
    monkeypatch.setattr(jao.cache, 'restore', broken if failed_stage == 'restore' else lambda *a: False)
    monkeypatch.setattr(jao.cache, 'publish', broken if failed_stage == 'publish' else lambda *a: calls.append('publish'))
    if failed_stage == 'local_save':
        monkeypatch.setattr(jao, 'write_element_ends', broken)
    if failed_stage == 'hourly_save':
        monkeypatch.setattr(jao.cache, 'atomic_text', broken)
    found = jao.load_element_ends(pd.Timestamp('2024-08-28T22:00:00Z'), cnecs.elements(fc))
    pd.testing.assert_frame_equal(found.reset_index(drop=True), ends)
    assert 'fetch' in calls
    if failed_stage != 'local_save':
        pd.testing.assert_frame_equal(jao.read_element_ends(), ends)
    if failed_stage in ('restore', 'local_save'):
        assert 'publish' in calls


def test_partial_hourly_cache_survives_failed_refresh(tmp_path, monkeypatch):
    monkeypatch.setattr(jao, 'JAO_DIR', tmp_path)
    fc = rows('final-computation-hour.json')
    ends = cnecs.element_ends(fc)
    seed, hourly = ends.iloc[:1], ends.iloc[1:2]
    jao.write_element_ends(seed)
    directory = tmp_path / 'endpoints/20240828T22Z'
    directory.mkdir(parents=True)
    hourly.to_csv(directory / 'element-ends.csv', index=False)

    def offline(*args, **kwargs):
        raise OSError('upstream unavailable')

    monkeypatch.setattr(jao, '_get', offline)
    found = jao.load_element_ends(pd.Timestamp('2024-08-28T22:00:00Z'), cnecs.elements(fc))
    expected = ends.iloc[:2].reset_index(drop=True)
    pd.testing.assert_frame_equal(found.reset_index(drop=True), expected)
    pd.testing.assert_frame_equal(jao.read_element_ends(), expected)
