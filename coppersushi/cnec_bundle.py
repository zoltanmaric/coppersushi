"""Pure conversion from validated market inputs to the browser's day contract."""
import math
from collections.abc import Sequence
from pandera.typing import DataFrame
from coppersushi import cnec_market, cnec_price_map, market
from coppersushi.cnec_page import Day
from coppersushi.data_model.cnec_bundle import DayBundle, ZoneGeometry, ElementGeometry, BindingRow, CountryCap, MarketInterval
from coppersushi.data_model.cnec_price_map import MappedCnecElements
from coppersushi.market_day import MARKET_TZ


def finite(value: float) -> float | None:
    return float(value) if math.isfinite(value) else None


def build(day: Day, geometries: dict[int, DataFrame[MappedCnecElements]]) -> DayBundle:
    """Preserve unavailable attribution; never replace missing coefficients with zero."""
    times = day.market_day.market_time_units()
    zones = []
    for row in day.zones.itertuples():
        centre = row.geometry.representative_point()
        zones.append(ZoneGeometry(zone=row.zone, name=market.ZONE_NAMES[row.zone],
            rings=[list(ring.coords) for ring in cnec_price_map._country_rings(row.geometry)],
            centre=(centre.x, centre.y)))
    elements: dict[str, ElementGeometry] = {}
    intervals = []
    for index, geometry in geometries.items():
        timestamp = times[index]
        view = cnec_market.snapshot(day.constraints, day.ptdfs, day.prices, timestamp, context=day.context)
        located = {(r.eic, r.tso, r.name): r for r in geometry.itertuples()}
        rows = []
        for row in view.constraints.itertuples():
            mapped = located.get((row.eic, row.tso, row.name))
            key = None
            if mapped is not None and mapped.match_status == 'matched':
                element = ElementGeometry(branch_id=mapped.branch_id,
                    kind='transformer' if mapped.element_type in cnec_price_map.POINT_TYPES else 'line',
                    endpoints=((mapped.x0, mapped.y0), (mapped.x1, mapped.y1)))
                # Compact references while retaining direction changes across publications.
                existing = next((k for k, v in elements.items() if v == element), None)
                key = existing if existing is not None else str(len(elements))
                elements[key] = element
            ptdfs = day.ptdfs[day.ptdfs.source_id.eq(row.source_id) & day.ptdfs.interval.eq(timestamp)]
            rows.append(BindingRow(source_id=row.source_id, name=row.name, direction=row.direction,
                contingency=None if not isinstance(row.cont_name, str) else row.cont_name,
                shadow_price=row.shadow_price, ram=finite(row.ram), capacity=finite(row.capacity),
                geometry=key, ptdfs=dict(zip(ptdfs.zone, ptdfs.ptdf))))
        context = None if day.context is None else day.context[day.context.interval.eq(timestamp)]
        alpha = finite(context.alpha.iloc[0]) if context is not None and len(context) == 1 else None
        intervals.append(MarketInterval(index=index, label=timestamp.tz_convert(MARKET_TZ).strftime('%a %d %b %Y · %H:%M %Z'),
            prices=dict(zip(view.prices.zone, view.prices.price)), constraints=rows, alpha=alpha,
            caps=[CountryCap.model_validate({k: getattr(r, k) for k in CountryCap.model_fields}) for r in view.caps.itertuples()],
            notes=list(view.notes)))
    return DayBundle(day=day.market_day.date, labels=[t.tz_convert(MARKET_TZ).strftime('%a %d %b %Y · %H:%M %Z') for t in times], zones=zones, elements=elements, intervals=intervals,
                     price_range=cnec_market.daily_price_range(day.prices))
