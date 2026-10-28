"""Select historical training outcomes independently of retrospective scoring truth."""
from datetime import date

from forecasts.dataset import cutoff
from forecasts.input_types import PriceSeries
from forecasts.prices import select_history
from forecasts.snapshot import InputReader


def select_labels(reader: InputReader, fit_day: date) -> PriceSeries:
    """Return earlier price outcomes eligible at the fit day's first issue.

    Both model fitting and reference calibration use this path. Never substitute
    the reader's retrospective scoring truth for these version-selected labels.
    """
    selected = select_history(reader.prices, fit_day, cutoff(fit_day))
    return dict(selected.select("valid_utc", "price_eur_mwh").iter_rows())
