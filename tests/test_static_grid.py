import pandas as pd
import pytest

from coppersushi import REPO, static_grid

FIXTURES = REPO / "tests" / "fixtures" / "static-grid"


def sheet(name: str) -> pd.DataFrame:
    """A trimmed real sheet, as `pd.read_excel(..., header=1)` hands it over."""
    return pd.read_csv(FIXTURES / name)


def test_s_nom_matches_jaos_published_fmax_for_the_days_binding_transformer():
    tr = static_grid.transformers(sheet("transformers-sample.csv"))
    rosiori = tr[tr.eic == "30T-ROSI400AT--1"]
    assert not rosiori.empty
    assert rosiori.s_nom.iloc[0] == pytest.approx(400.0, abs=1.0)  # JAO's feed publishes fmax 400


def test_a_phase_shifter_is_flagged_by_its_angle():
    tr = static_grid.transformers(sheet("transformers-sample.csv"))
    assert tr[tr.eic == "19T0000000063830"].is_pst.all()  # PST MIKULOWA-PF1
    assert not tr[tr.eic == "30T-ROSI400AT--1"].is_pst.any()


def test_a_row_with_only_a_fixed_rating_still_gets_one():
    tr = static_grid.transformers(sheet("transformers-sample.csv"))
    assert tr.imax.notna().all()
    assert tr.s_nom.gt(0).all()


def test_a_row_with_no_rating_at_all_is_refused():
    rows = sheet("transformers-sample.csv").assign(Min=None, Max=None, Fixed=None)
    with pytest.raises(ValueError, match="no current rating"):
        static_grid.transformers(rows)


def test_impedance_survives_for_every_row():
    tr = static_grid.transformers(sheet("transformers-sample.csv"))
    assert tr.x.notna().all()
    assert tr.x.gt(0).all()


def test_two_transformers_sharing_an_eic_are_both_kept():
    """RTE publishes one EIC for two Cergy transformers whose R and X differ."""
    tr = static_grid.transformers(sheet("transformers-sample.csv"))
    cergy = tr[tr.eic == "17T000000014198T"]
    assert len(cergy) == 2
    assert cergy.x.nunique() == 2


def test_the_static_model_joins_to_the_publication_feed_on_eic():
    tr = static_grid.transformers(sheet("transformers-sample.csv"))
    elements = pd.read_csv(REPO / "data" / "jao" / "2024-08-29" / "elements.csv")
    monitored = set(elements[elements.element_type.isin(("Transformer", "PST"))].eic)
    assert monitored & set(tr.eic)


def test_branches_carry_both_sheets_and_their_substation_names():
    branches = static_grid.branches(sheet("lines-sample.csv"), sheet("tielines-sample.csv"))
    assert branches.is_tieline.any() and not branches.is_tieline.all()
    assert branches.substation_from.ne("").all()
    assert branches.eic.isna().any()  # some line rows carry no EIC


def test_the_seasonal_rating_is_the_highest_of_the_six_periods():
    branches = static_grid.branches(sheet("lines-sample.csv"), sheet("tielines-sample.csv"))
    seasonal = branches[branches.imax_seasonal.notna()]
    assert not seasonal.empty
    assert branches.imax_fixed.notna().any()
    assert seasonal.imax_seasonal.gt(0).all()


def test_s_nom_is_three_phase_apparent_power_in_mva():
    assert static_grid.s_nom(pd.Series([400.0]), pd.Series([577.0])).iloc[0] == pytest.approx(399.76, abs=0.01)
