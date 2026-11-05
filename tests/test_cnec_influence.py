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
    """Five zone centres and one row's contribution relative to AT."""
    centres, contribution = (
        pd.read_csv(FIXTURES / f"{name}.csv") for name in ("centres", "contribution")
    )
    return centres, contribution


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


def test_only_influenced_zones_get_rays_and_no_endpoint_nodes():
    overlay = cnec_influence.overlay(*frames())
    assert [t.name for t in overlay.traces if t.name.endswith(" ray")] == ["BE ray", "SI ray", "DE ray"]
    assert not any(t.mode == "markers" for t in overlay.traces)


def test_rays_leave_reference_and_land_on_the_zone_along_an_arc():
    belgium = trace(cnec_influence.overlay(*frames()), "BE ray")
    assert (belgium.lon[0], belgium.lat[0]) == (14.0, 47.2)
    assert (belgium.lon[-1], belgium.lat[-1]) == pytest.approx(BRUSSELS)
    assert len(belgium.lon) > 2


def test_positive_contributions_are_purple_and_negative_contributions_are_teal():
    overlay = cnec_influence.overlay(*frames())
    assert trace(overlay, "BE ray").line.color == map_style.BINDING
    assert trace(overlay, "DE ray").line.color == map_style.PRICE_DOWN


def test_rays_are_translucent_without_a_glow():
    overlay = cnec_influence.overlay(*frames())
    core = trace(overlay, "SI ray")
    assert core.opacity == pytest.approx(.48)
    assert not any(t.name.endswith("ray glow") for t in overlay.traces)


def test_missing_reference_centre_has_no_rays():
    centres, contribution = frames()
    overlay = cnec_influence.overlay(centres[centres.zone.ne("AT")], contribution)
    assert not overlay.traces
    assert "no mapped centre" in overlay.note


def test_visible_ray_labels_show_each_signed_contribution():
    overlay = cnec_influence.overlay(*frames())
    labels = trace(overlay, "ray contributions")
    assert labels.mode == "text"
    for zone, value in [('BE', '+€2.87'), ('SI', '+€12.65'), ('DE', '−€5.00')]:
        ray = trace(overlay, f'{zone} ray')
        assert any(label == value and f'Spread: {zone} −' in hover
                   for label, hover in zip(labels.text, labels.hovertext))
        assert 'contribution:' in ray.hovertext
    assert '€/MWh' in overlay.note
