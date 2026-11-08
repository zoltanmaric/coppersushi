"""Small public JAO feeds required for normalized FB and Polish cap attribution."""

import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import pandas as pd
from pandera.typing import DataFrame

from coppersushi.data_model.cnec_attribution import (
    JaoRecord, AlphaFactor, AllocationConstraint, NetPosition, PolishAlternative, AttributionContext, normalize_alpha,
)

from coppersushi import cnec_attribution
from coppersushi.data_sources import cache, jao
from coppersushi.market_day import MarketDay

POLISH_ALTERNATIVE_PUBLICATION_START = date(2026, 5, 6)

def load_day(day: MarketDay, refresh: bool = False) -> DataFrame[AttributionContext]:
    """Cache complete inputs; empty feeds leave gaps, while loading and validation errors raise."""
    day_key = day.date.isoformat()
    path = jao.day_dir(day_key) / "attribution.csv"
    key = f"jao/attribution/{day_key}"
    if not refresh and not path.is_file():
        cache.restore(key, path.parent, (path.name,))
    if path.is_file() and not refresh:
        frame = pd.read_csv(path)
        frame = frame.assign(interval=pd.to_datetime(frame.interval, utc=True),
                             alpha=frame.alpha.map(normalize_alpha))
        frame = AttributionContext.validate(frame)
        if not frame.notna().all().all() or frame.interval.tolist() != list(day.market_time_units()):
            raise ValueError(f"Incomplete attribution cache for {day_key}")
        return frame

    def fetch[T: JaoRecord](endpoint: str, model: type[T]) -> list[T]:
        kwargs = {"base_url": "https://publicationtool.jao.eu/crossCCR/api/data"} if endpoint == "DA_PL_AC" else {}
        rows = jao._get(endpoint, day.start_time_utc, day.end_time_utc,
                        timeout=10, **kwargs)
        return [model.model_validate(row) for row in rows]

    # Independent feeds share JAO's process-wide request budget and cooldown.
    with ThreadPoolExecutor(max_workers=4) as pool:
        alpha = pool.submit(fetch, 'alphaFactor', AlphaFactor)
        allocation = pool.submit(fetch, 'allocationConstraint', AllocationConstraint)
        positions = pool.submit(fetch, 'netPos', NetPosition)
        polish = (pool.submit(fetch, 'DA_PL_AC', PolishAlternative)
                  if day.date >= POLISH_ALTERNATIVE_PUBLICATION_START else None)
        frame = cnec_attribution.context(
            day, alpha.result(), allocation.result(), positions.result(),
            polish.result() if polish is not None else [],
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
