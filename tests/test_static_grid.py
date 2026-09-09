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
    assert tr[tr.x_physical].x.gt(0).all()


def test_a_negative_reactance_is_flagged_rather_than_dropped_or_repaired():
    """RTE publishes x = -11.7 for TR 400/225kV 761 PONTEAU; PR 6 divides by it."""
    tr = static_grid.transformers(sheet("transformers-sample.csv"))
    ponteau = tr[tr.eic == "17T0000000154066"]
    assert ponteau.x.iloc[0] == -11.7
    assert not ponteau.x_physical.iloc[0]
    assert tr.x_physical.sum() == len(tr) - 1


def test_a_zero_reactance_branch_is_flagged_too():
    """A branch of exactly zero reactance is a short circuit, not a small impedance."""
    branches = static_grid.branches(sheet("lines-sample.csv"), sheet("tielines-sample.csv"))
    beverwijk = branches[branches.eic == "49T0000000000509"]
    assert beverwijk.x.iloc[0] == 0.0
    assert not beverwijk.x_physical.iloc[0]
    assert branches[branches.x_physical].x.gt(0).all()


def test_two_transformers_sharing_an_eic_are_both_kept():
    """RTE publishes one EIC for two Cergy transformers whose R and X differ."""
    tr = static_grid.transformers(sheet("transformers-sample.csv"))
    cergy = tr[tr.eic == "17T000000014198T"]
    assert len(cergy) == 2
    assert cergy.x.nunique() == 2
    assert set(static_grid.eic_collisions(tr).eic) == {"17T000000014198T"}


def test_joining_on_a_colliding_eic_raises_instead_of_multiplying_rows():
    """`merge(on="eic")` would silently return two rows for Cergy; this must not."""
    tr = static_grid.transformers(sheet("transformers-sample.csv"))
    elements = pd.DataFrame({"eic": ["30T-ROSI400AT--1", "17T000000014198T"]})
    with pytest.raises(ValueError, match="eic is not a key: 1 EICs"):
        static_grid.join_on_eic(elements, tr)


def test_a_join_that_does_not_collide_goes_through():
    tr = static_grid.transformers(sheet("transformers-sample.csv"))
    elements = pd.DataFrame({"eic": ["30T-ROSI400AT--1", "19T0000000063830"]})
    joined = static_grid.join_on_eic(elements, tr)
    assert len(joined) == 2
    assert joined.s_nom.notna().all()


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


def test_the_placeholder_eic_is_blanked_rather_than_treated_as_a_key():
    """Three line rows write `N.A.` where 29 others leave the EIC blank."""
    branches = static_grid.branches(sheet("lines-sample.csv"), sheet("tielines-sample.csv"))
    assert not branches.eic.eq(static_grid.EIC_PLACEHOLDER).any()
    hollandse = branches[branches.name.str.startswith("Hollandse Kust Zuid")]
    assert not hollandse.empty
    assert hollandse.eic.isna().all()
    assert static_grid.eic_collisions(branches).eic.notna().all()


def test_the_seasonal_rating_is_the_highest_of_the_six_periods():
    """RTE's Airvault-Bonneau publishes 932, 932, 1145, 1145, blank, 0.0 — max, not first."""
    branches = static_grid.branches(sheet("lines-sample.csv"), sheet("tielines-sample.csv"))
    airvault = branches[branches.eic == "17T000000015268T"]
    assert airvault.imax_seasonal.iloc[0] == 1145.0
    assert branches.imax_seasonal.notna().any()
    assert branches.imax_fixed.notna().any()


def test_a_non_numeric_period_does_not_become_a_rating():
    """Beznau-Tiengen publishes 1792, 1792, 2187 and then `-` three times, and `-` as `Fixed`."""
    branches = static_grid.branches(sheet("lines-sample.csv"), sheet("tielines-sample.csv"))
    beznau = branches[branches.eic == "10T-CH-DE-000034"]
    assert beznau.imax_seasonal.iloc[0] == 2187.0
    assert pd.isna(beznau.imax_fixed.iloc[0])


def test_s_nom_is_three_phase_apparent_power_in_mva():
    assert static_grid.s_nom(pd.Series([400.0]), pd.Series([577.0])).iloc[0] == pytest.approx(399.76, abs=0.01)
