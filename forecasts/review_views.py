"""Install versioned MLflow review views and print the forecast review entry link."""
import argparse
import base64
import importlib.metadata
import json
from pathlib import Path
import time
import zlib

from forecasts.run import tracking_client


def install(base_url: str) -> None:
    config = json.loads(Path(__file__).with_name('review-views.json').read_text())
    if importlib.metadata.version('mlflow') != config['mlflow_version']:
        raise ValueError('Verify the saved-view format with the installed MLflow version first')
    client = tracking_client()
    experiment = client.get_experiment_by_name(config['experiment_name'])
    if experiment is None:
        raise ValueError('Load the local forecast tracking records before installing review views')
    links = {}
    for key, view in config['views'].items():
        view_id = f'forecast-{key}'
        tag = f'mlflow.sharedViewState.{view_id}'
        old = json.loads(experiment.tags.get(tag, '{}'))
        now = int(time.time() * 1000)
        state = 'deflate;' + base64.b64encode(zlib.compress(json.dumps(view['state']).encode())).decode()
        client.set_experiment_tag(experiment.experiment_id, tag, json.dumps({
            'name': view['name'], 'createdAt': old.get('createdAt', now),
            'updatedAt': now, 'state': state}))
        links[key] = f'{base_url.rstrip("/")}/#/experiments/{experiment.experiment_id}/runs?viewStateShareKey={view_id}'
    print('Forecast review: ' + links[config['default_view']])
    for key, url in links.items():
        if key != config['default_view']:
            print(config['views'][key]['name'] + ': ' + url)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:5001')
    install(parser.parse_args().url)
