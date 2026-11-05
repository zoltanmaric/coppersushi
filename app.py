from dataclasses import replace
from datetime import date
from flask import redirect, request
from werkzeug.wrappers import Response
import logging
from time import perf_counter
from collections.abc import Callable
from functools import partial
import os
from pathlib import Path

import pandas as pd
from pandera.typing import DataFrame

import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output, Patch, ctx, no_update
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate

from coppersushi.cnec_component import CnecView
from coppersushi.data_model.jao import ActiveConstraints
from coppersushi import REPO, cnec_page, map_style, power_flow
from coppersushi.data_model.network_views import BiddingZoneShapes
from coppersushi.data_model.cnec_price_map import MappedCnecElements
from coppersushi.data_model.cnec_attribution import AttributionPayload, attribution_from_browser
from coppersushi.data_sources import element_catalog, opf_bundle, zone_shapes, credentials, electricity_maps, jao, mapbox_styles, networks
from coppersushi.market_day import MARKET_TZ, MarketDay

# Every page's controls live in one tree that the router swaps, so a callback whose
# components belong to the other page is simply not fired.
app = Dash(
    __name__,
    title='Copper Sushi 🍣',
    external_stylesheets=[dbc.themes.DARKLY],
    suppress_callback_exceptions=True,
)

server = app.server
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def timed[**P, R](stage: str, function: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R:
    """Report server stages under Gunicorn as well as the development server."""
    started = perf_counter()
    try:
        return function(*args, **kwargs)
    finally:
        logger.info("cnec stage=%s elapsed_ms=%.1f", stage, (perf_counter() - started) * 1000)


NETWORK_LOADERS = {
    'opf-2024': lambda: networks.load(networks.solved('2024-08-29')),
}
# Unsanctioned solves are viewable at /candidates/<file stem>
NETWORK_LOADERS.update({
    f'candidates/{path.stem}': partial(networks.load, path)
    for path in sorted(networks.CANDIDATES_DIR.glob('*.nc'))
})
ROOT_VIEW = os.environ.get('ROOT_VIEW', 'embed')
if ROOT_VIEW not in {'embed', 'full'}:
    raise ValueError('ROOT_VIEW must be embed or full')

CNEC_FIRST_DAY = date(2025, 11, 5)
CNEC_ROUTE = 'cnec'  # /cnec, or /cnec/<delivery day> to open on one day
_cache: dict[str, tuple[go.Figure, pd.Index]] = {}
_zones: dict[str, DataFrame[BiddingZoneShapes]] = {}
_cnec_days: dict[MarketDay, cnec_page.Day] = {}
_basemap: dict[str, dict] = {}


def mapbox_token() -> str:
    """From the environment (deploys) or the gitignored secrets file (README: Mapbox token)."""
    return credentials.token('MAPBOX_TOKEN', Path('.secrets/.mapbox_token'))


def basemap() -> dict:
    """Mapbox's dark style without its labels, fetched once per process."""
    if 'dark' not in _basemap:
        _basemap['dark'] = map_style.without_labels(mapbox_styles.fetch(mapbox_token()))
    return _basemap['dark']


def figure_for(network_key: str) -> tuple[go.Figure, pd.Index]:
    if network_key not in _cache:
        n = NETWORK_LOADERS[network_key]()
        fig = power_flow.colored_network_figure(n, 'net_power', mapbox_token())
        fig.update_layout(
            mapbox=map_style.OPF_CAMERA
        )
        _cache[network_key] = (fig, n.snapshots)
    return _cache[network_key]


def core_zones() -> DataFrame[BiddingZoneShapes]:
    """The Core bidding zones' polygons from the bundled outline shelf."""
    if 'core' not in _zones:
        _zones['core'] = zone_shapes.load()
    return _zones['core']


def cnec_geometries(day: cnec_page.Day, interval_index: int) -> DataFrame[MappedCnecElements]:
    """Resolve the viewed interval before drawing; new endpoints must be visible immediately."""
    intervals = day.market_day.market_time_units()
    interval = intervals[min(max(interval_index, 0), len(intervals) - 1)]
    required = day.constraints[day.constraints.interval.eq(interval)]
    return locate_constraints(interval, required)


def locate_constraints(interval: pd.Timestamp, required: DataFrame[ActiveConstraints]) -> DataFrame[MappedCnecElements]:
    """Resolve one interval without waiting for prices or attribution."""
    catalog = Path(os.environ.get("COPPERSUSHI_ELEMENT_CATALOG", str(REPO / "data/element-catalog")))
    return timed("catalog", element_catalog.resolve, interval, required, catalog)


def cnec_day(day: MarketDay) -> cnec_page.Day:
    """One delivery day's inputs, fetching the day's own feeds on first use."""
    if day not in _cnec_days:
        active = timed("constraints", jao.load_active_day, day.date.isoformat())
        _cnec_days[day] = cnec_page.Day(
            market_day=day,
            zones=timed("zone_shapes", core_zones),
            constraints=active.constraints,
            ptdfs=active.ptdfs,
            prices=timed("prices", electricity_maps.load_day, day.date.isoformat()),
        )
    return _cnec_days[day]


def network_key_from_path(pathname: str) -> str | None:
    key = (pathname or '').strip('/')
    if key in {'', 'embed/opf-2024'}:
        return 'opf-2024'
    return key if key in NETWORK_LOADERS else None


def is_embed_path(pathname: str, root_view: str = ROOT_VIEW) -> bool:
    key = (pathname or '').strip('/')
    return key == 'embed/opf-2024' or (not key and root_view == 'embed')


def navigation() -> html.Nav:
    return html.Nav([
        dcc.Link('2024 OPF on the 2025 grid', href='/opf-2024'),
        dcc.Link('Prices and binding CNECs', href=f'/{CNEC_ROUTE}'),
    ], className='app-navigation')


def cnec_day_from_path(pathname: str) -> str | None:
    """The delivery day a `/cnec/<day>` path opens on, or None when it names no day."""
    parts = (pathname or '').strip('/').split('/')
    return parts[1] if len(parts) > 1 and parts[0] == CNEC_ROUTE else None



def unsupported_cnec_path(pathname: str) -> bool:
    day = cnec_day_from_path(pathname)
    try:
        return day is not None and date.fromisoformat(day) < CNEC_FIRST_DAY
    except ValueError:
        return False


@server.before_request
def redirect_unsupported_cnec_day() -> Response | None:
    if request.method == 'GET' and unsupported_cnec_path(request.path):
        return redirect('/cnec')
    return None

def is_cnec_path(pathname: str) -> bool:
    return (pathname or '').strip('/').split('/')[0] == CNEC_ROUTE


def network_layout(token: str | None = None) -> html.Div:
    return html.Div([
        html.Div(id='opf-time', className='opf-time'),
        dbc.Alert(id='status', color='danger', is_open=False, style={'margin': '0 1em'}),
        dcc.Loading(
            dcc.Graph(
                id='map',
                style={'height': '100%'},
                figure=dict(
                    data=[dict(type='scattermapbox', lon=[None], lat=[None], hoverinfo='skip')],
                    layout=dict(
                        autosize=True, uirevision=True, showlegend=False, hovermode='closest',
                        mapbox=dict(style=map_style.MAP_STYLE, accesstoken=token, **map_style.OPF_CAMERA),
                        margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor='#111',
                    ),
                ),
                config=dict(responsive=True, displayModeBar=False, scrollZoom=True)
            ),
            custom_spinner=html.Div('Loading network…', className='opf-loading', role='status'),
            delay_show=300,
            parent_style={'flex': '1', 'minHeight': '0', 'position': 'relative',
                          'display': 'flex', 'flexDirection': 'column'},
            overlay_style={'visibility': 'visible'},
        ),
        html.Div(
            dcc.Slider(
                0, 1, step=1, value=0,
                id='snapshot-slider', allow_direct_input=False
            ),
            className='opf-slider',
        )
    ], className='opf-view')


app.layout = html.Div([
    dcc.Location(id='url'),
    html.Div(id='page'),
])


@app.callback(Output('page', 'children'), Input('url', 'pathname'))
def show_page(pathname: str, root_view: str = ROOT_VIEW) -> html.Div:
    if unsupported_cnec_path(pathname):
        return html.Div(dcc.Location(id='cnec-redirect', href='/cnec', refresh=True))
    if is_cnec_path(pathname):
        return html.Div([navigation(), CnecView(id='cnec-view', day=cnec_day_from_path(pathname) or cnec_page.local_today(), min_day=CNEC_FIRST_DAY.isoformat(), token=mapbox_token(), basemap=basemap())])
    if network_key_from_path(pathname) is None:
        return html.Div([html.H1('Page not found'), dcc.Link('2024 OPF', href='/opf-2024')])
    return html.Div([
        *([] if is_embed_path(pathname, root_view) else [navigation()]),
        network_layout(mapbox_token()),
    ], className='app-page')



def render(pathname: str, snapshot_index: int, slider_moved: bool) -> tuple:
    """Figure, slider state and status banner for one view; a failed load becomes the banner."""
    network_key = network_key_from_path(pathname)
    if network_key is None:
        raise PreventUpdate
    try:
        snapshots: pd.Index | None = opf_bundle.snapshots() if network_key == 'opf-2024' else None
        if snapshots is None:
            fig, snapshots = figure_for(network_key)
            state = opf_snapshot_state(snapshots, snapshot_index, slider_moved)
            selected = power_flow.show_snapshot(fig, state[2])
        else:
            state = opf_snapshot_state(snapshots, snapshot_index, slider_moved)
            selected = opf_bundle.load(state[2], mapbox_token())
    except Exception as e:  # noqa: BLE001 — every loader failure must reach the page
        logging.exception('Loading %s failed', network_key)
        return no_update, no_update, no_update, no_update, no_update, f'Could not load {network_key}: {e}', True
    maximum, marks, snapshot_index, label = state
    # The page owns the layout; loading an hour only replaces network traces.
    update = Patch()
    update['data'] = selected.to_plotly_json()['data']
    return update, maximum, marks, snapshot_index, label, '', False


def opf_snapshot_state(snapshots: pd.Index, snapshot_index: int, slider_moved: bool) -> tuple:
    """Pure local-time labels and selection, shared by normal and embedded OPF views."""
    # PyPSA stores naive snapshots as UTC; display the operating day's named zone.
    local = pd.DatetimeIndex(snapshots)
    local = local.tz_localize('UTC') if local.tz is None else local
    local = local.tz_convert(MARKET_TZ)
    if not slider_moved or not 0 <= snapshot_index < len(snapshots):
        snapshot_index = min(enumerate(local), key=lambda item: abs(item[1].hour - 12))[0]
    marks = {
        idx: dict(label=snapshot.strftime('%H:%M')
                  if snapshot.hour % 4 == 0 or idx == len(local) - 1 else ' ')
        for idx, snapshot in enumerate(local)
    }
    label = local[snapshot_index].strftime('%d %b %Y · %H:%M %Z')
    return len(snapshots) - 1, marks, snapshot_index, label



@app.callback(
    Output('map', 'figure'),
    Output('snapshot-slider', 'max'),
    Output('snapshot-slider', 'marks'),
    Output('snapshot-slider', 'value'),
    Output('opf-time', 'children'),
    Output('status', 'children'),
    Output('status', 'is_open'),
    Input('url', 'pathname'),
    Input('snapshot-slider', 'value'))
def update_figure(pathname: str, snapshot_index: int) -> tuple:
    return render(pathname, snapshot_index, ctx.triggered_id == 'snapshot-slider')


def render_cnec(day: MarketDay, interval_index: int, selected: str | None, attribution: AttributionPayload | None = None) -> cnec_page.Rendered:
    """Load and render one CNEC view; the HTTP boundary handles failures."""
    inputs = timed("day_inputs", cnec_day, day)
    if attribution is not None:
        inputs = replace(inputs, context=attribution_from_browser(attribution))
    return timed("figure", cnec_page.render,
        inputs, cnec_geometries(inputs, interval_index),
        interval_index, selected, mapbox_token=mapbox_token(), basemap=timed("basemap", basemap)
    )


# HTTP requests and React own CNEC coordination; Dash still owns OPF callbacks.
import cnec_http
from coppersushi.data_model.cnec_api import EnrichedRequest


def enriched_view(view: EnrichedRequest) -> cnec_page.Rendered:
    return render_cnec(MarketDay.on(view.day), view.interval,
                        None if view.selected is None else str(view.selected), view.attribution)


cnec_http.register(server, cnec_http.Services(core_zones, mapbox_token, basemap,
                                            locate_constraints, enriched_view))


if __name__ == '__main__':
    app.run(debug=True)
