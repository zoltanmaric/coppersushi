"""Small public JAO feeds required for normalized FB and Polish cap attribution."""

import logging
import tempfile
import time
from pathlib import Path

import pandas as pd
from pandera.errors import SchemaError
from pandera.typing import DataFrame

from coppersushi.data_model.cnec_attribution import (
    JaoRecord, AlphaFactor, AllocationConstraint, NetPosition, PolishAlternative, AttributionContext,
)

from coppersushi import cnec_attribution
from coppersushi.data_sources import cache, jao
from coppersushi.market_day import MarketDay

logger = logging.getLogger(__name__)


def load_day(day: str, refresh: bool = False) -> DataFrame[AttributionContext]:
    """Cache only complete successful inputs; optional outages leave contributions unavailable."""
    path = jao.day_dir(day) / "attribution.csv"
    delivery = MarketDay.on(day)
    key = f"jao/attribution/{day}"
    if not refresh and not path.is_file():
        cache.restore(key, path.parent, (path.name,))
    if path.is_file() and not refresh:
        try:
            frame = pd.read_csv(path)
            frame = frame.assign(interval=pd.to_datetime(frame.interval, utc=True))
            frame = AttributionContext.validate(frame)
            if frame.notna().all().all() and frame.interval.tolist() == list(delivery.market_time_units()):
                return frame
        except (OSError, ValueError, AttributeError, SchemaError):
            logger.exception("Ignoring unusable attribution cache for %s", day)
    def fetch[T: JaoRecord](endpoint: str, model: type[T], pause: bool = True) -> list[T]:
        if pause:
            time.sleep(1.5)  # Respect the publication service's rate limit, including small feeds.
        try:
            kwargs = {"base_url": "https://publicationtool.jao.eu/crossCCR/api/data"} if endpoint == "DA_PL_AC" else {}
            rows = jao._get(endpoint, delivery.start_time_utc, delivery.end_time_utc,
                            timeout=10, **kwargs)
            return [model.model_validate(row) for row in rows]
        except Exception:
            logger.exception("Attribution input %s unavailable for %s", endpoint, day)
            return []

    try:
        frame = cnec_attribution.context(
            delivery,
            fetch("alphaFactor", AlphaFactor, pause=False),
            fetch("allocationConstraint", AllocationConstraint),
            fetch("netPos", NetPosition),
            fetch("DA_PL_AC", PolishAlternative),
        )
    except (ValueError, TypeError, KeyError, SchemaError):
        logger.exception("Invalid attribution inputs for %s", day)
        return cnec_attribution.context(delivery, [], [], [], [])
    if frame.notna().all().all():
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".csv", delete=False) as file:
            temporary = Path(file.name)
        try:
            frame.to_csv(temporary, index=False)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        cache.publish(key, path.parent, (path.name,))
    return frame
