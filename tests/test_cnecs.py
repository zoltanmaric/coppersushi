import json

import pandas as pd
import pandera.errors
import pytest

from coppersushi import REPO, cnecs
from coppersushi.data_model.jao import Elements

FIXTURES = REPO / "tests" / "fixtures" / "jao"


def rows(name: str) -> list[dict]:
    return json.loads((FIXTURES / name).read_text())["data"]


def final_computation() -> list[dict]:
    return rows("final-computation-hour.json")


def untyped_element() -> list[dict]:
    """Two `St. Peter 2 - Salzburg 455` rows of 2024-08-29T05:00Z, verbatim, one presolved.

    A real 220 kV APG line with an EIC and an fmax, published with no `elementType`, no hubs,
    no substations and no direction at all. JAO presolved it in four hours of 2024-08-29.
    """
    return rows("final-computation-untyped-element.json")


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
    assert elements.name.eq("Obersielach - Podlog 247").any()


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
    heviz = elements[elements.eic == "10T1001C--00101B"]
    assert not heviz.empty
    assert heviz.fmax.eq(1109.0).all()          # ELES's tighter rating, not MAVIR's 1386
    assert heviz.tso_disagreement.all()


def test_a_differing_fmax_without_a_differing_tso_is_an_error():
    raw = [dict(r) for r in final_computation()]
    for row in raw:
        if row.get("cneEic") == "10T1001C--00101B":
            row["tso"] = "ELES"                  # force one TSO, two fmax values
    with pytest.raises(ValueError, match="10T1001C--00101B"):
        cnecs.elements(raw)


def test_contingencies_come_from_the_structured_field():
    conts = cnecs.contingencies(final_computation())
    obersielach = conts[conts.eic == "10T-AT-SI-00003P"]
    assert not obersielach.empty
    assert "Kainachtal" in set(obersielach.substation_from)
    assert obersielach.branch_eic.notna().all()


def test_tso_casing_is_normalised_across_the_two_feeds():
    assert list(cnecs.normalise_tso(pd.Series(["Apg", "TennetGmbh", "NA", None]))) == [
        "APG", "TENNETGMBH", "", ""
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
    assert list(elements.eic) == ["14T-220-0-00455F"]
    assert elements.fmax.iloc[0] == 624.0
    assert elements.ram.iloc[0] == 336.0
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


def test_a_price_for_a_constraint_the_domain_feed_never_published_is_an_error():
    hourly = cnecs.external_constraints(final_computation())
    priced = cnecs.external_constraints(rows("shadow-prices-day.json"))
    stray = priced[priced.hour.isin(hourly.hour)].copy()
    assert not stray.empty, "the fixture needs a priced constraint in the domain feed's hour"
    stray.iloc[0, stray.columns.get_loc("name")] = "External Constraint NOWHERE"
    with pytest.raises(ValueError, match="NOWHERE"):
        cnecs.with_constraint_prices(hourly, stray)
