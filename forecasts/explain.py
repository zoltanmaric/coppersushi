"""Export a checked historical run as an offline, read-only explanation website."""
import argparse
from collections import defaultdict
from datetime import date
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pyarrow.parquet as pq

from .scoring import metrics
from .input_types import Report, Row
from .config import QUANTILES
from .dataset import BERLIN, cutoff

Scores = dict[str, dict[str, float | int]]

ROOT = Path(__file__).resolve().parents[1]
METHODS = ('system', 'reference', 'prices', 'weather', 'demand')

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scores(rows: list[Row]) -> Scores:
    common = [r for r in rows if r['target'] is not None]
    days = [r['delivery_date'] for r in common]
    return {name: metrics([r['target'] for r in common],
                          [[r[f'{name}_q{q}'] for q in QUANTILES] for r in common],
                          days) for name in METHODS}


def reconcile(actual: Scores, expected: Scores) -> None:
    for name in METHODS:
        if actual[name].keys() != expected[name].keys():
            raise ValueError(f'Metric fields differ for {name}')
        for key, value in actual[name].items():
            if not np.isclose(value, expected[name][key], atol=1e-6, rtol=1e-9):
                raise ValueError(f'Metric mismatch: {name}.{key}')


def build_payload(run: Path) -> Report:
    manifest = json.loads((run / 'manifest.json').read_text())
    for name in ('predictions.parquet', 'report.json', 'config.json'):
        if digest(run / name) != manifest['artifacts'][name]:
            raise ValueError(f'Artifact checksum mismatch: {name}')
    config = json.loads((run / 'config.json').read_text())
    if config != manifest['config']:
        raise ValueError('Configuration differs from manifest')
    if config['quantiles'] != list(QUANTILES):
        raise ValueError('Unsupported quantile contract')
    report = json.loads((run / 'report.json').read_text())
    rows = pq.read_table(run / 'predictions.parquet').to_pylist()
    if not rows:
        raise ValueError('No predictions to explain')
    rows.sort(key=lambda r: r['delivery_utc'])
    timestamps = [r['delivery_utc'] for r in rows]
    if len(set(timestamps)) != len(rows):
        raise ValueError('Duplicate delivery timestamps')
    for row in rows:
        local = row['delivery_utc'].astimezone(BERLIN)
        if local.date() != row['delivery_date']:
            raise ValueError('Delivery date disagrees with Europe/Berlin timestamp')
        if row['target'] is not None and not np.isfinite(row['target']):
            raise ValueError('Non-finite target')
        for name in METHODS:
            q = [row[f'{name}_q{p}'] for p in QUANTILES]
            if not np.isfinite(q).all() or any(a > b for a, b in zip(q, q[1:])):
                raise ValueError('Expected finite ordered quantiles, including unscored rows')
    if (len(rows) != report['delivery_rows']
            or sum(r['target'] is None for r in rows) != report['missing_truth']
            or sum(r['target'] is not None for r in rows) != report['scored_rows']):
        raise ValueError('Report population differs from predictions')
    reconcile(scores(rows), report['metrics'])
    grouped: dict[date, list[Row]] = defaultdict(list)
    months: dict[str, list[Row]] = defaultdict(list)
    for row in rows:
        grouped[row['delivery_date']].append(row)
        months[row['delivery_date'].strftime('%Y-%m')].append(row)
    for month, selected in months.items():
        reconcile(scores(selected), report['breakdowns']['month'][month]['metrics'])
    folds = {f['first_delivery_day']: f for f in report['folds']}
    days = []
    for day, selected in sorted(grouped.items()):
        fold_ids = {r['fold'].isoformat() for r in selected}
        if len(fold_ids) != 1 or not fold_ids <= folds.keys():
            raise ValueError('Day does not resolve to one recorded fold')
        issue = cutoff(day).astimezone(BERLIN)
        points = []
        for row in selected:
            local = row['delivery_utc'].astimezone(BERLIN)
            points.append({'utc': row['delivery_utc'].isoformat(), 'clock': local.strftime('%H:%M %Z'),
                           'actual': row['target'], 'q': {n: [row[f'{n}_q{q}'] for q in QUANTILES] for n in METHODS},
                           'selected': row['selected_model'], 'reason': row['fallback_reason'],
                           'demand_update': row['demand_selected_update_utc'].isoformat() if row['demand_selected_update_utc'] is not None else None,
                           'missing': [k.removesuffix('_missing') for k, v in row.items() if k.endswith('_missing') and v]})
        days.append({'date': day.isoformat(), 'issue': issue.isoformat(), 'fold': selected[0]['fold'].isoformat(),
                     'metrics': scores(selected), 'missing_truth': sum(r['target'] is None for r in selected),
                     'points': points})
    revision = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    sources = {}
    for key, source in json.loads((ROOT / 'forecasts/web/sources.json').read_text()).items():
        name = source['path']
        if digest(ROOT / name) != source['sha256']:
            raise ValueError(f'Explainer source changed; review narrative and update sources.json: {name}')
        # Reject uncommitted knowledge: a revision link must identify the bytes used.
        committed = subprocess.check_output(['git', '-C', str(ROOT), 'show', f'{revision}:{name}'])
        if (ROOT / name).read_bytes() != committed:
            raise ValueError(f'Commit wiki source before export: {name}')
        sources[key] = {'path': name, 'sha256': digest(ROOT / name), 'revision': revision,
                        'url': f'https://github.com/zoltanmaric/coppersushi/blob/{revision}/{name}'}
    return {'schema_version': 1, 'run': {k: manifest[k] for k in
            ('run_id', 'code_revision', 'exploratory', 'mlflow_run_id', 'metaflow_run_id')},
            'snapshot': config['snapshot_id'], 'manifest_sha256': digest(run / 'manifest.json'),
            'config': {k: config[k] for k in ('train_start', 'evaluation_start', 'end_exclusive', 'catboost')},
            'features': {n: len(v) for n, v in config['features'].items()},
            'sources': sources,
            'presentation_sha256': {p.name: digest(p) for p in sorted((ROOT / 'forecasts/web').iterdir()) if p.is_file()},
            'report': {k: report[k] for k in
                ('metrics', 'comparison', 'delivery_rows', 'scored_rows', 'missing_truth', 'breakdowns',
                 'timing_limits', 'limitations', 'raw_crossing_fraction', 'prediction_failures', 'fallback_rows')},
            'pipeline': json.loads((ROOT / 'forecasts/web/pipeline.json').read_text()),
            'folds': folds, 'days': days}


def export(run: Path, output: Path) -> Path:
    if output.exists():
        raise ValueError('Choose a new output directory; exports are never overwritten')
    payload = build_payload(run)
    output.mkdir(parents=True)
    for source in (ROOT / 'forecasts/web').iterdir():
        if source.is_file():
            shutil.copyfile(source, output / source.name)
    (output / 'data.js').write_text('window.FORECAST = ' + json.dumps(payload, allow_nan=False, separators=(',', ':')) + ';\n')
    return output / 'index.html'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(export(args.run, args.output).resolve())


if __name__ == '__main__':
    main()
