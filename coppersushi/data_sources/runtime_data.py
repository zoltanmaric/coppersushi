"""Prepare and validate the static tables required by local and container startup."""
import argparse
import csv
import hashlib
import logging
import os
from pathlib import Path
import urllib.request

import pandera.pandas as pa

from coppersushi import REPO
from coppersushi.market_day import MarketDay
from coppersushi.grid_catalog.data_sources import catalog_backfill
from coppersushi.grid_catalog.data_sources import catalog_sweep
from coppersushi.grid_catalog.data_sources import element_catalog
from coppersushi.data_sources import jao
from coppersushi.opf.data_sources import networks
from coppersushi.grid_catalog.data_sources import osm_locator
from coppersushi.grid_catalog.data_sources import zone_shapes

logger = logging.getLogger(__name__)
SETUP_COMMAND = 'pixi run --locked setup-app'
# A fixed seed day makes fresh checkouts independent of the latest publication's availability.
SEED_DAY = '2026-09-11'
BUSES_URL = 'https://zenodo.org/records/18619025/files/buses.csv'
BUSES_SHA256 = 'f50c75ea0339f5578ae383b47a1c0564b371c5d0d60fd4181ed626c7f3a5a523'


def catalog_directory() -> Path:
    return Path(os.environ.get('COPPERSUSHI_ELEMENT_CATALOG', str(REPO/'data/element-catalog')))


def check_sources() -> None:
    """Validate bundled source tables without requesting upstream data."""
    if jao.read_element_ends().empty:
        raise ValueError('JAO endpoint seed is empty')
    if osm_locator.read_csvs().empty:
        raise ValueError('OSM locator is empty')
    with element_catalog.load(catalog_directory()) as db:
        for table in element_catalog.TABLES:
            if not db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]:
                raise ValueError(f'element catalog table {table} is empty')


def check(*, sources_only: bool = False) -> None:
    """Fail before serving if a required static table or solved network is absent."""
    try:
        check_sources()
        if sources_only:
            return
        if zone_shapes.load().empty:
            raise ValueError('country outlines are empty')
        path = networks.solved('2024-08-29')
        with path.open('rb') as stream:
            if stream.read(64).startswith(b'version https://git-lfs'):
                raise ValueError('solved network is a Git LFS pointer')
    except (OSError, ValueError, RuntimeError, KeyError, csv.Error, pa.errors.SchemaError) as error:
        raise RuntimeError(f'Application data is missing or invalid: {error}. Run `{SETUP_COMMAND}`.') from error


def prepare(day: MarketDay, refresh: bool = False) -> None:
    """Build local tables from cached inputs, downloading absent inputs once."""
    root = REPO/'data'
    backfill = root/'research/element-catalog'
    if jao.JAO_DIR != root/'jao':
        raise ValueError('Prepare checkout data without COPPERSUSHI_DATA_DIR; runtime caches are separate')
    try:
        if refresh:
            raise FileNotFoundError('refresh requested')
        if osm_locator.read_csvs().empty:
            raise ValueError('empty locator')
    except (OSError, ValueError, RuntimeError, KeyError, pa.errors.SchemaError):
        logger.info('Preparing OSM locator')
        osm_locator.fetch()
        osm_locator.read_csvs()
    buses = root/'osm-prebuilt-v0.7/buses.csv'
    if refresh or not buses.exists() or hashlib.sha256(buses.read_bytes()).hexdigest() != BUSES_SHA256:
        logger.info('Downloading pinned OSM buses')
        with urllib.request.urlopen(BUSES_URL, timeout=60) as response:
            payload = response.read()
        if hashlib.sha256(payload).hexdigest() != BUSES_SHA256:
            raise ValueError('OSM buses checksum mismatch')
        buses.parent.mkdir(parents=True, exist_ok=True)
        temporary = buses.with_suffix('.partial')
        temporary.write_bytes(payload)
        temporary.replace(buses)
    if hashlib.sha256(buses.read_bytes()).hexdigest() != BUSES_SHA256:
        raise ValueError('Cached OSM buses checksum mismatch; rerun setup-data with --refresh')
    seed_day = day.date.isoformat()
    try:
        if refresh:
            raise FileNotFoundError('refresh requested')
        jao.read_day(jao.day_dir(seed_day))
    except (OSError, ValueError, RuntimeError, KeyError, pa.errors.SchemaError):
        logger.info('Preparing JAO domain for %s', day.date)
        jao.fetch_day(seed_day)
    # Reading validates every domain table; an interrupted download cannot become a seed.
    jao.read_day(jao.day_dir(seed_day))
    try:
        if refresh:
            raise FileNotFoundError('refresh requested')
        if jao.read_element_ends().empty:
            raise ValueError('empty endpoint seed')
    except (OSError, ValueError, RuntimeError, KeyError, pa.errors.SchemaError):
        jao.seed_element_ends([seed_day])
    catalog_backfill.fetch_site_evidence(backfill, refresh=refresh)
    logger.info('Compiling element catalog')
    summary = catalog_sweep.sweep(root, backfill, catalog_directory())
    logger.info('Catalog: %s', summary)
    try:
        if refresh:
            raise FileNotFoundError('refresh requested')
        if zone_shapes.load().empty:
            raise ValueError('empty country outlines')
    except (OSError, ValueError, RuntimeError, KeyError, pa.errors.SchemaError):
        logger.info('Building country outlines')
        zone_shapes.build()
    check()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'check'])
    parser.add_argument('--day', default=SEED_DAY, help='domain seed delivery day (default: %(default)s)')
    parser.add_argument('--refresh', action='store_true', help='replace downloaded inputs')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    if args.action == 'check':
        check()
    else:
        prepare(MarketDay.on(args.day), args.refresh)


if __name__ == '__main__':
    main()
