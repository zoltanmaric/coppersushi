"""Select historical training outcomes independently of retrospective scoring truth."""
from datetime import date

import pyarrow as pa

from forecasts.dataset import cutoff
from forecasts.input_types import PriceSeries
from forecasts.prices import read_prices, select_history
from forecasts.schemas import SCHEMAS
from forecasts.snapshot import InputReader


def select_labels(reader: InputReader, fit_day: date) -> PriceSeries:
    """Return earlier price outcomes eligible at the fit day's first issue.

    Both model fitting and reference calibration use this path. Never substitute
    the reader's retrospective scoring truth for these version-selected labels.
    """
    candidates = [row for rows in reader.daily["prices"].values() for row in rows]
    table = pa.Table.from_pylist(candidates, schema=SCHEMAS["prices"])
    selected = select_history(read_prices(table), fit_day, cutoff(fit_day))
    return dict(selected.select("valid_utc", "price_eur_mwh").iter_rows())
