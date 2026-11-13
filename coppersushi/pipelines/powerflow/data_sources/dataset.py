"""Export a solved network as validated numeric data, with no Plotly figures."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

from coppersushi.pipelines.data_sources import cache
from coppersushi.pipelines.powerflow.export import extract
from coppersushi.pipelines.powerflow.data_sources import networks

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('network', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--bucket')
    parser.add_argument('--serve', action='store_true', help='Preview this prepared network locally')
    args = parser.parse_args()
    dataset = extract(networks.load(args.network))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    content = dataset.model_dump_json().encode()
    generation = hashlib.sha256(content).hexdigest()[:24]
    target = args.output / generation
    target.mkdir(parents=True, exist_ok=True)
    metadata = dataset.model_dump(mode='json', exclude={'intervals'})
    (target / 'metadata.json').write_text(json.dumps(metadata, allow_nan=False))
    for index, interval in enumerate(dataset.intervals):
        (target / f'{index}.json').write_text(interval.model_dump_json())
    (args.output / 'schema.json').write_text(json.dumps(type(dataset).model_json_schema()))
    # Publish the pointer only after every file in the generation is complete.
    manifest = {'version': 2, 'generation': generation,
                'snapshots': [interval.timestamp.isoformat() for interval in dataset.intervals]}
    temporary = args.output / 'manifest.json.tmp'
    temporary.write_text(json.dumps(manifest))
    temporary.replace(args.output / 'manifest.json')
    if args.bucket:
        client = cache._client()
        files = [*sorted(target.iterdir()), args.output / 'manifest.json']
        for path in files:
            name = path.relative_to(args.output).as_posix()
            client.put_object(Bucket=args.bucket, Key=f'data/opf/v2/opf-2024/{name}',
                Body=gzip.compress(path.read_bytes(), mtime=0), ContentType='application/json',
                ContentEncoding='gzip', CacheControl='public,max-age=60' if name == 'manifest.json'
                else 'public,max-age=31536000,immutable')
    if args.serve:
        from coppersushi.frontend.packaging.preview import create_app
        app = create_app(production_data=True)
        app.config['OPF_PREVIEW_DIRECTORY'] = args.output.resolve()
        app.run(host='127.0.0.1', port=8050)



if __name__ == '__main__':
    main()
