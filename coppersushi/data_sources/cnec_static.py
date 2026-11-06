"""Publish the browser shell and public frontend assets without a serving process."""
import argparse
import gzip
import mimetypes
from pathlib import Path
from coppersushi import REPO
from coppersushi.data_sources import cache


def publish(bucket: str) -> None:
    """Upload assets first, then the shell; deployment invalidates their edge paths."""
    from cnec_server import server, index
    required = ['cnec-app.js', 'cnec-app.css', 'plotly-mapbox-3.7.0.min.js',
                'cnec-markers.json', 'cnec-markers.png', 'cnec-markers@2x.json', 'cnec-markers@2x.png']
    missing = [name for name in required if not (REPO / 'assets' / name).is_file()]
    if missing:
        raise ValueError(f'Build frontend assets before publication: {missing}')
    with server.app_context():
        html = index()
    if not isinstance(html, str):
        raise ValueError('Static shell did not render')
    client = cache._client()
    prefix = 'data/cnec/v1/ui'
    for path in sorted((REPO / 'assets').iterdir()):
        if not path.is_file() or path.name.startswith('cnec-view.'):
            continue
        content = path.read_bytes()
        kind = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        client.put_object(Bucket=bucket, Key=f'{prefix}/assets/{path.name}', Body=gzip.compress(content, mtime=0),
                          ContentType=kind, ContentEncoding='gzip', CacheControl='public,max-age=0,must-revalidate')
    client.put_object(Bucket=bucket, Key=f'{prefix}/index.html', Body=gzip.compress(html.encode(), mtime=0),
                      ContentType='text/html;charset=utf-8', ContentEncoding='gzip', CacheControl='public,max-age=60')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bucket', required=True)
    publish(parser.parse_args().bucket)

if __name__ == '__main__':
    main()
