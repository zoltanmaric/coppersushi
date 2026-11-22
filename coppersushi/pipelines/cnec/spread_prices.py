"""Recover missing zonal prices from JAO's signed B-minus-A price spreads."""
from collections import defaultdict, deque
from decimal import Decimal
from typing import NamedTuple

import pandas as pd
from pandera.typing import DataFrame
from pydantic import AwareDatetime, TypeAdapter

from coppersushi.pipelines.cnec.prices import IncompletePrices
from coppersushi.pipelines.data_model.market import DayAheadPrices

SOURCE = "Derived from JAO border price spreads"
_timestamp = TypeAdapter(AwareDatetime)


class BorderSpread(NamedTuple):
    origin: str
    destination: str
    difference: Decimal


def parse_spreads(rows: list[dict], zones: tuple[str, ...]) -> dict[pd.Timestamp, list[BorderSpread]]:
    """Read only Core borders. A null spread supplies no price relationship."""
    intervals = {}
    for row in rows:
        time = pd.to_datetime(_timestamp.validate_python(row["dateTimeUtc"]), utc=True)
        if time in intervals:
            raise ValueError(f"Duplicate JAO price spread interval {time}")
        borders = []
        for key, value in row.items():
            match key.split("_"):
                case ["border", a, b] if a in zones and b in zones and value is not None:
                    difference = Decimal(str(value))
                    if not difference.is_finite():
                        raise ValueError(f"Invalid {key} price spread at {time}")
                    borders.append(BorderSpread(a, b, difference))
        intervals[time] = borders
    return intervals


def recover(prices: DataFrame[DayAheadPrices], times: pd.DatetimeIndex, zones: tuple[str, ...],
            spreads: dict[pd.Timestamp, list[BorderSpread]]) -> DataFrame[DayAheadPrices]:
    """Propagate known prices through missing zones, checking every alternative path."""
    derived = []
    observed_at = pd.Timestamp.now(tz="UTC")
    for time in times:
        direct = prices[prices.interval.eq(time)]
        known = {zone: Decimal(str(price)) for zone, price in zip(direct.zone, direct.price)}
        missing = set(zones).difference(known)
        if not missing:
            continue
        edges: dict[str, list[tuple[str, Decimal]]] = defaultdict(list)
        for a, b, difference in spreads.get(time, []):
            if a in missing or b in missing:
                edges[a].append((b, difference))
                edges[b].append((a, -difference))
        pending = deque(known)
        while pending:
            origin = pending.popleft()
            for destination, difference in edges[origin]:
                candidate = known[origin] + difference
                if destination in known:
                    if known[destination] != candidate:
                        raise IncompletePrices(f"Conflicting JAO spreads for {origin}/{destination} at {time}")
                else:
                    known[destination] = candidate
                    pending.append(destination)
        for zone in sorted(missing):
            if zone not in known:
                raise IncompletePrices(f"No anchored JAO spread for {zone} at {time}")
            derived.append(dict(interval=time, zone=zone, price=float(known[zone]), unit="EUR/MWh",
                                source=SOURCE, updated_at=observed_at))
    return pd.concat([prices, pd.DataFrame(derived)], ignore_index=True).sort_values(
        ["interval", "zone"], ignore_index=True).pipe(DayAheadPrices.validate)
