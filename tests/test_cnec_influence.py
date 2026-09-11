import math

import numpy as np
import pandas as pd
import pytest

from coppersushi import REPO, cnec_influence, map_style

FIXTURES = REPO / "tests" / "fixtures" / "cnec-influence"

ELEMENT = (14.75, 46.45)  # Midpoint of the fixture element
BRUSSELS = (4.5, 50.8)


def trace(overlay, name):
    return next(item for item in overlay.traces if item.name == name)


def frames():
    """The fixture element, five zone centres, and one row's contribution relative to AT."""
    placed, centres, contribution = (
        pd.read_csv(FIXTURES / f"{name}.csv") for name in ("placed", "centres", "contribution")
    )
    return placed.iloc[0], centres, contribution


def test_arc_starts_and_ends_where_asked():
    lon, lat = cnec_influence.arc(ELEMENT, BRUSSELS)
    assert (lon[0], lat[0]) == ELEMENT
    assert (lon[-1], lat[-1]) == pytest.approx(BRUSSELS)
    assert len(lon) == len(lat) == cnec_influence.ARC_POINTS


def test_arc_rises_north_of_its_chord():
    lon, lat = cnec_influence.arc(ELEMENT, BRUSSELS)
    chord = np.interp(lon, [BRUSSELS[0], ELEMENT[0]], [BRUSSELS[1], ELEMENT[1]])
    assert (lat[1:-1] > chord[1:-1]).all()
    assert (np.diff(lon) < 0).all()  # Westward all the way: no loop, no overshoot


def test_arc_due_north_stays_straight():
    lon, lat = cnec_influence.arc((10.0, 46.0), (10.0, 52.0))
    assert lon == pytest.approx(np.full_like(lon, 10.0))
    assert (np.diff(lat) > 0).all()


def test_arc_bows_by_its_length_on_the_ground():
    lon, lat = cnec_influence.arc((20.0, 46.0), (10.0, 46.0), points=25)
    ground_length = 10 * math.cos(math.radians(46.0))
    assert lat[12] - 46.0 == pytest.approx(0.5 * cnec_influence.BOW * ground_length)


def test_every_influenced_zone_gets_a_ray_and_the_others_a_neutral_dot():
    overlay = cnec_influence.overlay(*frames())
    rays = [item.name for item in overlay.traces if item.name.endswith(" ray")]
    assert rays == ["BE ray", "SI ray", "DE ray"]  # Neither the reference nor untouched CZ
    dots = trace(overlay, "contribution relative to AT")
    by_zone = dict(zip(dots.text, dots.marker.color))
    assert by_zone["AT · reference zone"] == cnec_influence.NEUTRAL
    assert by_zone["CZ · +0.00 €/MWh relative to AT"] == cnec_influence.NEUTRAL


def test_rays_leave_the_element_and_land_on_the_zone_along_an_arc():
    belgium = trace(cnec_influence.overlay(*frames()), "BE ray")
    assert (belgium.lon[0], belgium.lat[0]) == ELEMENT
    assert (belgium.lon[-1], belgium.lat[-1]) == pytest.approx(BRUSSELS)
    assert len(belgium.lon) > 2


def test_pink_raises_a_price_and_cyan_lowers_it():
    overlay = cnec_influence.overlay(*frames())
    assert trace(overlay, "BE ray").line.color == map_style.PRICE_UP
    assert trace(overlay, "DE ray").line.color == map_style.PRICE_DOWN
    dots = trace(overlay, "contribution relative to AT")
    by_text = dict(zip(dots.text, dots.marker.color))
    assert by_text["BE · +2.87 €/MWh relative to AT"] == map_style.PRICE_UP
    assert by_text["SI · +12.65 €/MWh relative to AT"] == map_style.PRICE_UP
    assert by_text["DE · -5.00 €/MWh relative to AT"] == map_style.PRICE_DOWN


def test_width_and_dot_size_follow_the_size_of_the_contribution():
    overlay = cnec_influence.overlay(*frames())
    widths = {zone: trace(overlay, f"{zone} ray").line.width for zone in ("BE", "SI", "DE")}
    assert widths["SI"] > widths["DE"] > widths["BE"]
    assert widths["SI"] == cnec_influence.RAY_WIDTH[1]
    dots = trace(overlay, "contribution relative to AT")
    sizes = dict(zip(dots.text, dots.marker.size))
    assert sizes["SI · +12.65 €/MWh relative to AT"] == cnec_influence.DOT_SIZE[1]
    assert sizes["AT · reference zone"] == cnec_influence.DOT_SIZE[0]


def test_each_ray_and_dot_glows_under_its_core():
    overlay = cnec_influence.overlay(*frames())
    glow, core = trace(overlay, "SI ray glow"), trace(overlay, "SI ray")
    assert list(glow.lon) == list(core.lon)
    assert glow.line.width > core.line.width
    assert glow.opacity < (core.opacity or 1.0)
    names = [item.name for item in overlay.traces]
    assert names.index("DE ray glow") < names.index("BE ray")  # No halo over another's core
    assert names.index("contribution relative to AT glow") < names.index("contribution relative to AT")


def test_the_rays_start_from_a_bright_origin_on_the_element():
    origin = trace(cnec_influence.overlay(*frames()), "ray origin")
    assert (origin.lon[0], origin.lat[0]) == ELEMENT
    assert origin.marker.color == "white"


def test_an_unmapped_row_keeps_its_dots_but_anchors_no_rays_and_says_so():
    selected, centres, contribution = frames()
    unmapped = selected.copy()
    unmapped[["x0", "y0", "x1", "y1"]] = None
    unmapped["match_status"] = "no_branch"
    overlay = cnec_influence.overlay(unmapped, centres, contribution)
    assert not any(item.name.endswith(" ray") for item in overlay.traces)
    assert trace(overlay, "contribution relative to AT") is not None
    assert "rays cannot be anchored" in overlay.note
