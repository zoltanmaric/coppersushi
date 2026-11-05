"""The locator CSVs may not be redistributed, so these run on synthesised look-alikes.

They reproduce the real format's quirks — the headerless name column, diacritics, punctuation,
and one name repeated across two templates. The real measurements at the pinned commit are in
the PR body.
"""

import pandas as pd
import pytest

from coppersushi import REPO
from coppersushi.data_sources import osm_locator

FIXTURES = REPO / "tests" / "fixtures" / "synthetic-osm-locator"


@pytest.fixture(autouse=True)
def synthetic_templates(monkeypatch):
    monkeypatch.setattr(osm_locator, 'EXPECTED_TEMPLATES', frozenset({'ZA', 'ZA225kv', 'ZB'}))


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("Core _Static Grid Model_template_ZA_OSM_corrected.csv", "ZA"),
        ("Core _Static Grid Model_template_ZA225kv_OSM_corrected.csv", "ZA225kv"),
        ("Core _Static Grid Model_ZB_Q4-2021_all_EIC_0_OSM_corrected.csv", "ZB"),
    ],
)
def test_the_template_token_comes_from_the_filename(filename, expected):
    assert osm_locator.template_token(filename) == expected


def test_a_filename_of_another_shape_is_refused():
    with pytest.raises(RuntimeError, match="no template token"):
        osm_locator.template_token("substations.csv")


def test_the_headerless_first_column_becomes_the_name():
    assert "Zähringen Süd" in set(osm_locator.read_csvs(FIXTURES).name)


def test_a_row_without_coordinates_is_not_a_location():
    """The CSVs keep the names nobody found; they cannot serve a coordinate lookup."""
    assert not osm_locator.read_csvs(FIXTURES).name.eq("NEVER FOUND").any()


def test_a_name_in_two_templates_keeps_both_rows():
    """Which of the two answers a JAO name is the matcher's decision, not the reader's."""
    rows = osm_locator.read_csvs(FIXTURES).set_index("template").loc[["ZA", "ZA225kv"]]
    assert sorted(rows[rows.name.eq("TWO PLACES")].x) == [6.0, 7.0]


def test_a_missing_osm_id_survives_as_missing_rather_than_a_number():
    frame = osm_locator.read_csvs(FIXTURES)
    assert frame.set_index("name").osm_id.loc["Zähringen Süd"] == 111111111
    assert frame.loc[frame.template.eq("ZA225kv") & frame.name.eq("TWO PLACES"), "osm_id"].isna().all()


def test_a_coordinate_outside_europe_is_refused_where_it_is_loaded():
    """A column-shifted or corrupt download has to fail at the boundary, not on a map."""
    frame = osm_locator.read_csvs(FIXTURES)
    with pytest.raises(RuntimeError, match=r"rows with x outside"):
        osm_locator.check_located(frame.assign(x=frame.x + 200.0))
    with pytest.raises(RuntimeError, match=r"rows with y outside"):
        osm_locator.check_located(frame.assign(y=pd.NA))


def test_incomplete_locator_is_rejected(tmp_path):
    import shutil
    shutil.copytree(FIXTURES, tmp_path/'locator')
    next((tmp_path/'locator').glob('*ZA225kv*')).unlink()
    with pytest.raises(RuntimeError, match='Incomplete locator templates'):
        osm_locator.read_csvs(tmp_path/'locator')


def test_duplicate_template_cannot_replace_a_missing_template(tmp_path):
    import shutil
    shutil.copytree(FIXTURES, tmp_path/'locator')
    next((tmp_path/'locator').glob('*ZA225kv*')).unlink()
    source = next((tmp_path/'locator').glob('*template_ZA_*'))
    shutil.copyfile(source, source.with_name(source.stem+'-duplicate.csv'))
    with pytest.raises(RuntimeError, match='Incomplete locator templates'):
        osm_locator.read_csvs(tmp_path/'locator')


def test_download_is_validated_before_replacing_cached_locator(tmp_path):
    import shutil
    shutil.copytree(FIXTURES, tmp_path/'locator')
    before = {p.name: p.read_bytes() for p in (tmp_path/'locator').glob('*.csv')}
    payload = (FIXTURES.parent/'synthetic-osm-locator-invalid.tar.gz').read_bytes()
    with pytest.raises(pd.errors.ParserError):
        osm_locator.write_csvs(tmp_path/'locator', payload)
    assert before == {p.name: p.read_bytes() for p in (tmp_path/'locator').glob('*.csv')}
    assert not osm_locator.read_csvs(tmp_path/'locator').empty
