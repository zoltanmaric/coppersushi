"""Publish the browser shell and public frontend assets without a serving process."""
import argparse
import gzip
import mimetypes
from typing import Literal
from coppersushi.frontend.packaging.shell import render_shell
from coppersushi import REPO
from coppersushi.pipelines.data_sources import cache
from coppersushi.pipelines.data_sources import credentials


def publish(bucket: str) -> None:
    """Upload assets first, then the shell; deployment invalidates their edge paths."""
    required = ['opf-app.js', 'opf-app.css', 'navigation.css', 'cnec-app.js', 'cnec-app.css', 'plotly-mapbox-3.7.0.min.js',
                'cnec-markers.json', 'cnec-markers.png', 'cnec-markers@2x.json', 'cnec-markers@2x.png']
    dist = REPO / 'coppersushi/frontend/dist'
    assets = dist / 'assets'
    missing = [name for name in required if not (assets / name).is_file()]
    if missing:
        raise ValueError(f'Build frontend assets before publication: {missing}')
    token = credentials.token('MAPBOX_TOKEN', REPO / '.secrets/.mapbox_token')
    shells: list[tuple[str, bool, Literal['cnec', 'opf']]] = [
        ('index.html', False, 'cnec'), ('embed.html', True, 'cnec'),
        ('opf.html', False, 'opf'), ('opf-embed.html', True, 'opf'),
    ]
    for filename, embed, view in shells:
        (dist / filename).write_text(render_shell(token, embed=embed, view=view))
    client = cache._client()
    prefix = 'data/cnec/v1/ui'
    for path in sorted(assets.iterdir()):
        if not path.is_file():
            continue
        content = path.read_bytes()
        kind = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        client.put_object(Bucket=bucket, Key=f'{prefix}/assets/{path.name}', Body=gzip.compress(content, mtime=0),
                          ContentType=kind, ContentEncoding='gzip', CacheControl='public,max-age=0,must-revalidate')
    for filename, _, _ in shells:
        client.put_object(Bucket=bucket, Key=f'{prefix}/{filename}', Body=gzip.compress((dist / filename).read_bytes(), mtime=0),
                          ContentType='text/html;charset=utf-8', ContentEncoding='gzip', CacheControl='public,max-age=60')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bucket', required=True)
    publish(parser.parse_args().bucket)

if __name__ == '__main__':
    main()
