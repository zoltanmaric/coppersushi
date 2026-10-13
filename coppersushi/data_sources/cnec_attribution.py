"""Small public JAO feeds required for normalized FB and Polish cap attribution."""

import logging
import tempfile
import time
from pathlib import Path

import pandas as pd

from coppersushi import cnec_attribution
from coppersushi.data_sources import jao
from coppersushi.market_day import MarketDay

logger = logging.getLogger(__name__)


def load_day(day: str, refresh: bool = False) -> pd.DataFrame:
    """Cache only complete successful inputs; optional outages leave contributions unavailable."""
    path = jao.day_dir(day) / "attribution.csv"
    delivery = MarketDay.on(day)
    if path.is_file() and not refresh:
        try:
            frame = pd.read_csv(path)
            frame = frame.assign(interval=pd.to_datetime(frame.interval, utc=True))
            fields = {"interval", "alpha", "import_limit", "export_limit", "polish_position", "polish_alt"}
            if fields.issubset(frame) and frame.notna().all().all() and frame.interval.tolist() == list(delivery.market_time_units()):
                return frame
        except (OSError, ValueError, AttributeError):
            logger.exception("Ignoring unusable attribution cache for %s", day)
    feeds = []
    complete = True
    for index, endpoint in enumerate(["alphaFactor", "allocationConstraint", "netPos", "DA_PL_AC"]):
        if index:
            time.sleep(1.5)  # Respect the publication service's rate limit, including small feeds.
        try:
            kwargs = {"base_url": "https://publicationtool.jao.eu/crossCCR/api/data"} if endpoint == "DA_PL_AC" else {}
            feeds.append(jao._get(endpoint, delivery.start_time_utc, delivery.end_time_utc,
                                  timeout=10, **kwargs))
        except Exception:
            logger.exception("Attribution input %s unavailable for %s", endpoint, day)
            feeds.append([])
            complete = False
    try:
        frame = cnec_attribution.context(delivery, *feeds)
    except (ValueError, TypeError, KeyError):
        logger.exception("Invalid attribution inputs for %s", day)
        return cnec_attribution.context(delivery, [], [], [], [])
    if complete and frame.notna().all().all():
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".csv", delete=False) as file:
            temporary = Path(file.name)
        try:
            frame.to_csv(temporary, index=False)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return frame
