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
    with pytest.raises(InvalidCatalog, match='require A/B'):
        with load(tmp_path):
            pytest.fail('incomplete snapshot exposed')


def test_catalog_projects_publisher_orientation_and_missing_geometry():
    from coppersushi.data_sources.element_catalog import mapped_elements
    frame = mapped_elements(FIXTURE).set_index('name')
    line = frame.loc['Westhaven-Eastfield']
    assert (line.x0, line.y0, line.x1, line.y1) == (3., 46., 4., 46.)
    assert line.bus_source == 'element-catalog'
    assert frame.loc['Westhaven-Unknown'].match_status == 'no_substation'


def test_orientation_is_independent_of_assignment_basis():
    from coppersushi.data_sources.element_catalog import mapped_elements
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        shutil.copytree(FIXTURE, root, dirs_exist_ok=True)
        path = root/'elements.csv'
        path.write_text(path.read_text().replace('a_to_b,published,synthetic', 'b_to_a,inferred,synthetic'))
        line = mapped_elements(root).set_index('name').loc['Westhaven-Eastfield']
        assert (line.x0, line.x1) == (4., 3.)
        path.write_text(path.read_text().replace('b_to_a,inferred,synthetic', 'unknown,unknown,synthetic'))
        assert mapped_elements(root).set_index('name').loc['Westhaven-Eastfield'].match_status == 'no_substation'


def test_sql_rejects_false_orientation_and_assignment_claims():
    with load(FIXTURE) as db:
        for statement in [
            "UPDATE elements SET direct_orientation='unknown' WHERE element_id='line-a'",
            "UPDATE element_endpoints SET assignment_basis='unknown' WHERE status='resolved'",
            "UPDATE element_endpoints SET assignment_basis='inferred' WHERE status='missing'",
        ]:
            with pytest.raises(sqlite3.IntegrityError):
                db.execute(statement)


def test_legacy_snapshot_preserves_sites_and_projection(tmp_path):
    import csv
    from coppersushi.data_sources.element_catalog import mapped_elements
    shutil.copytree(FIXTURE,tmp_path,dirs_exist_ok=True)
    for table in ('elements','element_endpoints'):
        path=tmp_path/f'{table}.csv'
        records=list(csv.DictReader(path.open()))
        if table=='elements':
            columns=['element_id','source','tso','eic','name','element_type']
        else:
            columns=['element_id','side','published_name','site_id','status','evidence']
            for row in records:row['side']={'a':'from','b':'to'}[row['terminal']]
        with path.open('w') as stream:
            writer=csv.DictWriter(stream,fieldnames=columns,extrasaction='ignore')
            writer.writeheader();writer.writerows(records)
    frame=mapped_elements(tmp_path).set_index('name')
    assert (frame.loc['Westhaven-Eastfield'].x0,frame.loc['Westhaven-Eastfield'].x1)==(3.,4.)
    assert frame.loc['Westhaven-Unknown'].match_status=='no_substation'
