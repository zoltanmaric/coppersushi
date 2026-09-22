import pandas as pd
import pypsa
import pytest

from coppersushi import REPO, elements, jao_map, power_flow
from coppersushi.data_sources import jao, networks

FIXTURES = REPO / "tests" / "fixtures"
ELEMENT_FIXTURES = FIXTURES / "elements"


@pytest.fixture(scope="module")
def day() -> jao.Day:
    """A synthesised market day of JAO's four tables: no JAO bytes may be redistributed."""
    return jao.read_day(FIXTURES / "jao-map")


@pytest.fixture(scope="module")
def sliced_network() -> pypsa.Network:
    return networks.load(ELEMENT_FIXTURES / "network-slice.nc")


@pytest.fixture(scope="module")
def flat_network() -> pypsa.Network:
    """The same slice with the transformers removed: the network as PyPSA-Eur leaves it today."""
    return networks.load(ELEMENT_FIXTURES / "network-slice-no-transformers.nc")


@pytest.fixture(scope="module")
def substation_matches() -> pd.DataFrame:
    return pd.read_csv(ELEMENT_FIXTURES / "substation-matches.csv")


@pytest.fixture(scope="module")
def matched(day, substation_matches, sliced_network) -> pd.DataFrame:
    return elements.branch_for(day.elements, substation_matches, sliced_network)


@pytest.fixture(scope="module")
def hourly(sliced_network, matched, day) -> pd.DataFrame:
    return jao_map.hourly_elements(sliced_network, matched, day.elements, day.shadow_prices)


@pytest.fixture(scope="module")
def fig(sliced_network, matched, day):
    return jao_map.figure(sliced_network, matched, day.elements, day.shadow_prices, day.external_constraints)


def hour_of(fig, index: int) -> list:
    start = index * jao_map.NUM_TRACES_PER_HOUR
    return list(fig.data[start:start + jao_map.NUM_TRACES_PER_HOUR])


def test_jao_hours_convert_onto_pypsa_snapshots(day, sliced_network):
    """JAO publishes aware UTC, PyPSA naive UTC; a wrong conversion drops every join in silence."""
    snapshots = jao_map.to_snapshot(day.elements.hour)
    assert snapshots.dt.tz is None
    assert set(snapshots) == set(sliced_network.snapshots)


def test_every_matched_element_is_placed_in_every_hour(hourly, matched, sliced_network):
    placed = matched[matched.match_status == "matched"]
    assert not hourly.empty
    assert set(hourly.snapshot) == set(sliced_network.snapshots)
    assert hourly.groupby("snapshot").eic.nunique().eq(len(placed)).all()
    assert not hourly[["x0", "y0", "x1", "y1"]].isna().any().any()


def test_the_tighter_of_the_two_directions_is_the_margin(hourly, day):
    """An element carries a DIRECT and an OPPOSITE limit each hour; the map draws the worse."""
    published = day.elements.assign(margin=day.elements.ram / day.elements.fmax)
    tightest = published.groupby([jao_map.to_snapshot(published.hour), "eic"]).margin.min()
    drawn = hourly.set_index(["snapshot", "eic"]).margin
    assert drawn.round(6).eq(tightest.reindex(drawn.index).round(6)).all()


def test_an_element_that_bound_carries_its_price_and_the_rest_do_not(hourly, day):
    bound = set(zip(jao_map.to_snapshot(day.shadow_prices.hour), day.shadow_prices.eic))
    drawn = set(zip(hourly[hourly.binding].snapshot, hourly[hourly.binding].eic))
    assert drawn == bound & set(zip(hourly.snapshot, hourly.eic))
    assert hourly[~hourly.binding].shadow_price.isna().all()


def test_the_trace_count_per_hour_is_fixed(fig, sliced_network, matched, day):
    """`show_snapshot` finds an hour's traces by a stride, so the stride may not move."""
    assert len(fig.data) == len(sliced_network.snapshots) * jao_map.NUM_TRACES_PER_HOUR
    quiet = day.elements[day.elements.eic == "SYN-LINE-ABSENT"]  # nothing of it reaches the map
    sparse = jao_map.figure(sliced_network, matched, quiet, day.shadow_prices.iloc[:0])
    assert len(sparse.data) == len(fig.data)


def test_one_hour_is_visible_at_a_time_and_the_slider_moves_it(fig):
    assert all(trace.visible for trace in hour_of(fig, 0))
    assert not any(trace.visible for trace in hour_of(fig, 12))
    moved = power_flow.show_snapshot(fig, 12, jao_map.NUM_TRACES_PER_HOUR)
    assert all(trace.visible for trace in hour_of(moved, 12))
    assert not any(trace.visible for trace in hour_of(moved, 0))
    power_flow.show_snapshot(fig, 0, jao_map.NUM_TRACES_PER_HOUR)


def test_binding_elements_are_drawn_in_the_price_palette_and_the_rest_in_the_margin_palette(fig, hourly):
    """Two scales: what an element cost the market, or how close it came to costing anything."""
    drawn = {trace.name: trace for trace in hour_of(fig, 19) if trace.mode == "lines"}
    binding = hourly[(hourly.snapshot == hourly.snapshot.max()) | hourly.binding]
    assert binding.binding.any()  # the fixture's evening peak, or the test proves nothing
    price_labels = [label for _, label, _ in jao_map.PRICE_BINS]
    margin_labels = [label for _, label, _ in jao_map.MARGIN_BINS]
    assert set(price_labels) | set(margin_labels) <= set(drawn)
    assert any(drawn[label].lon is not None and len(drawn[label].lon) for label in price_labels)
    assert all(drawn[label].line.color == colour for _, label, colour in jao_map.PRICE_BINS)


def test_transformers_and_psts_are_point_markers(fig, hourly):
    points = hour_of(fig, 0)[-1]
    drawn = hourly[(hourly.snapshot == hourly.snapshot.min()) & (hourly.branch_type == "Transformer")]
    assert points.mode == "markers" and points.marker.symbol == "square"
    assert len(points.lon) == len(drawn) > 0


def test_a_network_without_transformers_draws_nothing_there_rather_than_crashing(
    day, substation_matches, flat_network
):
    """PyPSA-Eur's simplification leaves no transformers; the map must say so, not fall over."""
    flat_matches = elements.branch_for(day.elements, substation_matches, flat_network)
    flat = jao_map.figure(flat_network, flat_matches, day.elements, day.shadow_prices)
    points = list(flat.data)[jao_map.NUM_TRACES_PER_HOUR - 1]
    assert len(points.lon) == 0
    assert "no_component_in_network" in flat.layout.annotations[0].text


def test_what_is_missing_is_on_the_map(matched, day):
    note = jao_map.missing_note(matched, day.external_constraints)
    assert "no_substation" in note and "no_branch" in note
    assert "external constraints have no location" in note
    assert "of them bound" in note


def test_the_hover_shows_the_element_name_over_its_ends_and_the_branch_id(fig):
    hovers = list(hour_of(fig, 19)[-2].text)
    headings = [hover.split("<br>")[0] for hover in hovers]
    ends = [hover.split("<br>")[1] for hover in hovers]
    identifiers = [hover.split("<br>")[2] for hover in hovers]
    assert all(heading.startswith("<b>") for heading in headings)
    assert all(" \u2192 " in end for end in ends)  # both ends, named where the bus has a name
    assert set(identifiers) <= matched_ids()
    assert any("€/MWh" in hover for hover in hovers)  # the hour's binding element says its price


def matched_ids() -> set[str]:
    """The branches of the fixture slice a line element can resolve to."""
    return {
        "relation/3730417-380", "relation/3730418-380", "relation/395087-380",
        "relation/5134262-400", "relation/5264657-400", "way/1342256406-400",
        "synthetic/hagenwerder-mikulowa-220", "synthetic/etzenricht-vernerov-380",
    }
