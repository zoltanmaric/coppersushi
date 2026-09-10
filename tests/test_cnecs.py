import json

import pandas as pd
import pandera.errors
import pytest

from coppersushi import REPO, cnecs
from coppersushi.data_model.jao import Elements

FIXTURES = REPO / "tests" / "fixtures" / "synthetic-jao"


def rows(name: str) -> list[dict]:
    return json.loads((FIXTURES / name).read_text())["data"]


def final_computation() -> list[dict]:
    return rows("final-computation-hour.json")


def untyped_element() -> list[dict]:
    """Two rows of one element, one presolved, in the shape JAO publishes an untyped line.

    A 220 kV line with an EIC and an fmax, published with no `elementType` and the literal
    `"NA"` for its hubs, substations and direction. Synthesised: the licence forbids
    redistributing JAO's own rows.
    """
    return rows("final-computation-untyped-element.json")


def active_fb() -> list[dict]:
    """Invented rows in the active flow-based response shape; no JAO values are redistributed."""
    return rows("active-fb-day.json")


def test_non_physical_rows_are_filtered_from_final_computation_too():
    elements = cnecs.elements(final_computation())
    assert not elements.eic.eq(cnecs.PLACEHOLDER).any()
    assert not elements.name.str.startswith(cnecs.NON_PHYSICAL).any()
    externals = cnecs.external_constraints(final_computation())
    assert len(externals) >= 2


def test_names_are_stripped():
    elements = cnecs.elements(final_computation())
    assert (elements.name == elements.name.str.strip()).all()
    assert (elements.substation_from == elements.substation_from.str.strip()).all()
    assert elements.name.eq("Elmridge - Fernhollow 247").any()


def test_one_row_per_element_hour_and_direction():
    elements = cnecs.elements(final_computation())
    assert not elements.duplicated(subset=["hour", "eic", "direction"]).any()
    assert set(elements.element_type) <= {"Line", "TieLine", "Transformer", "PST", ""}


def test_hour_is_utc_aware():
    assert str(cnecs.elements(final_computation()).hour.dt.tz) == "UTC"


def test_a_naive_hour_is_rejected_rather_than_localised():
    elements = cnecs.elements(final_computation())
    naive = elements.assign(hour=elements.hour.dt.tz_localize(None))
    with pytest.raises(pandera.errors.SchemaErrors):
        Elements.validate(naive)


def test_two_tsos_disagreeing_yields_the_tighter_limit_and_a_flag():
    elements = cnecs.elements(final_computation())
    shared = elements[elements.eic == "99T1001C--00101B"]
    assert not shared.empty
    assert shared.fmax.eq(1140.0).all()         # VOLTRA's tighter rating, not MERIDIA's 1420
    assert shared.tso_disagreement.all()


def test_a_differing_fmax_without_a_differing_tso_is_an_error():
    raw = [dict(r) for r in final_computation()]
    for row in raw:
        if row.get("cneEic") == "99T1001C--00101B":
            row["tso"] = "VOLTRA"                # force one TSO, two fmax values
    with pytest.raises(ValueError, match="99T1001C--00101B"):
        cnecs.elements(raw)


def test_element_ends_keep_each_tsos_own_orientation():
    shared, other = "99T1001C--00101B", "VOLTRA"
    feed = [
        {**row, "substationFrom": row["substationTo"], "substationTo": row["substationFrom"]}
        if row["cneEic"] == shared and row["tso"] == other
        else row
        for row in final_computation()
    ]
    ends = cnecs.element_ends(feed)
    assert list(ends.columns) == cnecs.END_COLUMNS
    assert not ends.duplicated(["eic", "tso"]).any()
    both = ends[ends.eic.eq(shared)].set_index("tso")
    assert both.loc["MERIDIA", "substation_from"] == "Cindervale"
    assert both.loc[other, "substation_from"] == "Dunmoor"


def test_one_tso_naming_two_pairs_for_one_element_is_refused():
    feed = final_computation()
    element = next(row for row in feed if row["cneEic"] == "99T-AA-BB-00003P")
    with pytest.raises(ValueError, match="99T-AA-BB-00003P"):
        cnecs.element_ends(feed + [{**element, "substationTo": "Nowhere"}])


def test_contingencies_come_from_the_structured_field():
    conts = cnecs.contingencies(final_computation())
    monitored = conts[conts.eic == "99T-AA-BB-00003P"]
    assert not monitored.empty
    assert "Grayspire" in set(monitored.substation_from)
    assert monitored.branch_eic.notna().all()


def test_tso_casing_is_normalised_across_the_two_feeds():
    assert list(cnecs.normalise_tso(pd.Series(["Avalon", "NordekGmbh", "NA", None]))) == [
        "AVALON", "NORDEKGMBH", "", ""
    ]


def test_shadow_prices_join_one_to_one():
    elements = cnecs.elements(final_computation())
    prices = cnecs.shadow_prices(rows("shadow-prices-day.json"))
    joined = cnecs.with_shadow_prices(elements, prices)
    assert len(joined) == len(elements)
    assert joined.shadow_price.notna().any()
    assert "binding_contingency" in joined


def test_an_unmatched_shadow_price_is_an_error_not_a_silent_drop():
    elements = cnecs.elements(final_computation())
    prices = cnecs.shadow_prices(rows("shadow-prices-day.json"))
    stray = prices[prices.hour.isin(elements.hour)].copy()
    assert not stray.empty, "the fixture needs a physical shadow price in the elements' hour"
    stray.iloc[0, stray.columns.get_loc("eic")] = "NOT-AN-ELEMENT"
    with pytest.raises(ValueError, match="NOT-AN-ELEMENT"):
        cnecs.with_shadow_prices(elements, stray)


def test_two_prices_for_one_element_name_it_rather_than_failing_in_the_merge():
    elements = cnecs.elements(final_computation())
    prices = cnecs.shadow_prices(rows("shadow-prices-day.json"))
    within = prices[prices.hour.isin(elements.hour)]
    assert not within.empty
    doubled = pd.concat([prices, within.head(1)], ignore_index=True)
    with pytest.raises(ValueError, match=str(within.iloc[0].eic)):
        cnecs.with_shadow_prices(elements, doubled)


def test_an_element_with_no_type_is_not_an_external_constraint():
    """Classification follows the handbook's definition, not the presence of metadata."""
    assert cnecs.external_constraints(untyped_element()).empty


def test_an_element_with_no_type_keeps_its_eic_and_its_limit():
    elements = cnecs.elements(untyped_element())
    assert list(elements.eic) == ["94T-220-0-00919F"]
    assert elements.fmax.iloc[0] == 648.0
    assert elements.ram.iloc[0] == 352.0
    assert elements.element_type.iloc[0] == ""
    assert elements.substation_from.iloc[0] == ""
    assert elements.direction.iloc[0] == ""


def test_the_na_placeholder_never_survives_as_a_value():
    elements = cnecs.elements(final_computation() + untyped_element())
    for column in ["direction", "hub_from", "hub_to", "substation_from", "substation_to", "element_type"]:
        assert not elements[column].eq(cnecs.PLACEHOLDER).any()


def test_a_constraint_that_bound_is_one_row_carrying_its_price():
    hourly = cnecs.external_constraints(final_computation())
    priced = cnecs.external_constraints(rows("shadow-prices-day.json"))
    joined = cnecs.with_constraint_prices(hourly, priced)
    assert len(joined) == len(hourly)
    assert joined.shadow_price.notna().any()
    assert set(joined.loc[joined.shadow_price.notna(), "binding_direction"]) == {"OPPOSITE"}


def test_a_constraint_assessed_under_several_contingencies_is_one_row_with_the_tightest_margin():
    feed = final_computation()
    constraint = next(row for row in feed if row["cneName"] == "External Constraint AA_XL_export")
    under_outage = {**constraint, "contName": "Grayspire - Dunmoor", "ram": constraint["ram"] - 250}
    hourly = cnecs.external_constraints(feed + [under_outage])
    rows_for = hourly[hourly.name.eq("External Constraint AA_XL_export")]
    assert len(rows_for) == 1
    assert rows_for.ram.iloc[0] == constraint["ram"] - 250
    assert rows_for.fmax.iloc[0] == constraint["fmax"]


def test_a_price_for_a_constraint_the_domain_feed_never_published_is_an_error():
    hourly = cnecs.external_constraints(final_computation())
    priced = cnecs.external_constraints(rows("shadow-prices-day.json"))
    stray = priced[priced.hour.isin(hourly.hour)].copy()
    assert not stray.empty, "the fixture needs a priced constraint in the domain feed's hour"
    stray.iloc[0, stray.columns.get_loc("name")] = "External Constraint NOWHERE"
    with pytest.raises(ValueError, match="NOWHERE"):
        cnecs.with_constraint_prices(hourly, stray)


def test_active_fb_keeps_two_contingencies_on_one_element_as_two_constraints():
    active = cnecs.active_constraints(active_fb())
    assert len(active) == 2
    assert active.eic.nunique() == 1
    assert active.cont_name.isna().sum() == 1
    assert active.source_id.is_unique
    assert str(active.interval.dt.tz) == "UTC"


def test_active_fb_ptdfs_are_one_row_per_constraint_and_core_zone():
    ptdfs = cnecs.constraint_ptdfs(active_fb())
    assert len(ptdfs) == 2 * 12
    assert set(ptdfs.zone) == {"AT", "BE", "CZ", "DE", "FR", "HR", "HU", "NL", "PL", "RO", "SI", "SK"}


def test_contribution_is_shadow_price_times_the_ptdf_difference_with_the_documented_sign():
    active = cnecs.active_constraints(active_fb()).iloc[0]
    contribution = cnecs.price_contributions(active, cnecs.constraint_ptdfs(active_fb()), "AT")
    values = contribution.set_index("zone").contribution
    assert values["AT"] == pytest.approx(0.0)
    assert values["BE"] == pytest.approx(2.87)
    assert contribution.reference_zone.eq("AT").all()


def test_contribution_requires_an_explicit_core_reference_zone():
    active = cnecs.active_constraints(active_fb()).iloc[0]
    with pytest.raises(ValueError, match="reference zone"):
        cnecs.price_contributions(active, cnecs.constraint_ptdfs(active_fb()), "GB")


def test_active_non_spatial_rows_are_retained_separately():
    external = cnecs.active_external_constraints(active_fb())
    assert list(external.name) == ["External Constraint ALPHA_export"]
    assert external.shadow_price.iloc[0] == 12.0


def test_a_repeated_active_row_identifier_is_refused():
    duplicate = active_fb() + [dict(active_fb()[0])]
    with pytest.raises(ValueError, match="repeated active"):
        cnecs.active_constraints(duplicate)
