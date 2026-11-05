"""Relational contracts use invented catalog data, never downloaded JAO records."""
import shutil
import sqlite3

import pytest

from coppersushi import REPO
from coppersushi.data_sources.element_catalog import InvalidCatalog, load

FIXTURE = REPO / 'tests' / 'fixtures' / 'element-catalog'


def test_valid_catalog_preserves_ambiguous_names_and_distinct_legs():
    with load(FIXTURE) as db:
        assert db.execute("SELECT count(*) FROM site_names WHERE published_name='Central'").fetchone()[0] == 2
        assert db.execute('SELECT count(*) FROM elements').fetchone()[0] == 2
        assert db.execute("SELECT site_id FROM element_endpoints WHERE status='missing'").fetchone()[0] is None
        assert db.execute('PRAGMA foreign_keys').fetchone()[0] == 1


@pytest.mark.parametrize('statement', (FIXTURE / 'invalid.sql').read_text().splitlines())
def test_relational_constraints_reject_invalid_changes(statement):
    with load(FIXTURE) as db, pytest.raises(sqlite3.IntegrityError):
        db.execute(statement)


def test_loader_names_file_and_row_for_duplicate(tmp_path):
    shutil.copytree(FIXTURE, tmp_path, dirs_exist_ok=True)
    path = tmp_path / 'sites.csv'
    with path.open('a') as stream:
        stream.write(path.read_text().splitlines(keepends=True)[1])
    with pytest.raises(InvalidCatalog, match=r'sites.csv:4: UNIQUE'):
        with load(tmp_path):
            pytest.fail('invalid snapshot exposed')


def test_loader_rejects_incomplete_endpoint_pair(tmp_path):
    shutil.copytree(FIXTURE, tmp_path, dirs_exist_ok=True)
    path = tmp_path / 'element_endpoints.csv'
    path.write_text(''.join(path.read_text().splitlines(keepends=True)[:-1]))
    with pytest.raises(InvalidCatalog, match='require from/to'):
        with load(tmp_path):
            pytest.fail('incomplete snapshot exposed')


def test_catalog_projects_publisher_orientation_and_missing_geometry():
    from coppersushi.data_sources.element_catalog import mapped_elements
    frame = mapped_elements(FIXTURE).set_index('name')
    line = frame.loc['Westhaven-Eastfield']
    assert (line.x0, line.y0, line.x1, line.y1) == (3., 46., 4., 46.)
    assert line.bus_source == 'element-catalog'
    assert frame.loc['Westhaven-Unknown'].match_status == 'no_substation'
