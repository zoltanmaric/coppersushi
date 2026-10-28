#!/usr/bin/env python3
"""Check sitemap pages and same-origin HTML media for a site."""
import argparse
from html.parser import HTMLParser
import json
from urllib.parse import urljoin, urlsplit
from urllib.request import urlopen
import xml.etree.ElementTree as ET


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('img', 'script', 'source', 'video', 'audio'):
            for key in ('src', 'poster'):
                if attrs.get(key):
                    self.urls.add(attrs[key])
            for entry in attrs.get('srcset', '').split(','):
                if entry.strip():
                    self.urls.add(entry.strip().split()[0])
        if tag == 'link' and attrs.get('rel') in ('stylesheet', 'icon'):
            if attrs.get('href'):
                self.urls.add(attrs['href'])


def verify(base):
    base = base.rstrip('/') + '/'
    origin = urlsplit(base).netloc
    if urlsplit(base).scheme not in ('http', 'https'):
        raise ValueError('Expected an HTTP or HTTPS site URL')
    sitemap_queue = [urljoin(base, 'sitemap.xml')]
    visited = set()
    pages = set()
    assets = set()
    failures = []

    def read(url):
        with urlopen(url, timeout=30) as response:
            if urlsplit(response.url).netloc != origin:
                raise ValueError('Redirect left requested origin: ' + response.url)
            return response.read()

    while sitemap_queue:
        url = sitemap_queue.pop()
        if url in visited:
            continue
        visited.add(url)
        try:
            tree = ET.fromstring(read(url))
            namespace = '{http://www.sitemaps.org/schemas/sitemap/0.9}'
            if tree.tag not in ('sitemapindex', 'urlset', namespace + 'sitemapindex', namespace + 'urlset'):
                raise ValueError('Expected sitemapindex or urlset, not ' + tree.tag)
            index = tree.tag in ('sitemapindex', namespace + 'sitemapindex')
            entries = tree.findall('./{*}sitemap' if index else './{*}url')
            links = [(entry.findtext('{*}loc') or '').strip() for entry in entries]
            for link in links:
                if urlsplit(link).scheme not in ('http', 'https') or urlsplit(link).netloc != origin:
                    raise ValueError('Sitemap points outside the requested origin: ' + link)
            if index:
                sitemap_queue.extend(links)
            else:
                pages.update(links)
        except Exception as error:
            failures.append({'url': url, 'error': str(error)})
    if not pages:
        failures.append({'url': base, 'error': 'No pages found in sitemaps'})
    pages.add(base)
    for url in sorted(pages):
        try:
            parser = Assets()
            parser.feed(read(url).decode('utf-8'))
            for asset in parser.urls:
                absolute = urljoin(url, asset)
                if urlsplit(absolute).netloc == origin:
                    assets.add(absolute)
        except Exception as error:
            failures.append({'url': url, 'error': str(error)})
    for url in sorted(assets):
        try:
            read(url)
        except Exception as error:
            failures.append({'url': url, 'error': str(error)})
    return {'pages': len(pages), 'assets': len(assets), 'failures': failures,
            'scope': 'Sitemap pages and same-origin HTML assets; external embeds and CSS URLs require browser review.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base', help='Site origin, e.g. https://blog.example.org')
    args = parser.parse_args()
    report = verify(args.base)
    print(json.dumps(report, indent=2))
    raise SystemExit(bool(report['failures']))
