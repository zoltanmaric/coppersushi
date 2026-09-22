import logging

import pandas as pd
import pytest
from pandera.typing import DataFrame

from coppersushi import REPO, substations
from coppersushi.data_model.substations import BusNames, Overrides

FIXTURES = REPO / "tests" / "fixtures" / "substations"


@pytest.fixture
def buses() -> DataFrame[BusNames]:
    """The name side of a bus table, as the network hands it over.

    OSM names are ODbL and are quoted verbatim; JAO substation names are facts about
    physical infrastructure rather than JAO's dataset, so they appear here too. None of
    JAO's measurements do.

    `keep_default_na=False` because an unnamed OSM substation arrives as an empty string,
    not as NaN, and the empty name is one of the cases under test.
    """
    frame = pd.read_csv(FIXTURES / "bus-names-sample.csv", keep_default_na=False)
    return frame.pipe(BusNames.validate)


def overrides(*rows: tuple[str, str, str]) -> DataFrame[Overrides]:
    return pd.DataFrame(rows, columns=["jao_name", "bus_id", "note"]).pipe(Overrides.validate)


def matched(buses, *jao_names, **kwargs) -> pd.DataFrame:
    return substations.match(pd.Series(jao_names), buses, **kwargs).set_index("jao_name")


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Umspannwerk Mühlbach", "muhlbach"),  # Prefix and diacritic
        ("MUHLBACH", "muhlbach"),  # JAO's side of the same name
        ("Mikułowa", "mikulowa"),  # ł has no NFKD decomposition; folding alone loses it
        ('Stacja elektroenergetyczna "Krosno Iskrzynia" 400/110 kV', "krosno iskrzynia"),
        ("Stacja elektroenergetyczna 400/110kV „SE Rzeszów Systemowa”", "rzeszow systemowa"),
        ("APG Umspannwerk Westtirol", "westtirol"),  # Operator prefix on top of a facility prefix
        ("RTP Cirkovce", "cirkovce"),
        ("Mikulowa AT1", "mikulowa"),  # AT1 names the transformer, not the site
        ("Westtirol 1", "westtirol"),
        ("", ""),
        ("Umspannwerk", "umspannwerk"),  # A name that is nothing but a prefix keeps it
    ],
)
def test_normalise_reduces_both_conventions_to_one_form(name, expected):
    assert substations.normalise(name) == expected


def test_an_identical_name_matches_exactly(buses):
    row = matched(buses, "HORTA").loc["HORTA"]
    assert (row.bus_id, row.osm_id, row.country, row.source, row.score) == (
        "relation/10047998-380",
        "relation/10047998",
        "BE",
        "exact",
        1.0,
    )


@pytest.mark.parametrize(
    ("jao_name", "bus_id"),
    [
        ("MUHLBACH", "way/4444444-380"),  # Accents and case only
        ("AVELGEM", "relation/10047997-380"),  # OSM wraps the name in quotes
        ("Bisamberg", "way/3333333-220"),  # OSM carries a facility prefix
        ("Cirkovce", "way/8888888-220"),  # ... and an operator-style one
        ("Krosno Iskrzynia", "relation/6666666-400"),  # Quoted inner name inside a description
        ("Rzeszow Systemowa", "relation/6666667-400"),  # Typographic quotes, voltages, diacritic
        ("Mikulowa AT1", "relation/6666668-400"),  # Element suffix
        ("H.Zdana", "way/7777777-400"),  # JAO abbreviates the leading word to an initial
        ("P.Bystrica", "way/7777778-400"),
    ],
)
def test_normalisation_closes_each_measured_gap_exactly(buses, jao_name, bus_id):
    """Every one of these is an *exact* hit once normalised — none leans on the fuzzy step."""
    row = matched(buses, jao_name).loc[jao_name]
    assert (row.bus_id, row.source) == (bus_id, "exact")


def test_a_transliteration_difference_matches_fuzzily(buses):
    """JAO writes `Duernrohr` where OSM writes `Dürnrohr`, and ue is not a fold of ü."""
    row = matched(buses, "Duernrohr 1").loc["Duernrohr 1"]
    assert (row.bus_id, row.source) == ("node/5555555-380", "fuzzy")
    assert row.score == pytest.approx(0.94, abs=0.01)


def test_a_confusable_neighbour_is_not_matched(buses):
    """Dürnkrut sits 0.63 from Dürnrohr — near, and well under the cut."""
    assert matched(buses, "Duernrohr 1").loc["Duernrohr 1"].bus_id != "node/5555556-380"


def test_a_threshold_above_the_score_refuses_the_fuzzy_match(buses):
    row = matched(buses, "Duernrohr 1", threshold=0.95).loc["Duernrohr 1"]
    assert row.source == "unmatched"


def test_an_unmatchable_name_is_unmatched_not_wrong(buses):
    """MOSTAR is outside Core; its nearest key is 0.55 away, which must not be taken."""
    row = matched(buses, "MOSTAR").loc["MOSTAR"]
    assert row.source == "unmatched"
    assert row.score == 0.0
    assert pd.isna(row.bus_id) and pd.isna(row.osm_id) and pd.isna(row.country)


def test_a_bus_without_an_osm_name_is_never_matched(buses):
    """An empty OSM name normalises to nothing, which must not become a wildcard."""
    assert "way/9999999-380" not in set(substations.match(pd.Series([""]), buses).bus_id.dropna())
    assert matched(buses, "").loc[""].source == "unmatched"


def test_a_site_at_two_voltages_resolves_to_the_highest(buses, caplog):
    """Westtirol is one site on two buses; the pick is the 380 kV one, and it is logged."""
    with caplog.at_level(logging.INFO, logger="coppersushi.substations"):
        row = matched(buses, "Westtirol 1").loc["Westtirol 1"]
    assert row.bus_id == "way/2222222-380"
    assert "way/2222222-220" in caplog.text


def test_two_elements_at_one_site_stay_distinct_rows(buses):
    """`Westtirol 1` and `Westtirol 2` are two JAO elements: same bus, two rows, digits kept."""
    rows = matched(buses, "Westtirol 1", "Westtirol 2")
    assert list(rows.index) == ["Westtirol 1", "Westtirol 2"]
    assert set(rows.bus_id) == {"way/2222222-380"}


def test_a_repeated_jao_name_yields_one_row(buses):
    assert len(substations.match(pd.Series(["HORTA", "HORTA"]), buses)) == 1


def test_an_override_wins_over_the_computed_match(buses):
    row = matched(
        buses,
        "HORTA",
        overrides=overrides(("HORTA", "relation/10047997-380", "JAO's Horta is Avelgem's other bay")),
    ).loc["HORTA"]
    assert (row.bus_id, row.source, row.score) == ("relation/10047997-380", "override", 1.0)


def test_an_override_rescues_an_otherwise_unmatched_name(buses):
    row = matched(
        buses, "MOSTAR", overrides=overrides(("MOSTAR", "way/8888888-220", "hand-checked"))
    ).loc["MOSTAR"]
    assert (row.bus_id, row.osm_id, row.source) == ("way/8888888-220", "way/8888888", "override")


def test_coverage_is_the_share_of_names_that_reached_a_bus(buses):
    assert substations.coverage(substations.match(pd.Series(["HORTA", "MOSTAR"]), buses)) == 0.5
    assert substations.coverage(substations.match(pd.Series(["HORTA"]), buses)) == 1.0
    assert substations.coverage(substations.match(pd.Series([], dtype=str), buses)) == 0.0
