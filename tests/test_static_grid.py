import pandas as pd
import pytest

from coppersushi import REPO, static_grid

FIXTURES = REPO / "tests" / "fixtures" / "static-grid"


def sheet(name: str) -> pd.DataFrame:
    """A synthesised sheet under the workbook's own headers, as `read_excel(header=1)` hands it over.

    JAO's terms forbid redistributing their tables, so the rows are invented; each one
    reproduces a shape measured in the 5th release, recorded beside the case it exercises.
    """
    return pd.read_csv(FIXTURES / name)


def transformers() -> pd.DataFrame:
    return static_grid.transformers(sheet("transformers-sample.csv"))


def branches() -> pd.DataFrame:
    return static_grid.branches(sheet("lines-sample.csv"), sheet("tielines-sample.csv"))


def elements() -> pd.DataFrame:
    """The publication feed's shape, keyed on the same EICs as the transformer sheet."""
    return sheet("elements-sample.csv")


def test_s_nom_is_three_phase_apparent_power_in_mva():
    assert static_grid.s_nom(pd.Series([400.0]), pd.Series([577.0])).iloc[0] == pytest.approx(399.76, abs=0.01)


def test_s_nom_of_a_fixed_rated_transformer_is_its_nameplate_mva():
    """√3 · 400 kV · 577 A: the shape that reproduced JAO's published fmax of 400 for TR Rosiori."""
    charlie = transformers().set_index("eic").loc["99T-CHARL-TR001C"]
    assert charlie.imax == 577.0
    assert charlie.s_nom == pytest.approx(400.0, abs=1.0)


def test_a_phase_shifter_is_flagged_by_its_angle():
    tr = transformers().set_index("eic")
    assert tr.loc["99T-BRAVO-PS001B"].is_pst  # θ = 90
    assert tr.loc["99T-GOLF0-TR001G"].is_pst  # θ = 0 is published, so it counts
    assert not tr.loc["99T-CHARL-TR001C"].is_pst  # θ absent


def test_a_row_with_only_a_fixed_rating_still_gets_one():
    tr = transformers()
    assert tr.imax.notna().all()
    assert tr.s_nom.gt(0).all()
    assert tr.set_index("eic").loc["99T-DELTA-TR001D"].imax == 1443.0


def test_the_rating_falls_back_past_fixed_to_min():
    """Only 339 of the release's 520 rows publish `Max`; the chain is Max, Fixed, Min."""
    tr = transformers().set_index("eic")
    assert tr.loc["99T-ALPHA-TR001A"].imax == 866.0  # Max, over the Min beside it
    assert tr.loc["99T-CHARL-TR001C"].imax == 577.0  # Fixed, no Max
    assert tr.loc["99T-GOLF0-TR001G"].imax == 500.0  # Min alone


def test_a_row_with_no_rating_at_all_is_refused():
    rows = sheet("transformers-sample.csv").assign(Min=None, Max=None, Fixed=None)
    with pytest.raises(ValueError, match="no current rating"):
        static_grid.transformers(rows)


def test_impedance_survives_for_every_row():
    tr = transformers()
    assert tr.x.notna().all()
    assert tr[tr.x_physical].x.gt(0).all()


def test_a_negative_reactance_is_flagged_rather_than_dropped_or_repaired():
    """One row of the release publishes a reactance of −11.7 Ω; PR 6 divides by it."""
    foxtrot = transformers().set_index("eic").loc["99T-FOXTR-TR001F"]
    assert foxtrot.x == -11.7
    assert not foxtrot.x_physical
    assert transformers().x_physical.sum() == len(transformers()) - 1


def test_a_zero_reactance_branch_is_flagged_too():
    """A branch of exactly zero reactance is a short circuit, not a small impedance."""
    november = branches().set_index("name").loc["November - Oscar 380 Z"]
    assert november.x == 0.0
    assert not november.x_physical
    assert branches()[branches().x_physical].x.gt(0).all()


def test_a_branch_with_no_reactance_published_is_flagged_too():
    """The release's one DC cable publishes no electrical parameters at all."""
    victor = branches().set_index("name").loc["Victor - Whiskey (DC cable)"]
    assert pd.isna(victor.x)
    assert not victor.x_physical


def test_two_transformers_sharing_an_eic_are_both_kept():
    """The release publishes one EIC for two transformers whose R, X and rating all differ."""
    tr = transformers()
    echo = tr[tr.eic == "99T-ECHO0-TR001E"]
    assert len(echo) == 2
    assert echo.x.nunique() == 2 and echo.imax.nunique() == 2
    assert set(static_grid.eic_collisions(tr).eic) == {"99T-ECHO0-TR001E"}


def test_the_static_model_joins_to_the_publication_feed_on_eic():
    """The feed's `cneEic` and the workbook's `EIC_Code` are one key: 103 of the day's 106 join."""
    monitored = elements()[elements().element_type.isin(("Transformer", "PST"))]
    joined = static_grid.join_on_eic(monitored[monitored.eic != "99T-ECHO0-TR001E"], transformers())
    assert len(joined) == 2
    assert joined.s_nom.notna().all()
    assert joined.fmax.notna().all()


def test_joining_on_a_colliding_eic_raises_instead_of_multiplying_rows():
    """`merge(on="eic")` would silently return an extra row for the shared EIC; this must not."""
    with pytest.raises(ValueError, match="eic is not a key: 1 EICs"):
        static_grid.join_on_eic(elements(), transformers())


def test_an_element_the_workbook_does_not_carry_joins_to_nothing_rather_than_vanishing():
    """Three of the day's 106 EICs are absent from the release; a left join must keep them."""
    joined = static_grid.join_on_eic(elements().tail(1), transformers())
    assert len(joined) == 1
    assert pd.isna(joined.s_nom.iloc[0])


def test_branches_carry_both_sheets_and_their_substation_names():
    b = branches()
    assert b.is_tieline.any() and not b.is_tieline.all()
    assert b.substation_from.ne("").all() and b.substation_to.ne("").all()
    assert b.substation_from.eq(b.substation_from.str.strip()).all()


def test_the_placeholder_eic_is_blanked_rather_than_treated_as_a_key():
    """Three line rows write the literal `N.A.` where 29 others leave the EIC blank."""
    b = branches()
    assert not b.eic.eq(static_grid.EIC_PLACEHOLDER).any()
    assert b[b.name == "Romeo - Sierra 380 W"].eic.isna().all()
    assert b[b.name == "Papa - Quebec 220"].eic.isna().all()
    assert static_grid.eic_collisions(b).eic.notna().all()


def test_a_tie_line_published_by_both_its_tsos_keeps_both_rows():
    """334 tie-line rows carry only 210 distinct EICs: each end's TSO publishes its own."""
    zulu = branches()[branches().eic == "99T-ZA-000001Z"]
    assert len(zulu) == 2
    assert zulu.tso.nunique() == 2
    assert zulu.is_tieline.all()


def test_the_seasonal_rating_is_the_highest_of_the_six_periods():
    """Periods 932, 932, 1145, 1145, blank, 0.0 — the max, not the first, last or mean."""
    juliett = branches().set_index("name").loc["Juliett - Kilo 380"]
    assert juliett.imax_seasonal == 1145.0
    assert pd.isna(juliett.imax_fixed)


def test_a_non_numeric_period_does_not_become_a_rating():
    """The tie-line sheet writes `-` in 295 period and `Fixed` cells; one line cell holds `;`."""
    xray = branches().set_index("name").loc["Xray - Yankee 400"]
    assert xray.imax_seasonal == 2187.0
    assert pd.isna(xray.imax_fixed)


def test_a_column_whose_name_cannot_be_matched_is_refused_rather_than_guessed():
    """The workbook spells the same unit two ways, so columns are matched on letters and digits."""
    rows = sheet("transformers-sample.csv")
    rows = rows.drop(columns=[c for c in rows.columns if c.startswith("Reactance")])
    with pytest.raises(KeyError, match="reactancex"):
        static_grid.transformers(rows)
