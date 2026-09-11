import pandas as pd
import pypsa
import pytest
from pandera.typing import DataFrame

from coppersushi import REPO, elements
from coppersushi.data_model.elements import Overrides
from coppersushi.data_model.jao import Contingencies, Elements
from coppersushi.data_model.substations import Matches
from coppersushi.data_sources import networks

FIXTURES = REPO / "tests" / "fixtures" / "elements"


@pytest.fixture(scope="module")
def day_elements() -> DataFrame[Elements]:
    """A synthesised day of JAO elements: JAO's terms forbid redistributing the real ones.

    Substation names are facts about physical infrastructure, so they are real; the EICs, the
    limits and the margins are invented. `keep_default_na=False` because JAO's untyped rows
    arrive from `cnecs` as an empty `element_type`, not as NaN, and that is a case under test.
    """
    frame = pd.read_csv(FIXTURES / "elements-day.csv", keep_default_na=False, na_values=[""])
    frame = frame.assign(
        hour=pd.to_datetime(frame.hour, utc=True, format="ISO8601"),
        element_type=frame.element_type.fillna(""),
        substation_from=frame.substation_from.fillna(""),
        substation_to=frame.substation_to.fillna(""),
    )
    return frame.pipe(Elements.validate)


@pytest.fixture(scope="module")
def day_contingencies() -> DataFrame[Contingencies]:
    frame = pd.read_csv(FIXTURES / "contingencies-day.csv")
    return frame.assign(hour=pd.to_datetime(frame.hour, utc=True, format="ISO8601")).pipe(Contingencies.validate)


@pytest.fixture(scope="module")
def substation_matches() -> DataFrame[Matches]:
    return pd.read_csv(FIXTURES / "substation-matches.csv").pipe(Matches.validate)


@pytest.fixture(scope="module")
def sliced_network() -> pypsa.Network:
    return networks.load(FIXTURES / "network-slice.nc")


@pytest.fixture(scope="module")
def sliced_network_without_transformers() -> pypsa.Network:
    return networks.load(FIXTURES / "network-slice-no-transformers.nc")


@pytest.fixture(scope="module")
def matched(day_elements, substation_matches, sliced_network) -> pd.DataFrame:
    return elements.branch_for(day_elements, substation_matches, sliced_network)


def overrides(*rows: tuple[str, str, str, str]) -> DataFrame[Overrides]:
    return pd.DataFrame(rows, columns=["eic", "branch_id", "branch_type", "note"]).pipe(Overrides.validate)


def test_one_row_per_eic_not_per_direction_and_hour(matched, day_elements):
    """The triple JAO publishes on keys the measurement; the component is the same all day."""
    assert matched.eic.is_unique
    assert len(matched) == day_elements.eic.nunique() < len(day_elements)


def test_a_tie_line_written_both_ways_round_is_one_element(matched):
    """Keyed on the ordered pair, `Etzenricht → Hradec` and `Hradec → Etzenricht` are two."""
    assert (matched.eic == "SYN-TIE-BOTHWAYS").sum() == 1
    row = matched.set_index("eic").loc["SYN-TIE-BOTHWAYS"]
    assert (row.branch_id, row.match_status) == ("relation/395087-380", "matched")


def test_a_tie_line_and_a_line_resolve_the_same_way(matched):
    """A tie-line is an ordinary line that crosses a border, and takes no special path."""
    by_eic = matched.set_index("eic")
    assert set(by_eic.loc[["SYN-LINE-380-A", "SYN-TIE-BOTHWAYS"], "branch_type"]) == {"Line"}


def test_parallel_branches_are_told_apart_by_the_voltage_in_the_bus_name(matched):
    """Both elements join Hagenwerder to Mikulowa; only their voltage says which branch.

    Every `v_nom` in this network is 380 — an upstream simplification — so a rule reading
    `v_nom` first would pick the same branch for both.
    """
    by_eic = matched.set_index("eic")
    assert by_eic.loc["SYN-LINE-380-A"].branch_id == "relation/3730417-380"
    assert by_eic.loc["SYN-LINE-220-B"].branch_id == "synthetic/hagenwerder-mikulowa-220"


def test_a_transformer_element_is_unmatched_when_the_network_has_none(
    day_elements, substation_matches, sliced_network_without_transformers
):
    """PyPSA-Eur's simplification leaves no transformers; that is a precondition, not a miss."""
    flat = elements.branch_for(day_elements, substation_matches, sliced_network_without_transformers).set_index("eic")
    assert flat.loc["SYN-TRAFO-HAGENWERDER"].match_status == "no_component_in_network"
    assert flat.loc["SYN-PST-ETZENRICHT"].match_status == "no_component_in_network"
    assert flat.loc["SYN-TRAFO-HAGENWERDER"].score == 1.0  # the substation did match; only the class is missing


def test_a_missing_component_class_never_hides_a_substation_that_did_not_match(
    day_elements, substation_matches, sliced_network, sliced_network_without_transformers
):
    """A transformer at an unmatched site is a matching failure, whatever the network holds.

    Claiming `no_component_in_network` there would make every transformer element read as a
    precondition, and a coverage measurement would count genuine misses as a known gap.
    """
    for network in (sliced_network, sliced_network_without_transformers):
        row = elements.branch_for(day_elements, substation_matches, network).set_index("eic")
        assert row.loc["SYN-TRAFO-ABSENT"].match_status == "no_substation"


def test_a_transformer_and_a_pst_resolve_to_a_transformer_at_one_site(matched):
    by_eic = matched.set_index("eic")
    trafo = by_eic.loc["SYN-TRAFO-HAGENWERDER"]
    pst = by_eic.loc["SYN-PST-ETZENRICHT"]
    assert (trafo.branch_type, trafo.branch_id) == ("Transformer", "synthetic/hagenwerder-trafo")
    assert (pst.branch_type, pst.branch_id) == ("Transformer", "synthetic/etzenricht-pst")
    assert {trafo.bus0, trafo.bus1} == {"way/59026005-380", "way/59026005-220"}


def test_an_untyped_element_still_resolves_as_a_line(matched):
    """JAO publishes real monitored circuits with no `elementType`; dropping them lost lines."""
    untyped = matched[matched.eic == "SYN-UNTYPED-LINE"]
    assert untyped.element_type.eq("").all()
    assert untyped.branch_type.eq("Line").all()
    assert untyped.match_status.eq("matched").all()


def test_an_element_whose_substation_is_absent_keeps_its_row(matched):
    row = matched.set_index("eic").loc["SYN-LINE-ABSENT"]
    assert row.match_status == "no_substation"
    assert pd.isna(row.branch_id) and row.bus_source == ""


def test_two_matched_substations_with_nothing_between_them_are_no_branch(matched):
    row = matched.set_index("eic").loc["SYN-LINE-NOBRANCH"]
    assert row.match_status == "no_branch"
    assert row.score == 1.0  # the substations matched; only the branch did not


def test_the_nearest_bus_fallback_is_recorded_not_hidden(matched):
    assert set(matched.bus_source) <= {"exact", "nearest", ""}
    assert matched[matched.match_status == "matched"].bus_source.ne("").all()
    nearest = matched.set_index("eic").loc["SYN-LINE-NEAREST"]
    assert (nearest.bus_source, nearest.branch_id) == ("nearest", "synthetic/etzenricht-vernerov-380")
    assert matched.set_index("eic").loc["SYN-TIE-BOTHWAYS"].bus_source == "exact"


def test_the_nearest_bus_fallback_cannot_take_another_named_substations_corridor(matched):
    """Vernerov is 8.5 km from Hradec, and Hradec is a substation JAO named in its own right.

    Widening into it would put Etzenricht-Vernerov on the Etzenricht-Hradec line that
    `SYN-TIE-BOTHWAYS` already holds, and a later stage would sum two elements' limits there.
    """
    by_eic = matched.set_index("eic")
    assert by_eic.loc["SYN-LINE-NEAREST"].branch_id != by_eic.loc["SYN-TIE-BOTHWAYS"].branch_id
    assert matched[matched.match_status == "matched"].branch_id.is_unique


def test_the_score_is_the_weaker_of_the_two_substation_matches(matched):
    """Vernerov was matched fuzzily at 0.92; the element is only as good as its worse end."""
    assert matched.set_index("eic").loc["SYN-LINE-NEAREST"].score == pytest.approx(0.92)
    assert matched.set_index("eic").loc["SYN-LINE-380-A"].score == 1.0


def test_coverage_is_the_share_of_elements_that_reached_a_branch(matched):
    assert elements.coverage(matched) == pytest.approx((matched.match_status == "matched").mean())
    assert 0 < elements.coverage(matched) < 1
    assert elements.coverage(matched.iloc[:0]) == 0.0


def test_an_override_wins_over_the_computed_match(day_elements, substation_matches, sliced_network):
    forced = overrides(("SYN-LINE-380-A", "relation/3730418-380", "Line", "circuit 1 is the second of the pair"))
    row = elements.branch_for(day_elements, substation_matches, sliced_network, forced).set_index("eic")
    assert row.loc["SYN-LINE-380-A"].branch_id == "relation/3730418-380"
    assert row.loc["SYN-LINE-380-A"].match_status == "matched"


def test_an_override_retypes_the_element_it_corrects(day_elements, substation_matches, sliced_network):
    """A `Line` id filed under `Transformer` would be looked up in the wrong table for ever."""
    forced = overrides(("SYN-LINE-380-A", "synthetic/hagenwerder-trafo", "Transformer", "JAO types it wrong"))
    row = elements.branch_for(day_elements, substation_matches, sliced_network, forced).set_index("eic")
    assert row.loc["SYN-LINE-380-A"].branch_type == "Transformer"
    assert row.loc["SYN-LINE-380-A"].element_type == "Line"  # JAO's own word is kept as it was published


def test_an_override_naming_a_branch_the_network_lacks_is_refused(
    day_elements, substation_matches, sliced_network
):
    forced = overrides(("SYN-LINE-380-A", "relation/nonesuch", "Line", "typo"))
    with pytest.raises(ValueError, match="absent from the network"):
        elements.branch_for(day_elements, substation_matches, sliced_network, forced)


def test_contingency_branches_folding_onto_one_line_are_counted_not_repeated(
    day_contingencies, substation_matches, sliced_network
):
    """Two of a corridor's circuits out is a reactance change, so PR 6 needs the count."""
    outages = elements.contingencies_for(day_contingencies, substation_matches, sliced_network)
    corridor = outages[outages.cont_name == "Hagenwerder - Mikulowa corridor"]
    folded = corridor[corridor.branch_id == "relation/3730417-380"]
    assert len(folded) == 1
    assert folded.circuits_out.iloc[0] == 2  # two circuits named, one branch of ours
    assert folded.branch_name.iloc[0] == "Hagenwerder - Mikulowa 1; Hagenwerder - Mikulowa 2"


def test_contingency_lists_repeated_every_hour_are_made_distinct(day_contingencies, substation_matches, sliced_network):
    outages = elements.contingencies_for(day_contingencies, substation_matches, sliced_network)
    assert not outages.duplicated(subset=["eic", "cont_name", "branch_id", "branch_name"]).any()
    assert len(outages) < len(day_contingencies)


def test_an_outaged_pst_resolves_to_a_transformer(day_contingencies, substation_matches, sliced_network):
    outages = elements.contingencies_for(day_contingencies, substation_matches, sliced_network).set_index("cont_name")
    assert outages.loc["Etzenricht PST out"].branch_id == "synthetic/etzenricht-pst"


def test_an_unmatched_outaged_branch_keeps_its_row(day_contingencies, substation_matches, sliced_network):
    outages = elements.contingencies_for(day_contingencies, substation_matches, sliced_network).set_index("cont_name")
    assert outages.loc["Mostar out"].match_status == "no_substation"
