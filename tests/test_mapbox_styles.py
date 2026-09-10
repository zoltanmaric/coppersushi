import json
from pathlib import Path

from coppersushi.data_sources import mapbox_styles

STYLE = Path(__file__).parent / "fixtures" / "mapbox-style" / "synthetic-dark.json"
TOKEN = "pk.synthetic"


def test_resolve_urls_credentials_every_reference_and_swaps_in_the_marker_sprite():
    resolved = mapbox_styles.resolve_urls(json.loads(STYLE.read_text()), TOKEN)
    assert resolved["sprite"] == (
        "https://api.mapbox.com/styles/v1/mapbox/dark-v9/sprite?access_token=pk.synthetic"
    )
    assert resolved["glyphs"] == (
        "https://api.mapbox.com/fonts/v1/example/{fontstack}/{range}.pbf?access_token=pk.synthetic"
    )
    assert resolved["sources"]["composite"]["url"] == (
        "https://api.mapbox.com/v4/example.synthetic-streets.json?secure&access_token=pk.synthetic"
    )
    assert "mapbox://" not in json.dumps(resolved)


def test_resolve_urls_leaves_the_layers_alone():
    style = json.loads(STYLE.read_text())
    assert mapbox_styles.resolve_urls(style, TOKEN)["layers"] == style["layers"]
