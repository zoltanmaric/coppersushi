"""JAO's tables may not be redistributed, so these run on a synthesised look-alike.

`domain-elements.csv` is invented — its substation and element names are made up — but every
quirk it carries is one the real feed has: umlauts spelled both ways, diacritics and
punctuation, a `Y ` tap prefix, a trailing equipment token, one name meaning two places
hundreds of kilometres apart, a tie-line published from both ends in two spellings, and a row
naming no substations and no element type. `located-substations.csv` is the locator's row
shape, with one site recorded twice as the duplicated national templates record it.
"""

import pandas as pd
import pytest

from coppersushi import REPO, cnec_geometry
from coppersushi.data_model.cnec_price_map import MappedCnecElements
from coppersushi.data_model.jao import ElementEnds, Elements
from coppersushi.data_model.osm_locator import LocatedSubstations
from coppersushi.data_sources import jao

FIXTURES = REPO / "tests" / "fixtures" / "cnec-geometry"

ALIASES = {"Suedhafen": "Nordkamp"}
NORDKAMP = (13.5, 48.5)
TIE_LINE = "99T-AA-BB-00012P"


@pytest.fixture
def elements():
    """The fixture elements as `read_day` returns a cached day: zone restored, blanks back."""
    frame = pd.read_csv(FIXTURES / "domain-elements.csv")
    frame = frame.assign(hour=pd.to_datetime(frame.hour, utc=True))
    return jao._restore_blanks(frame, Elements).pipe(Elements.validate)


@pytest.fixture
def ends(elements):
    """Each TSO's own ends, as `cnecs.element_ends` keeps them from the raw feed."""
    return (
        elements[["eic", "tso", "element_type", "substation_from", "substation_to"]]
        .drop_duplicates(ignore_index=True)
        .pipe(ElementEnds.validate)
    )


@pytest.fixture
def substations():
    return pd.read_csv(FIXTURES / "located-substations.csv").pipe(LocatedSubstations.validate)


@pytest.fixture
def placements(ends, substations):
    """Every element placed, with the alias list the real run passes."""
    located = cnec_geometry.locate_elements(ends, substations, ALIASES)
    return located.set_index("eic")


def span(row):
    """The two ends a row is drawn between, as a set: which end is which is the TSO's."""
    return {(row.x0, row.y0), (row.x1, row.y1)}


def test_a_located_name_answers_to_both_the_transliterated_and_the_dropped_spelling(
    substations, placements
):
    index = cnec_geometry.substation_index(substations)
    assert cnec_geometry.keys("Röhrsbach") == ["rohrsbach", "roehrsbach"]
    assert {"rohrsbach", "roehrsbach"} <= set(index)
    # Röhrsbach is located with its umlaut and published transliterated; Zaehringen is
    # located transliterated and published with the umlaut. Both directions must hit.
    row = placements.loc["99T-AA-BB-00001P"]
    assert span(row) == {(13.0, 48.0), (13.1, 48.1)}


def test_diacritics_and_punctuation_collapse(placements):
    dotted = placements.loc["99T-AA-BB-00002P"]  # Vraclavek - V Dur, located as V.Dur
    assert span(dotted) == {(14.0, 49.0), (14.1, 49.1)}
    underscored = placements.loc["99T-AA-BB-00003P"]  # Ober_Feld - Vraclávek
    assert span(underscored) == {(14.0, 49.0), (14.2, 49.2)}


def test_the_alias_table_resolves_a_name_the_locator_files_differently(ends, substations):
    without = cnec_geometry.locate_elements(ends, substations).set_index("eic")
    assert without.loc["99T-AA-BB-00004P"].match_status == "no_substation"
    with_aliases = cnec_geometry.locate_elements(ends, substations, ALIASES).set_index("eic")
    aliased = with_aliases.loc["99T-AA-BB-00004P"]  # Suedhafen - Aufeld
    assert span(aliased) == {NORDKAMP, (15.0, 47.0)}
    assert aliased.score == 1.0


def test_a_tap_prefix_places_on_the_site_it_taps_with_a_lower_score(placements):
    row = placements.loc["99T-AA-BB-00005P"]  # Y Mellau - Nordkamp
    assert span(row) == {(12.9, 47.9), NORDKAMP}
    assert row.score == pytest.approx(cnec_geometry.TAP)
    assert row.score < cnec_geometry.EXACT


def test_a_trailing_equipment_token_is_trimmed_with_a_lower_score(placements):
    row = placements.loc["99T-AA-BB-00006P"]  # Grunbach PST1 - Nordkamp
    assert span(row) == {(12.8, 47.8), NORDKAMP}
    assert row.score == pytest.approx(cnec_geometry.TRIMMED)
    assert row.score < cnec_geometry.TAP


def test_one_site_recorded_twice_collapses_to_a_single_place(substations, placements):
    assert cnec_geometry.substation_index(substations)["doppelsee"] == [(10.0, 50.0)]
    row = placements.loc["99T-AA-BB-00007P"]  # Doppelsee - Nordkamp
    assert span(row) == {(10.0, 50.0), NORDKAMP}


def test_an_ambiguous_name_places_on_the_combination_with_the_shortest_span(placements):
    """`Sankt Ulrich` is two substations 480 km apart, as `St. Peter` really is.

    Both elements name it; the far endpoint of each is what decides which one is meant, so
    picking the first or the wrong candidate fails one of the two.
    """
    eastern = placements.loc["99T-AA-BB-00008P"]  # Sankt Ulrich - Ostanker (13.2, 48.4)
    assert span(eastern) == {(13.08, 48.26), (13.2, 48.4)}
    western = placements.loc["99T-AA-BB-00009P"]  # Westanker (6.5, 51.0) - Sankt Ulrich
    assert span(western) == {(6.5, 51.0), (6.8, 51.12)}


def test_a_point_element_is_placed_at_its_single_site(placements):
    row = placements.loc["99T-AA-BB-00010P"]  # Transformer Trafofeld - Trafofeld
    assert (row.x0, row.y0) == (row.x1, row.y1) == (11.0, 46.0)
    assert row.branch_type == "Transformer"


def test_an_ambiguous_point_element_has_no_span_to_choose_by_and_stays_unplaced(placements):
    row = placements.loc["99T-AA-BB-00011P"]  # PST at the ambiguous Sankt Ulrich
    assert row.match_status == "no_substation"
    assert pd.isna(row.x0)


def test_each_publisher_is_drawn_from_its_own_end_over_one_line(placements):
    """One EIC, published `Aufeld - Bachheim` by one TSO and `Baechheim - Aufeld` by the other.

    The locator holds `Bächheim`, so the two publishers hit it under different keys; the
    line's identity comes from the places found, not from the spellings that found them.
    """
    rows = placements.loc[[TIE_LINE]].set_index("tso")
    assert len(rows) == 2
    assert (rows.loc["ZATSO", "x0"], rows.loc["ZATSO", "y0"]) == (15.0, 47.0)  # Aufeld
    assert (rows.loc["ZBTSO", "x0"], rows.loc["ZBTSO", "y0"]) == (15.5, 47.5)  # Bächheim
    assert span(rows.loc["ZATSO"]) == span(rows.loc["ZBTSO"])
    assert rows.branch_id.nunique() == 1


@pytest.mark.parametrize(
    "eic,reason",
    [
        ("99T-AA-BB-00013P", "an endpoint the locator does not hold"),
        ("99T-AA-BB-00014P", "a row publishing no substations and no element type"),
    ],
)
def test_an_unplaceable_endpoint_keeps_its_row_without_coordinates(placements, eic, reason):
    row = placements.loc[eic]
    assert row.match_status == "no_substation", reason
    assert all(pd.isna(value) for value in (row.x0, row.y0, row.x1, row.y1))
    assert row.score == 0.0
    assert pd.isna(row.branch_id)


def test_the_placed_table_validates_and_carries_one_row_per_publisher_and_eic(
    ends, substations
):
    located = cnec_geometry.locate_elements(ends, substations, ALIASES)
    MappedCnecElements.validate(located)
    assert set(zip(located.eic, located.tso)) == set(zip(ends.eic, ends.tso))
    assert not located.duplicated(["eic", "tso"]).any()
