import json

import pandas as pd

from coppersushi import REPO, cnec_market, cnecs, market
from coppersushi.data_model.market import ElectricityMapsPriceResponse

FIXTURE = REPO / "tests" / "fixtures" / "synthetic-jao" / "active-fb-day.json"


def active_rows() -> list[dict]:
    return json.loads(FIXTURE.read_text())["data"]


PRICE_FIXTURE = REPO / "tests" / "fixtures" / "synthetic-electricity-maps" / "day-ahead-prices-day.json"


def price_payloads() -> list[ElectricityMapsPriceResponse]:
    return [ElectricityMapsPriceResponse.model_validate_json(PRICE_FIXTURE.read_text())]


def inputs():
    rows = active_rows()
    return (
        cnecs.active_constraints(rows),
        market.day_ahead_prices(price_payloads()),
    )


def test_an_interval_with_no_binding_row_still_has_its_published_prices():
    view = cnec_market.snapshot(*inputs(), pd.Timestamp("2024-08-28T23:00:00Z"))
    assert view.constraints.empty
    assert view.prices.set_index("zone").price.to_dict() == {"AT": 41.0}
