from dataclasses import replace
import logging
from time import perf_counter
from typing import Any, NamedTuple
from collections.abc import Callable
from functools import partial
import os
from pathlib import Path

import pandas as pd
from pandera.typing import DataFrame

import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output, State, Patch, ctx, no_update
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate

from coppersushi import cnec_geometry, cnec_page, map_style, power_flow
from coppersushi.data_model.cnec_price_map import MappedCnecElements
from coppersushi.data_model.cnec_attribution import AttributionPayload, AttributionFailure, attribution_to_browser, attribution_from_browser
from coppersushi.data_sources import opf_bundle, zone_shapes, credentials, virtual_attribution, cnec_attribution as attribution_source, electricity_maps, jao, mapbox_styles, networks, osm_locator
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

CNEC_ROUTE = 'cnec'  # /cnec, or /cnec/<delivery day> to open on one day
_cache: dict[str, tuple[go.Figure, pd.Index]] = {}
_zones: dict[str, pd.DataFrame] = {}
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


def core_zones() -> pd.DataFrame:
    """The Core bidding zones' polygons from the bundled outline shelf."""
    if 'core' not in _zones:
        _zones['core'] = zone_shapes.load()
    return _zones['core']


def cnec_geometries(day: cnec_page.Day, interval_index: int) -> DataFrame[MappedCnecElements]:
    """Resolve the viewed interval before drawing; new endpoints must be visible immediately."""
    intervals = day.market_day.market_time_units()
    interval = intervals[min(max(interval_index, 0), len(intervals) - 1)]
    required = day.constraints[day.constraints.interval.eq(interval)]
    ends = timed("endpoints", jao.load_element_ends, interval, required)
    return timed("locate", cnec_geometry.locate_elements,
        ends, timed("locator_read", osm_locator.read_csvs), osm_locator.load_aliases(),
    )


def cnec_day(day: MarketDay) -> cnec_page.Day:
    """One delivery day's inputs, fetching the day's own feeds on first use."""
    if day not in _cnec_days:
        active = timed("constraints", jao.load_active_day, day.date.isoformat())
        _cnec_days[day] = cnec_page.Day(
            market_day=day,
            zones=timed("zone_shapes", core_zones),
            constraints=active.constraints,
            ptdfs=active.ptdfs,
            external_constraints=active.external_constraints,
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
    if is_cnec_path(pathname):
        return html.Div([navigation(), cnec_page.layout(cnec_day_from_path(pathname), mapbox_token())])
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


class CnecRender(NamedTuple):
    view: cnec_page.Rendered | None
    error: str = ''


def render_cnec(day: MarketDay, interval_index: int, selected: str | None, attribution: AttributionPayload | None = None) -> CnecRender:
    """The CNEC page's map and controls for one day; a failed load becomes the banner."""
    try:
        inputs = timed("day_inputs", cnec_day, day)
        if attribution is not None:
            inputs = replace(inputs, context=attribution_from_browser(attribution))
        intervals = inputs.market_day.market_time_units()
        interval = intervals[min(max(interval_index or 0, 0), len(intervals) - 1)]
        chosen = inputs.external_constraints[
            inputs.external_constraints.source_id.astype(str).eq(str(selected))
            & inputs.external_constraints.interval.eq(interval)]
        if len(chosen) == 1:
            inputs = replace(inputs, adjacent=timed("adjacent_attribution", virtual_attribution.load_interval, day.date.isoformat(), interval, chosen.hub.iloc[0]))
        rendered = timed("figure", cnec_page.render,
            inputs, cnec_geometries(inputs, interval_index or 0),
            interval_index or 0, selected, mapbox_token=mapbox_token(), basemap=timed("basemap", basemap)
        )
    except Exception as e:  # noqa: BLE001 — every loader failure must reach the page
        logging.exception('Loading the CNEC day %s failed', day)
        return CnecRender(None, f'Could not load {day.date.isoformat()}: {e}')
    return CnecRender(rendered)


def cnec_outputs(result: CnecRender) -> tuple:
    """Convert a render result to the map/control outputs at the Dash boundary."""
    view = result.view
    if view is None:
        return (no_update,) * 6 + (result.error, True) + (no_update,) * 4
    return (
        view.figure, view.interval_max, view.interval_marks, view.interval_value,
        view.constraint_options, view.constraint_value, '', False,
        f'Reference: {view.reference or "unavailable"}',
        view.interval_value == 0, view.interval_value == view.interval_max, None,
    )


@app.callback(
    Output('cnec-active-ready', 'data'),
    Input('cnec-date', 'value'))
def load_cnec_constraints(day: str) -> dict:
    try:
        _cnec_days.pop(MarketDay.on(day), None)
        timed("constraints_load", jao.load_active_day, day)
        return {'day': day}
    except Exception as error:
        logging.exception('Loading CNEC constraints for %s failed', day)
        return {'day': day, 'error': str(error)}


@app.callback(
    Output('cnec-prices-ready', 'data'),
    Input('cnec-active-ready', 'data'),
    State('cnec-date', 'value'))
def load_cnec_prices(active: dict | None, day: str) -> dict:
    if not active or active['day'] != day:
        raise PreventUpdate
    if 'error' in active:
        return active
    try:
        timed("prices_load", electricity_maps.load_day, day)
        return active
    except Exception as error:
        logging.exception('Loading CNEC prices for %s failed', day)
        return {**active, 'error': str(error)}


app.clientside_callback(
    """function(day, active, prices) {
        if (!active || active.day !== day) return 'Loading binding constraints…';
        if (!prices || prices.day !== day) return 'Loading prices for the 12 Core zones…';
        return 'Locating binding lines and drawing the map…';
    }""",
    Output('cnec-progress', 'children'),
    Input('cnec-date', 'value'),
    Input('cnec-active-ready', 'data'),
    Input('cnec-prices-ready', 'data'))


CNEC_OUTPUTS = [
    ('cnec-map', 'figure'), ('cnec-interval', 'max'), ('cnec-interval', 'marks'),
    ('cnec-interval', 'value'), ('cnec-constraint', 'options'), ('cnec-constraint', 'value'),
    ('cnec-status', 'children'), ('cnec-status', 'is_open'),
    ('cnec-reference-zone', 'children'), ('cnec-previous', 'disabled'),
    ('cnec-next', 'disabled'), ('cnec-map', 'clickData'),
]


@app.callback(
    [Output(*output) for output in CNEC_OUTPUTS] + [Output('cnec-view-day', 'data'),
                                                        Output('cnec-attribution-status', 'children')],
    Input('cnec-prices-ready', 'data'),
    State('cnec-date', 'value'))
def open_cnec(ready: dict[str, Any] | None, day: str) -> tuple:
    token = {'day': day}
    if not ready or ready.get('day') != day:
        raise PreventUpdate
    if 'error' in ready:
        return (*cnec_outputs(CnecRender(None, f"Could not load {day}: {ready['error']}")), no_update, no_update)
    result = render_cnec(MarketDay.on(day), 0, None)
    loaded = result.view is not None
    return (*cnec_outputs(result), token if loaded else no_update,
            'Loading country caps and price contributions…' if loaded else no_update)


@app.callback(
    [Output(*output, allow_duplicate=True) for output in CNEC_OUTPUTS],
    Input('cnec-map', 'clickData'),
    Input('cnec-previous', 'n_clicks'),
    Input('cnec-next', 'n_clicks'),
    Input('cnec-interval', 'value'),
    Input('cnec-constraint', 'value'),
    State('cnec-attribution-ready', 'data'),
    State('cnec-date', 'value'),
    State('cnec-prices-ready', 'data'),
    State('cnec-constraint', 'options'),
    State('cnec-view-day', 'data'),
    prevent_initial_call=True)
def update_cnec(click: dict | None, previous: int | None, next_: int | None,
                interval_index: int | None, selected: str | None, attribution: dict | None,
                day: str, ready: dict | None, options: list[dict] | None,
                viewed_day: dict | None) -> tuple:
    token = {'day': day}
    if (viewed_day != token or not ready or 'error' in ready
            or ready.get('day') != day):
        raise PreventUpdate
    delivery = MarketDay.on(day)
    enrichment = attribution if attribution and attribution.get('day') == day else None
    if ctx.triggered_id == 'cnec-map':
        if not click:
            raise PreventUpdate
        selected = cnec_page.clicked_selection(click, options or [], selected)
    elif ctx.triggered_id == 'cnec-previous':
        interval_index = cnec_page.advance_interval(delivery, interval_index or 0, -1)
    elif ctx.triggered_id == 'cnec-next':
        interval_index = cnec_page.advance_interval(delivery, interval_index or 0, 1)
    payload = AttributionPayload.model_validate(enrichment) if enrichment and enrichment.get('rows') is not None else None
    return cnec_outputs(render_cnec(delivery, interval_index or 0, selected, payload))


@app.callback(
    Output('cnec-attribution-ready', 'data'),
    Input('cnec-view-day', 'data'),
    State('cnec-date', 'value'))
def load_cnec_attribution(viewed: dict | None, day: str) -> dict:
    """Start enrichment only after the base map has reached the browser."""
    token = {'day': day}
    if viewed != token:
        raise PreventUpdate
    delivery = MarketDay.on(day)
    try:
        frame = timed('attribution', attribution_source.load_day, delivery)
        return attribution_to_browser(frame, delivery).model_dump(mode="json")
    except Exception as error:
        logging.exception('Loading CNEC attribution for %s failed', day)
        return AttributionFailure(day=delivery.date, error=f'Attribution failed: {error}').model_dump(mode='json')


@app.callback(
    Output('cnec-enriched-view', 'data'),
    Input('cnec-attribution-ready', 'data'),
    State('cnec-date', 'value'),
    State('cnec-interval', 'value'),
    State('cnec-constraint', 'value'),
    State('cnec-view-day', 'data'),
    prevent_initial_call=True)
def enrich_cnec(attribution: dict | None, day: str, interval_index: int,
                selected: str | None, viewed: dict | None) -> dict:
    """Keep navigation independent of the pending attribution request."""
    token = {'day': day}
    if (viewed != token or not attribution or attribution.get('rows') is None
            or attribution.get('day') != day):
        raise PreventUpdate
    result = render_cnec(MarketDay.on(day), interval_index, selected, AttributionPayload.model_validate(attribution))
    view = result.view
    if view is None:
        return {**token, 'interval': interval_index, 'selected': selected,
                'error': result.error}
    return {**token, 'interval': interval_index, 'selected': selected,
            'figure': view.figure, 'options': view.constraint_options,
            'reference': f'Reference: {view.reference or "unavailable"}'}


app.clientside_callback(
    """function(view, day, interval, selected) {
        const unchanged = [window.dash_clientside.no_update, window.dash_clientside.no_update,
                           window.dash_clientside.no_update, window.dash_clientside.no_update,
                           window.dash_clientside.no_update];
        if (!view || view.day !== day ||
            view.interval !== interval || view.selected !== selected) return unchanged;
        if (view.error) return [...unchanged.slice(0, 3), view.error, true];
        return [view.figure, view.options, view.reference, '', false];
    }""",
    Output('cnec-map', 'figure', allow_duplicate=True),
    Output('cnec-constraint', 'options', allow_duplicate=True),
    Output('cnec-reference-zone', 'children', allow_duplicate=True),
    Output('cnec-status', 'children', allow_duplicate=True),
    Output('cnec-status', 'is_open', allow_duplicate=True),
    Input('cnec-enriched-view', 'data'),
    State('cnec-date', 'value'),
    State('cnec-interval', 'value'),
    State('cnec-constraint', 'value'),
    prevent_initial_call=True)


app.clientside_callback(
    """function(attribution, day) {
        if (!attribution || attribution.day !== day)
            return window.dash_clientside.no_update;
        if (attribution.error) return attribution.error;
        return attribution.complete ? '' : 'Source data is missing for some intervals; affected contributions are unavailable.';
    }""",
    Output('cnec-attribution-status', 'children', allow_duplicate=True),
    Input('cnec-attribution-ready', 'data'),
    State('cnec-date', 'value'),
    prevent_initial_call=True)


if __name__ == '__main__':
    app.run(debug=True)
