"""Export a solved network as validated numeric data, with no Plotly figures."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

from coppersushi.pipelines.data_sources import cache
from coppersushi.pipelines.powerflow.export import extract
from coppersushi.pipelines.powerflow.data_sources import networks

def publish(network: Path, output: Path, bucket: str | None = None) -> None:
    """Write a solved network as browser data and optionally publish it to S3."""
    dataset = extract(networks.load(network))
    output.parent.mkdir(parents=True, exist_ok=True)
    content = dataset.model_dump_json().encode()
    generation = hashlib.sha256(content).hexdigest()[:24]
    target = output / generation
    target.mkdir(parents=True, exist_ok=True)
    metadata = dataset.model_dump(mode='json', exclude={'intervals'})
    (target / 'metadata.json').write_text(json.dumps(metadata, allow_nan=False))
    for index, interval in enumerate(dataset.intervals):
        (target / f'{index}.json').write_text(interval.model_dump_json())
    (output / 'schema.json').write_text(json.dumps(type(dataset).model_json_schema()))
    # Publish the pointer only after every file in the generation is complete.
    manifest = {'version': 2, 'generation': generation,
                'snapshots': [interval.timestamp.isoformat() for interval in dataset.intervals]}
    temporary = output / 'manifest.json.tmp'
    temporary.write_text(json.dumps(manifest))
    temporary.replace(output / 'manifest.json')
    if bucket:
        client = cache._client()
        files = [*sorted(target.iterdir()), output / 'manifest.json']
        for path in files:
            name = path.relative_to(output).as_posix()
            client.put_object(Bucket=bucket, Key=f'data/opf/v2/opf-2024/{name}',
                Body=gzip.compress(path.read_bytes(), mtime=0), ContentType='application/json',
                ContentEncoding='gzip', CacheControl='public,max-age=60' if name == 'manifest.json'
                else 'public,max-age=31536000,immutable')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('network', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--bucket')
    args = parser.parse_args()
    publish(args.network, args.output, args.bucket)


if __name__ == '__main__':
    main()
