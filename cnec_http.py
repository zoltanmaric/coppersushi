"""Flask boundary for independently loaded CNEC layers; domain functions keep typed inputs."""

import json
import logging
from time import perf_counter
from collections.abc import Callable
from functools import wraps
from dataclasses import dataclass
from typing import Any
import plotly.graph_objects as go
from pandera.typing import DataFrame
from werkzeug.exceptions import BadRequest, HTTPException
from coppersushi.data_model.network_views import BiddingZoneShapes
from coppersushi.data_model.jao import ActiveConstraints
from coppersushi.data_model.cnec_price_map import MappedCnecElements
from coppersushi.data_model.cnec_attribution import AttributionPayload
from typing import ParamSpec, TypeVar

import pandas as pd
from flask import Blueprint, Flask, Response, request
from pydantic import BaseModel, ValidationError
from plotly.utils import PlotlyJSONEncoder

from coppersushi import cnec_page, cnec_price_map
from coppersushi.data_model.cnec_api import (
    ApiError, DayResponse, EnrichedRequest, LayerResponse, PlotlyFigure, ViewRequest,
)
from coppersushi.data_model.cnec_attribution import attribution_to_browser
from coppersushi.data_model.market import ZonalPrices
from coppersushi.data_sources import cnec_attribution, electricity_maps, jao
from coppersushi.market_day import MARKET_TZ, MarketDay

P = ParamSpec('P')
R = TypeVar('R', bound=BaseModel)
logger = logging.getLogger(__name__)


def json_endpoint(function: Callable[P, R]) -> Callable[P, Response]:
    @wraps(function)
    def respond(*args: P.args, **kwargs: P.kwargs) -> Response:
        started = perf_counter()
        try:
            payload: BaseModel = function(*args, **kwargs)
            status = 200
        except HTTPException as error:
            payload = ApiError(error=str(error))
            status = error.code or 500
        except Exception as error:
            logger.exception('CNEC request failed')
            payload = ApiError(error=str(error))
            status = 500
        logger.info('cnec endpoint=%s status=%s elapsed_ms=%.1f', request.path, status, (perf_counter() - started) * 1000)
        return Response(payload.model_dump_json(), status=status, mimetype='application/json',
                        headers={'Cache-Control': 'no-store'})
    return respond


def view_interval(view: ViewRequest) -> pd.Timestamp:
    intervals = MarketDay.on(view.day).market_time_units()
    if view.interval >= len(intervals):
        raise BadRequest('Interval is outside the selected market day')
    return intervals[view.interval]


def figure_payload(figure: go.Figure) -> PlotlyFigure:
    # Plotly owns the extensible nested schema and encodes numpy arrays/timestamps.
    return PlotlyFigure.model_validate_json(json.dumps(figure.to_plotly_json(), cls=PlotlyJSONEncoder))


@dataclass(frozen=True)
class Services:
    """Typed application operations shared by the independent HTTP layer handlers."""
    core_zones: Callable[[], DataFrame[BiddingZoneShapes]]
    mapbox_token: Callable[[], str]
    basemap: Callable[[], dict[str, Any]]
    locate_constraints: Callable[[pd.Timestamp, DataFrame[ActiveConstraints]], DataFrame[MappedCnecElements]]
    render: Callable[[EnrichedRequest], cnec_page.Rendered]


def parse[T: BaseModel](model: type[T], value: object) -> T:
    """Invalid client input is 400; publisher/model failures remain server errors."""
    try:
        return model.model_validate(value)
    except ValidationError as error:
        raise BadRequest(str(error)) from error


def register(server: Flask, services: Services) -> None:
    """Bind existing application services without changing OPF callback behavior."""
    @server.get('/data/cnec/v1/<day>/manifest.json')
    def unpublished(day: str):
        return Response(status=404)

    @server.get('/api/cnec/bundle/<day>')
    @json_endpoint
    def bundle(day: str):
        from coppersushi.data_sources import cnec_bundles
        parsed = parse(ViewRequest, {'day': day, 'interval': 0, 'selected': None})
        delivery = MarketDay.on(parsed.day)
        requested = request.args.get('interval')
        try:
            indices = None if requested is None else [int(requested)]
        except ValueError as error:
            raise BadRequest('Invalid interval') from error
        if indices is not None and any(i < 0 or i >= len(delivery.market_time_units()) for i in indices):
            raise BadRequest('Interval is outside the selected market day')
        return cnec_bundles.prepare(delivery, indices)

    api = Blueprint('cnec_api', __name__, url_prefix='/api/cnec')

    @api.get('/day/<day>')
    @json_endpoint
    def day_labels(day: str) -> DayResponse:
        parsed = parse(ViewRequest, {'day': day, 'interval': 0, 'selected': None})
        return DayResponse(day=parsed.day, labels=[
            t.tz_convert(MARKET_TZ).strftime('%a %d %b %Y · %H:%M %Z')
            for t in MarketDay.on(parsed.day).market_time_units()])

    @api.post('/prices')
    @json_endpoint
    def prices() -> LayerResponse:
        view = parse(ViewRequest, request.get_json())
        interval = view_interval(view)
        frame = electricity_maps.load_day(view.day.isoformat())
        figure = cnec_price_map.price_figure(services.core_zones(),
            ZonalPrices.validate(frame), interval,
            services.mapbox_token(), services.basemap())
        return LayerResponse(request=view, figure=figure_payload(figure), options=[], reference=None, notes=[])

    @api.post('/constraints')
    @json_endpoint
    def constraints() -> LayerResponse:
        view = parse(ViewRequest, request.get_json())
        interval = view_interval(view)
        active = jao.load_active_day(view.day.isoformat())
        rows = active.constraints[active.constraints.interval.eq(interval)]
        geometry = services.locate_constraints(interval, rows)
        figure = cnec_price_map.constraint_figure(services.core_zones(), rows,
            geometry, interval, view.selected, services.mapbox_token(), services.basemap())
        options = cnec_page.constraint_options(rows.assign(option_source="constraints"))
        return LayerResponse.model_validate(dict(request=view, figure=figure_payload(figure),
                                                 options=options, reference=None, notes=[]))

    @api.get('/attribution/<day>')
    @json_endpoint
    def attribution(day: str) -> AttributionPayload:
        view = parse(ViewRequest, {'day': day, 'interval': 0, 'selected': None})
        delivery = MarketDay.on(view.day)
        return attribution_to_browser(cnec_attribution.load_day(delivery), delivery)

    @api.post('/enriched')
    @json_endpoint
    def enriched() -> LayerResponse:
        view = parse(EnrichedRequest, request.get_json())
        view_interval(view)
        if view.attribution.day != view.day:
            raise BadRequest('Attribution belongs to another market day')
        result = services.render(view)
        return LayerResponse.model_validate(dict(
            request=ViewRequest(day=view.day, interval=view.interval, selected=view.selected, reference=view.reference),
            figure=figure_payload(result.figure), options=result.constraint_options,
            reference=result.reference, notes=list(result.notes)))

    server.register_blueprint(api)
