"""Export Dash's public files from the same image that serves the application."""
import argparse
from pathlib import Path
import sys
from urllib.parse import urlsplit


def export(dash_app, directory: Path) -> int:
    client = dash_app.server.test_client()
    response = client.get('/')
    if response.status_code != 200:
        raise RuntimeError('Could not initialize Dash resources')

    paths = set()
    # Registered paths include lazy-loaded chunks and Plotly, not only HTML scripts.
    resources = []
    for namespace, files in list(dash_app.registered_paths.items()):
        for name in sorted(files):
            if name.endswith(".map"):
                continue
            paths.add(f'/_dash-component-suites/{namespace}/{name}')
            resources.append({'namespace': namespace, 'relative_package_path': name})
    paths.update(dash_app._collect_and_register_resources(resources))
    assets = Path(dash_app.config.assets_folder)
    for path in assets.rglob('*'):
        if path.is_file():
            paths.add(dash_app.get_asset_url(path.relative_to(assets).as_posix()))

    for url in sorted(paths):
        path = urlsplit(url).path
        response = client.get(path)
        if response.status_code != 200:
            raise RuntimeError(f'Could not export {path}: {response.status_code}')
        target = directory / path.lstrip('/')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(response.data)
    return len(paths)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from app import app

    print(f'Exported {export(app, args.output)} public files to {args.output}')
