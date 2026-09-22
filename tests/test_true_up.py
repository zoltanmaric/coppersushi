import pandas as pd
import pypsa
import pytest
from pandera.typing import DataFrame

from coppersushi import REPO, true_up
from coppersushi.data_model.elements import ElementMatches
from coppersushi.data_model.jao import Elements
from coppersushi.data_sources import networks

FIXTURES = REPO / "tests" / "fixtures" / "true-up"
NETWORK = REPO / "tests" / "fixtures" / "elements" / "network-slice.nc"

HOURS = 3
HAGENWERDER_MIKULOWA = "relation/3730417-380"
ETZENRICHT_HRADEC = "relation/395087-380"
HAGENWERDER_220 = "synthetic/hagenwerder-mikulowa-220"
HAGENWERDER_TRAFO = "synthetic/hagenwerder-trafo"


@pytest.fixture(scope="module")
def day_elements() -> DataFrame[Elements]:
    """A synthesised day of JAO elements: JAO's terms forbid redistributing the real ones."""
    frame = pd.read_csv(FIXTURES / "elements-day.csv")
    return frame.assign(hour=pd.to_datetime(frame.hour, utc=True, format="ISO8601")).pipe(Elements.validate)


@pytest.fixture(scope="module")
def element_matches() -> DataFrame[ElementMatches]:
    frame = pd.read_csv(FIXTURES / "element-matches.csv", keep_default_na=False, na_values=[""])
    return frame.assign(bus_source=frame.bus_source.fillna("")).pipe(ElementMatches.validate)


@pytest.fixture(scope="module")
def sliced_network() -> pypsa.Network:
    return networks.load(NETWORK)


@pytest.fixture(scope="module")
def day_limits(day_elements) -> pd.DataFrame:
    return true_up.limits(day_elements)


@pytest.fixture(scope="module")
def day_ratings(day_limits, element_matches) -> pd.DataFrame:
    return true_up.ratings(day_limits, element_matches)


def branch(ratings: pd.DataFrame, branch_id: str) -> pd.DataFrame:
    return ratings[ratings.branch_id == branch_id].sort_values("hour")


def test_fmax_is_keyed_on_eic_direction_and_hour(day_limits):
    assert not day_limits.duplicated(["eic", "direction", "hour"]).any()


def test_a_fixed_limit_that_moves_is_still_treated_as_hourly(day_limits):
    mover = day_limits[day_limits.eic == "SYN-TU-FIXED-MOVER"]
    assert (mover.fmax_type == "FIXED").all()
    assert mover.is_hourly.all()
    assert mover.fmax.nunique() == HOURS


def test_a_dynamic_limit_that_never_moves_is_not_hourly(day_limits):
    constant = day_limits[day_limits.eic == "SYN-TU-CONSTANT"]
    assert (constant.fmax_type == "DYNAMIC").all()
    assert not constant.is_hourly.any()


def test_every_constant_limit_carries_one_fmax(day_limits):
    constant = day_limits[~day_limits.is_hourly]
    assert not constant.empty
    assert constant.groupby(["eic", "direction"]).fmax.nunique().eq(1).all()


def test_duplicate_rows_collapse_to_one_limit(day_elements):
    doubled = pd.concat([day_elements, day_elements], ignore_index=True).pipe(Elements.validate)
    assert true_up.limits(doubled).equals(true_up.limits(day_elements))


def test_elements_folding_onto_one_branch_have_their_limits_summed(day_ratings):
    folded = branch(day_ratings, HAGENWERDER_MIKULOWA)
    assert len(folded) == HOURS
    assert (folded.elements == 2).all()
    assert (folded.s_nom == 1100.0 + 700.0).all()


def test_the_tighter_direction_sets_the_rating(day_ratings):
    trafo = branch(day_ratings, HAGENWERDER_TRAFO)
    assert (trafo.s_nom == 1500.0).all()  # 1600 MW DIRECT, 1500 MW OPPOSITE


def test_an_hourly_limit_becomes_a_derating_of_the_largest_hour(day_ratings):
    mover = branch(day_ratings, ETZENRICHT_HRADEC)
    assert mover.is_hourly.all()
    assert (mover.s_nom == 2002.0).all()
    assert (mover.s_max_pu * mover.s_nom).round(6).tolist() == [1792.0, 1897.0, 2002.0]
    assert mover.s_max_pu.max() == 1.0


def test_a_constant_limit_is_a_flat_scalar_rating(day_ratings):
    constant = branch(day_ratings, HAGENWERDER_220)
    assert not constant.is_hourly.any()
    assert (constant.s_nom == 400.0).all()
    assert (constant.s_max_pu == 1.0).all()


def test_an_unmatched_element_writes_no_rating(day_ratings, day_limits):
    assert "SYN-TU-UNMATCHED" in set(day_limits.eic)
    assert len(day_ratings) == 4 * HOURS  # four branches, not five elements


def test_the_reliability_margin_is_not_written(day_limits, day_ratings):
    assert "frm" not in day_limits
    assert "frm" not in day_ratings


def test_ratings_are_empty_when_nothing_matched(day_limits, element_matches):
    unmatched = element_matches.assign(match_status="no_branch").pipe(ElementMatches.validate)
    assert true_up.ratings(day_limits, unmatched).empty


def test_the_comparison_reads_the_voltage_off_the_bus_names(day_ratings, sliced_network):
    compared = true_up.comparison(day_ratings, sliced_network).set_index("branch_id")
    # Every `v_nom` in the slice is 380; only the bus-name suffix knows the 220 kV line.
    assert compared.v_nom[HAGENWERDER_220] == 220.0
    assert compared.v_nom[HAGENWERDER_MIKULOWA] == 380.0


def test_a_transformer_rated_far_above_ours_is_flagged(day_ratings, sliced_network):
    compared = true_up.comparison(day_ratings, sliced_network).set_index("branch_id")
    assert compared.ratio[HAGENWERDER_TRAFO] == pytest.approx(1500.0 / 600.0)
    assert compared.ratio[HAGENWERDER_TRAFO] > true_up.RATIO_FLAG
    assert compared.flagged[HAGENWERDER_TRAFO]
    assert not compared.flagged[HAGENWERDER_MIKULOWA]


def test_the_report_separates_lines_from_transformers_by_voltage(day_ratings, sliced_network):
    summary = true_up.report(true_up.comparison(day_ratings, sliced_network))
    assert list(zip(summary.branch_type, summary.v_nom)) == [("Line", 220.0), ("Line", 380.0), ("Transformer", 380.0)]
    assert summary.branches.tolist() == [1, 2, 1]
    assert summary.flagged.tolist() == [0, 0, 1]


def test_the_report_of_nothing_is_empty(day_ratings, sliced_network):
    assert true_up.report(true_up.comparison(day_ratings.iloc[0:0], sliced_network)).empty
