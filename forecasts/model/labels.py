"""Select historical training outcomes independently of retrospective scoring truth."""
from datetime import date

from forecasts.inputs.input_types import PriceSeries
from forecasts.inputs.selection import PriceHistoryReader
from forecasts.market import cutoff


def select_labels(reader: PriceHistoryReader, fit_day: date) -> PriceSeries:
    """Return earlier price outcomes eligible at the fit day's first issue.

    Both model fitting and reference calibration use this path. Never substitute
    the reader's retrospective scoring truth for these version-selected labels.
    """
    selected = reader.price_history(fit_day, cutoff(fit_day))
    return dict(selected.select("valid_utc", "price_eur_mwh").iter_rows())
