"""Publish the browser shell and public frontend assets without a serving process."""
import argparse
import gzip
import mimetypes
from pathlib import Path
from typing import Literal
from frontend.shell import navigation_html
from coppersushi import REPO
import json
from coppersushi.cnec_support import FIRST_DAY
from coppersushi.data_sources import cache, credentials


def render_shell(token: str, *, embed: bool = False, view: Literal['cnec', 'opf'] = 'cnec') -> str:
    """Build a date-independent shell with safely embedded browser configuration."""
    config = json.dumps({'min_day': FIRST_DAY.isoformat(), 'token': token} if view == 'cnec' else {'token': token}).replace('<', r'\u003c')
    template = (REPO / 'frontend/index.html').read_text()
    template = template.replace('__APP_BUNDLE__', f'{view}-app')
    if view == 'opf':
        template = template.replace('Critical Elements', 'Power Flow').replace('A tool that shows exactly why day-ahead prices split between countries.', 'Hourly optimal power flow on the European grid.').replace('/cnec"', '/opf-2024"').replace('critical-elements-preview.png', 'copper-sushi-screenshot.png')
    return template.replace('__APP_NAVIGATION__', navigation_html()).replace('__CNEC_EMBED__', str(embed).lower()).replace('__CNEC_CONFIG__', config)


def publish(bucket: str) -> None:
    """Upload assets first, then the shell; deployment invalidates their edge paths."""
    required = ['opf-app.js', 'opf-app.css', 'navigation.css', 'cnec-app.js', 'cnec-app.css', 'plotly-mapbox-3.7.0.min.js',
                'cnec-markers.json', 'cnec-markers.png', 'cnec-markers@2x.json', 'cnec-markers@2x.png']
    missing = [name for name in required if not (REPO / 'assets' / name).is_file()]
    if missing:
        raise ValueError(f'Build frontend assets before publication: {missing}')
    token = credentials.token('MAPBOX_TOKEN', REPO / '.secrets/.mapbox_token')
    client = cache._client()
    prefix = 'data/cnec/v1/ui'
    for path in sorted((REPO / 'assets').iterdir()):
        if not path.is_file() or path.name.startswith('cnec-view.'):
            continue
        content = path.read_bytes()
        kind = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        client.put_object(Bucket=bucket, Key=f'{prefix}/assets/{path.name}', Body=gzip.compress(content, mtime=0),
                          ContentType=kind, ContentEncoding='gzip', CacheControl='public,max-age=0,must-revalidate')
    shells: list[tuple[str, bool, Literal['cnec', 'opf']]] = [
        ('index.html', False, 'cnec'), ('embed.html', True, 'cnec'),
        ('opf.html', False, 'opf'), ('opf-embed.html', True, 'opf'),
    ]
    for filename, embed, view in shells:
        html = render_shell(token, embed=embed, view=view)
        client.put_object(Bucket=bucket, Key=f'{prefix}/{filename}', Body=gzip.compress(html.encode(), mtime=0),
                          ContentType='text/html;charset=utf-8', ContentEncoding='gzip', CacheControl='public,max-age=60')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bucket', required=True)
    publish(parser.parse_args().bucket)

if __name__ == '__main__':
    main()
