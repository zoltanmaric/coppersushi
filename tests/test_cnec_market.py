import json

import pandas as pd
import pytest

from coppersushi import REPO, cnec_market, cnecs, market

FIXTURE = REPO / "tests" / "fixtures" / "synthetic-jao" / "active-fb-day.json"


def active_rows() -> list[dict]:
    return json.loads(FIXTURE.read_text())["data"]


PRICE_FIXTURE = (
    REPO / "tests" / "fixtures" / "synthetic-electricity-maps" / "day-ahead-prices-hour.json"
)


def price_payloads() -> list[dict]:
    return json.loads(PRICE_FIXTURE.read_text())["responses"]


def inputs():
    rows = active_rows()
    return (
        cnecs.active_constraints(rows),
        cnecs.constraint_ptdfs(rows),
        cnecs.active_external_constraints(rows),
        market.day_ahead_prices(price_payloads()),
    )


def test_an_interval_with_no_binding_row_still_has_its_published_prices():
    view = cnec_market.snapshot(*inputs(), pd.Timestamp("2024-08-28T22:15:00Z"))
    assert view.constraints.empty
    assert view.external_constraints.empty
    assert view.prices.set_index("zone").price.to_dict() == {"AT": 50.0, "BE": 70.0}
    assert view.contribution is None


def test_selecting_a_row_adds_its_relative_contribution():
    interval = pd.Timestamp("2024-08-28T22:00:00Z")
    base = cnec_market.snapshot(*inputs(), interval)
    selected = cnec_market.key_of(base.constraints.iloc[0])
    view = cnec_market.snapshot(*inputs(), interval, selected, "AT")
    contribution = view.contribution.set_index("zone").contribution
    assert contribution["AT"] == pytest.approx(0.0)
    assert contribution["BE"] == pytest.approx(2.87)


def test_a_selection_requires_an_explicit_reference():
    interval = pd.Timestamp("2024-08-28T22:00:00Z")
    base = cnec_market.snapshot(*inputs(), interval)
    with pytest.raises(ValueError, match="explicit reference"):
        cnec_market.snapshot(*inputs(), interval, cnec_market.key_of(base.constraints.iloc[0]))


def test_a_selection_from_another_interval_is_refused():
    interval = pd.Timestamp("2024-08-28T22:00:00Z")
    base = cnec_market.snapshot(*inputs(), interval)
    selected = cnec_market.key_of(base.constraints.iloc[0])
    with pytest.raises(ValueError, match="matched 0"):
        cnec_market.snapshot(*inputs(), pd.Timestamp("2024-08-28T22:15:00Z"), selected, "AT")
