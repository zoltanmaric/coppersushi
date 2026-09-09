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
    assert set(elements.element_type) <= {"Line", "TieLine", "Transformer", "PST"}


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
