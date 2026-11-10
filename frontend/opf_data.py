"""Publish immutable OPF hours before their public manifest."""
import argparse
import gzip
import hashlib
import json
from datetime import datetime
from pathlib import Path

from coppersushi.data_sources import cache


def objects(directory: Path) -> tuple[dict[str, bytes], bytes]:
    times = json.loads((directory / 'snapshots.json').read_text())
    if not isinstance(times, list) or not times:
        raise ValueError('OPF snapshots must be a nonempty timestamp list')
    parsed = [datetime.fromisoformat(t) for t in times]
    if any(t.tzinfo is None for t in parsed) or parsed != sorted(set(parsed)):
        raise ValueError('OPF timestamps must be ordered, unique and timezone-aware')
    hours = {}
    for index in range(len(times)):
        content = gzip.decompress((directory / f'{index}.json.gz').read_bytes())
        figure = json.loads(content)
        if not isinstance(figure.get('data'), list) or not isinstance(figure.get('layout', {}).get('mapbox'), dict):
            raise ValueError(f'Invalid OPF figure {index}')
        if figure['layout']['mapbox'].get('accesstoken'):
            raise ValueError('Published OPF figures must be token-free')
        hours[f'{index}.json'] = content
    digest = hashlib.sha256(json.dumps(times).encode())
    for content in hours.values():
        digest.update(content)
    generation = digest.hexdigest()[:24]
    manifest = json.dumps({'generation': generation, 'snapshots': times}).encode()
    return {f'{generation}/{name}': value for name, value in hours.items()}, manifest


def publish(directory: Path, *, bucket: str | None, output: Path | None) -> None:
    hours, manifest = objects(directory)
    client = cache._client() if bucket else None
    for name, content in [*hours.items(), ('manifest.json', manifest)]:
        if output:
            path = output / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        if client:
            client.put_object(Bucket=bucket, Key=f'data/opf/v1/opf-2024/{name}',
                              Body=gzip.compress(content, mtime=0), ContentType='application/json',
                              ContentEncoding='gzip', CacheControl='public,max-age=60' if name == 'manifest.json'
                              else 'public,max-age=31536000,immutable')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument('--bucket')
    destination.add_argument('--output', type=Path)
    args = parser.parse_args()
    publish(args.directory, bucket=args.bucket, output=args.output)


if __name__ == '__main__':
    main()
