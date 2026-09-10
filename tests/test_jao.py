import json

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
                                               cnecs.external_constraints(sp)))
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


def test_every_table_comes_back_with_its_zone(tmp_path):
    day = written(tmp_path)
    assert [str(frame.hour.dt.tz) for frame in day] == ["UTC"] * len(jao.Day._fields)


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
