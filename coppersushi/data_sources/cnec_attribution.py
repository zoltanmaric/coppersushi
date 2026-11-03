"""Small public JAO feeds required for normalized FB and Polish cap attribution."""

import tempfile
import time
from pathlib import Path

import pandas as pd
from pandera.typing import DataFrame

from coppersushi.data_model.cnec_attribution import (
    JaoRecord, AlphaFactor, AllocationConstraint, NetPosition, PolishAlternative, AttributionContext,
)

from coppersushi import cnec_attribution
from coppersushi.data_sources import cache, jao
from coppersushi.market_day import MarketDay

def load_day(day: str, refresh: bool = False) -> DataFrame[AttributionContext]:
    """Cache complete inputs; empty feeds leave gaps, while loading and validation errors raise."""
    path = jao.day_dir(day) / "attribution.csv"
    delivery = MarketDay.on(day)
    key = f"jao/attribution/{day}"
    if not refresh and not path.is_file():
        cache.restore(key, path.parent, (path.name,))
    if path.is_file() and not refresh:
        frame = pd.read_csv(path)
        frame = frame.assign(interval=pd.to_datetime(frame.interval, utc=True))
        frame = AttributionContext.validate(frame)
        if not frame.notna().all().all() or frame.interval.tolist() != list(delivery.market_time_units()):
            raise ValueError(f"Incomplete attribution cache for {day}")
        return frame

    def fetch[T: JaoRecord](endpoint: str, model: type[T], pause: bool = True) -> list[T]:
        if pause:
            # Conservative local pacing; concurrent callers still share the IP's quota.
            # Official limit and bulk-query guidance: wiki/jao-availability.md#rate-limits.
            time.sleep(1.5)
        kwargs = {"base_url": "https://publicationtool.jao.eu/crossCCR/api/data"} if endpoint == "DA_PL_AC" else {}
        rows = jao._get(endpoint, delivery.start_time_utc, delivery.end_time_utc,
                        timeout=10, **kwargs)
        return [model.model_validate(row) for row in rows]

    frame = cnec_attribution.context(
        delivery,
        fetch("alphaFactor", AlphaFactor, pause=False),
        fetch("allocationConstraint", AllocationConstraint),
        fetch("netPos", NetPosition),
        # JAO omitted 00:00–01:00 UTC on 2026-10-25 even for the full 25-hour query.
        # See wiki/country-import-export-caps.md#publication-coverage for evidence and gaps.
        fetch("DA_PL_AC", PolishAlternative),
    )
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
