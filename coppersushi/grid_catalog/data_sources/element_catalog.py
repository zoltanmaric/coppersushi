"""Load the four CSV tables through the same relational checks in CI and at runtime.

CSV is the editable source; SQLite is a disposable validator, never a second source
of truth. Empty CSV cells represent SQL NULL. Raw JAO catalogs stay in ignored data/.
"""

import argparse
import csv
import logging
import sqlite3
import pandas as pd
import pandera.pandas as pa
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator

from coppersushi import REPO
from pandera.typing import DataFrame
from coppersushi.data_model.cnec_price_map import MappedCnecElements
from coppersushi.data_model.jao import ActiveConstraints

logger = logging.getLogger(__name__)

SCHEMA = REPO / 'config' / 'element-catalog' / 'schema.sql'
TABLES = ('sites', 'site_names', 'elements', 'element_endpoints')


class InvalidCatalog(ValueError):
    """An invalid CSV value, relational constraint or catalog-wide invariant."""


def snapshot(directory: Path) -> Path:
    """Pin one published generation for the duration of a read."""
    current = directory / 'current'
    return current.resolve(strict=True) if current.is_symlink() else directory


@contextmanager
def load(directory: Path) -> Iterator[sqlite3.Connection]:
    """Validate a whole snapshot atomically and expose it only after all checks pass."""
    directory = snapshot(directory)
    connection = sqlite3.connect(':memory:')
    connection.row_factory = sqlite3.Row
    try:
        connection.executescript(SCHEMA.read_text())
        with connection:
            legacy_elements = False
            for table in TABLES:
                columns = [row['name'] for row in connection.execute(f'PRAGMA table_info({table})')]
                path = directory / f'{table}.csv'
                with path.open(newline='', encoding='utf-8') as stream:
                    reader = csv.reader(stream, strict=True)
                    header = next(reader, None)
                    legacy = {'elements': ['element_id','source','tso','eic','name','element_type'],
                              'element_endpoints': ['element_id','side','published_name','site_id','status','evidence']}
                    old = table in legacy and header == legacy[table]
                    if table == 'elements':
                        legacy_elements = old
                    if header != columns and not old:
                        raise InvalidCatalog(f'{path}: header must be {columns}')
                    for number, row in enumerate(reader, start=2):
                        if len(row) != len(header or []):
                            raise InvalidCatalog(f'{path}:{number}: expected {len(columns)} fields')
                        if old:
                            if table == 'elements':
                                row += ['a_to_b','published','Legacy JAO from/to publication']
                            else:
                                row[1] = {'from':'a','to':'b'}.get(row[1],row[1])
                                row += ['inferred' if row[4]=='resolved' else 'unknown']
                        try:
                            connection.execute(f'INSERT INTO {table} VALUES ({",".join("?" for _ in columns)})',
                                               [value if value != '' else None for value in row])
                        except sqlite3.IntegrityError as error:
                            raise InvalidCatalog(f'{path}:{number}: {error}') from error
            incomplete = connection.execute('''
                SELECT e.element_id FROM elements e LEFT JOIN element_endpoints p USING(element_id)
                GROUP BY e.element_id HAVING count(p.terminal) <> 2
            ''').fetchall()
            if incomplete:
                raise InvalidCatalog(f'element_endpoints.csv: require A/B rows for {[r[0] for r in incomplete]}')
            if legacy_elements:
                connection.execute('''
                    UPDATE elements SET direct_orientation='unknown', orientation_basis='unknown',
                        orientation_evidence='Legacy snapshot lacks reference terminal labels'
                    WHERE element_id IN (SELECT element_id FROM element_endpoints WHERE published_name IS NULL)
                ''')
            unsupported = connection.execute('''
                SELECT e.element_id FROM elements e JOIN element_endpoints p USING(element_id)
                WHERE (e.orientation_basis='published' AND p.published_name IS NULL)
                   OR (e.orientation_basis='inferred' AND p.site_id IS NULL)
            ''').fetchall()
            if unsupported:
                raise InvalidCatalog('Known orientation requires published terminal labels or inferred site assignments')
        yield connection
    finally:
        connection.close()


def mapped_elements(directory: Path) -> DataFrame[MappedCnecElements]:
    """Project a validated catalog into the map's existing oriented geometry contract."""
    import pandas as pd
    from coppersushi.grid_catalog import cnec_geometry as geometry
    from coppersushi.data_model.cnec_price_map import MappedCnecElements

    with load(directory) as db:
        records = []
        for row in db.execute("""
            SELECT e.*, f.site_id AS from_site, t.site_id AS to_site,
                   fs.longitude AS x0, fs.latitude AS y0,
                   ts.longitude AS x1, ts.latitude AS y1
            FROM elements e
            JOIN element_endpoints f ON f.element_id=e.element_id AND f.terminal='a'
            JOIN element_endpoints t ON t.element_id=e.element_id AND t.terminal='b'
            LEFT JOIN sites fs ON fs.site_id=f.site_id
            LEFT JOIN sites ts ON ts.site_id=t.site_id
            WHERE e.source='jao'
        """):
            resolved = row['from_site'] is not None and row['to_site'] is not None and row['direct_orientation'] != 'unknown'
            coordinates = {key: row[key] if resolved else None for key in ('x0','y0','x1','y1')}
            if row['direct_orientation'] == 'b_to_a':
                coordinates = dict(x0=coordinates['x1'], y0=coordinates['y1'],
                                   x1=coordinates['x0'], y1=coordinates['y0'])
            points = sorted([(row['x0'], row['y0']), (row['x1'], row['y1'])]) if resolved else []
            branch = 'osm-locator/' + '--'.join(f'{x:.5f},{y:.5f}' for x,y in points) if resolved else None
            records.append(dict(eic=row['eic'], tso=row['tso'], name=row['name'],
                                element_type=row['element_type'] or '',
                                branch_type='Transformer' if row['element_type'] in geometry.POINT_TYPES else 'Line',
                                branch_id=branch, match_status='matched' if resolved else 'no_substation',
                                bus_source='element-catalog' if resolved else geometry.UNRESOLVED,
                                score=1.0 if resolved else 0.0,
                                **coordinates))
    return pd.DataFrame(records, columns=list(MappedCnecElements.to_schema().columns)).pipe(MappedCnecElements.validate)


def resolve(interval: pd.Timestamp, required: DataFrame[ActiveConstraints], directory: Path) -> DataFrame[MappedCnecElements]:
    """Use reviewed publications first; discover only identities absent from the snapshot.

    A catalog conflict or known unresolved site is authoritative: fetching a new hour must not
    silently bypass a recorded conflict or an ambiguous endpoint. Publications
    missing endpoint metadata remain eligible for discovery.
    """
    import pandas as pd
    from coppersushi.grid_catalog import cnec_geometry
    from coppersushi.data_sources import jao
    from coppersushi.grid_catalog.data_sources import osm_locator

    directory = snapshot(directory)
    mapped = mapped_elements(directory)
    with load(directory) as db:
        pending = {tuple(row) for row in db.execute("""
            SELECT e.eic, e.tso, e.name FROM elements e
            JOIN element_endpoints p USING(element_id)
            GROUP BY e.element_id
            HAVING sum(p.status='missing') > 0
               AND sum(p.status NOT IN ('missing','resolved')) = 0
        """)}
    identity = ['eic', 'tso', 'name']
    authoritative = mapped.loc[[tuple(row) not in pending for row in mapped[identity].itertuples(index=False, name=None)]]
    known = pd.MultiIndex.from_frame(authoritative[identity])
    missing = required.loc[~pd.MultiIndex.from_frame(required[identity]).isin(known)]
    if missing.empty:
        return mapped
    ends = jao.load_element_ends(interval, missing)
    ends = ends.loc[pd.MultiIndex.from_frame(ends[identity]).isin(pd.MultiIndex.from_frame(missing[identity]))]
    if ends.empty:
        return mapped
    try:
        discovered = cnec_geometry.locate_elements(ends, osm_locator.read_csvs(),
                        osm_locator.load_aliases(), osm_locator.load_element_aliases())
    except (OSError, ValueError, KeyError, pa.errors.SchemaError):
        logger.warning("Location discovery could not use the locator; keeping catalog locations", exc_info=True)
        return mapped
    replaced = pd.MultiIndex.from_frame(discovered[identity])
    mapped = mapped.loc[~pd.MultiIndex.from_frame(mapped[identity]).isin(replaced)]
    return pd.concat([mapped, discovered], ignore_index=True).pipe(MappedCnecElements.validate)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    with load(args.directory) as db:
        for table in TABLES:
            print(f'{table}: {db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]} rows')


if __name__ == '__main__':
    main()
