"""Mapbox's own basemap styles, fetched with the account token.

Mapbox's terms keep its style documents its own, so a style is fetched at run time and
held in memory: never written to disk, never committed.
"""

import json
import urllib.parse
import urllib.request

API = "https://api.mapbox.com"
STYLES = f"{API}/styles/v1"
DARK = "mapbox/dark-v11"
SCHEME = "mapbox://"
TIMEOUT_SECONDS = 30


def fetch(token: str, style: str = DARK) -> dict:
    """The style document Plotly's ``mapbox.style`` accepts in place of a preset name."""
    query = urllib.parse.urlencode({"access_token": token})
    with urllib.request.urlopen(f"{STYLES}/{style}?{query}", timeout=TIMEOUT_SECONDS) as response:
        return resolve_urls(json.load(response), token)


def resolve_urls(style: dict, token: str) -> dict:
    """The style with every ``mapbox://`` reference turned into an HTTPS URL carrying the token.

    Plotly gives mapbox-gl the access token only for a style it names itself; a style
    document passes through untouched, so its Mapbox-scheme sources, sprite and glyphs
    would be requested without credentials and refused.
    """
    query = urllib.parse.urlencode({"access_token": token})
    resolved = {**style}
    if style["sprite"].startswith(SCHEME):
        resolved["sprite"] = f"{STYLES}/{_path(style['sprite'], 'sprites')}/sprite?{query}"
    if style["glyphs"].startswith(SCHEME):
        resolved["glyphs"] = f"{API}/fonts/v1/{_path(style['glyphs'], 'fonts')}?{query}"
    resolved["sources"] = {
        name: (
            {**source, "url": f"{API}/v4/{source['url'].removeprefix(SCHEME)}.json?secure&{query}"}
            if source.get("url", "").startswith(SCHEME)
            else source
        )
        for name, source in style["sources"].items()
    }
    return resolved


def _path(url: str, kind: str) -> str:
    return url.removeprefix(f"{SCHEME}{kind}/")
