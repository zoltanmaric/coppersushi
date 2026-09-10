import copy
import json
from pathlib import Path

from coppersushi import map_style

STYLE = Path(__file__).parent / "fixtures" / "mapbox-style" / "synthetic-dark.json"


def test_without_labels_drops_every_symbol_layer_and_nothing_else():
    style = json.loads(STYLE.read_text())
    unlabelled = map_style.without_labels(style)
    assert [layer["id"] for layer in unlabelled["layers"]] == ["land", "water", "admin-boundaries"]
    assert {key: unlabelled[key] for key in unlabelled if key != "layers"} == {
        key: style[key] for key in style if key != "layers"
    }


def test_without_labels_leaves_the_fetched_document_intact():
    style = json.loads(STYLE.read_text())
    before = copy.deepcopy(style)
    map_style.without_labels(style)
    assert style == before
