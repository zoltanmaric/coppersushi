"""Build model inputs at each delivery day's historical issue cutoff."""
from datetime import date
from collections.abc import Sequence

import numpy as np

from forecasts.config import MODEL_METHOD
from forecasts.contracts import FloatArray
from forecasts.dataset import CALENDAR_COLUMNS
from pandera.typing.polars import DataFrame
from forecasts.prices import PRICE_FEATURES
from forecasts.tables import Features, PRICE_MISSING_FIELDS
from forecasts.snapshot import InputReader

FEATURES = {MODEL_METHOD: [*CALENDAR_COLUMNS, *PRICE_FEATURES, *PRICE_MISSING_FIELDS]}


def build_features(reader: InputReader, start: date, end: date, *,
                   complete_from: date | None = None) -> DataFrame[Features]:
    """Build quarter-hour rows in [start, end), with no realised target values.

    Each day uses only inputs eligible by 11:00 Berlin on the preceding day.
    The input reader selects price versions and builds price and calendar inputs.
    """
    return reader.historical_features(start, end, complete_from=complete_from)


def feature_matrix(rows: DataFrame[Features], fields: Sequence[str]) -> FloatArray:
    """Select the frozen feature columns, mapping missing values to NaN.

    Targets and audit metadata are excluded by the explicit column inventory.
    """
    return rows.select(fields).to_numpy().astype(np.float64, copy=False)
