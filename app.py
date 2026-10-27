from dataclasses import replace
import logging
import os
from pathlib import Path

import pandas as pd

import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output, State, ctx, no_update
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate

from coppersushi import cnec_geometry, cnec_page, map_style, power_flow
from coppersushi.data_model.cnec_price_map import MappedCnecElements
from coppersushi.data_sources import zone_shapes, credentials, virtual_attribution, cnec_attribution as attribution_source, electricity_maps, jao, mapbox_styles, networks, osm_locator
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

NETWORK_LOADERS = {
    'opf-2024': lambda: networks.load(networks.solved('2024-08-29')),
}
# Unsanctioned solves are viewable at /candidates/<file stem>
NETWORK_LOADERS.update({
    f'candidates/{path.stem}': (lambda path=path: networks.load(path))
    for path in sorted(networks.CANDIDATES_DIR.glob('*.nc'))
})
ROOT_VIEW = os.environ.get('ROOT_VIEW', 'embed')
if ROOT_VIEW not in {'embed', 'full'}:
    raise ValueError('ROOT_VIEW must be embed or full')

CNEC_ROUTE = 'cnec'  # /cnec, or /cnec/<delivery day> to open on one day
_cache: dict[str, tuple[go.Figure, pd.Index]] = {}
_zones: dict[str, pd.DataFrame] = {}
_cnec_days: dict[str, cnec_page.Day] = {}
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
            mapbox=dict(center=go.layout.mapbox.Center(lat=53, lon=9), zoom=3.9, pitch=60)
        )
        _cache[network_key] = (fig, n.snapshots)
    return _cache[network_key]


def core_zones() -> pd.DataFrame:
    """The Core bidding zones' polygons from the bundled outline shelf."""
    if 'core' not in _zones:
        _zones['core'] = zone_shapes.load()
    return _zones['core']


def cnec_geometries(day: cnec_page.Day, interval_index: int) -> MappedCnecElements:
    """Resolve the viewed interval before drawing; new endpoints must be visible immediately."""
    intervals = day.market_day.market_time_units()
    interval = intervals[min(max(interval_index, 0), len(intervals) - 1)]
    required = day.constraints[day.constraints.interval.eq(interval)]
    ends = jao.load_element_ends(interval, required)
    return cnec_geometry.locate_elements(
        ends, osm_locator.read_csvs(), osm_locator.load_aliases(),
    )


def cnec_day(day: str) -> cnec_page.Day:
    """One delivery day's inputs, fetching the day's own feeds on first use."""
    if day not in _cnec_days:
        active = jao.load_active_day(day)
        _cnec_days[day] = cnec_page.Day(
            market_day=MarketDay.on(day),
            zones=core_zones(),
            constraints=active.constraints,
            ptdfs=active.ptdfs,
            external_constraints=active.external_constraints,
            prices=electricity_maps.load_day(day),
            context=attribution_source.load_day(day),
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


def network_layout() -> html.Div:
    return html.Div([
        html.Div(id='opf-time', className='opf-time'),
        dbc.Alert(id='status', color='danger', is_open=False, style={'margin': '0 1em'}),
        dcc.Loading(
            dcc.Graph(
                id='map',
                style={'height': '100%'},
                figure=dict(layout=dict(autosize=True)),
                config=dict(responsive=True, displayModeBar=False, scrollZoom=True)
            ),
            type='circle', delay_show=300,
            parent_style={'flex': '1', 'minHeight': '0', 'position': 'relative',
                          'display': 'flex', 'flexDirection': 'column'},
            overlay_style={'visibility': 'visible', 'opacity': 0.4},
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
def show_page(pathname: str, root_view: str = ROOT_VIEW):
    if is_cnec_path(pathname):
        return html.Div([navigation(), cnec_page.layout(cnec_day_from_path(pathname), mapbox_token())])
    if network_key_from_path(pathname) is None:
        return html.Div([html.H1('Page not found'), dcc.Link('2024 OPF', href='/opf-2024')])
    return html.Div([
        *([] if is_embed_path(pathname, root_view) else [navigation()]),
        network_layout(),
    ], className='app-page')



def render(pathname: str, snapshot_index: int, slider_moved: bool) -> tuple:
    """Figure, slider state and status banner for one view; a failed load becomes the banner."""
    network_key = network_key_from_path(pathname)
    if network_key is None:
        raise PreventUpdate
    try:
        fig, snapshots = figure_for(network_key)
    except Exception as e:  # noqa: BLE001 — every loader failure must reach the page
        logging.exception('Loading %s failed', network_key)
        return no_update, no_update, no_update, no_update, no_update, f'Could not load {network_key}: {e}', True
    maximum, marks, snapshot_index, label = opf_snapshot_state(snapshots, snapshot_index, slider_moved)
    return power_flow.show_snapshot(fig, snapshot_index), maximum, marks, snapshot_index, label, '', False


def opf_snapshot_state(snapshots: pd.Index, snapshot_index: int, slider_moved: bool) -> tuple:
    """Pure local-time labels and selection, shared by normal and embedded OPF views."""
    # PyPSA stores naive snapshots as UTC; display the operating day's named zone.
    local = pd.DatetimeIndex(snapshots)
    local = local.tz_localize('UTC') if local.tz is None else local
    local = local.tz_convert(MARKET_TZ)
    if not slider_moved or not 0 <= snapshot_index < len(snapshots):
        snapshot_index = min(range(len(local)), key=lambda i: abs(local[i].hour - 12))
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
def update_figure(pathname: str, snapshot_index: int):
    return render(pathname, snapshot_index, ctx.triggered_id == 'snapshot-slider')


def render_cnec(day: str, interval_index: int, selected: str | None) -> tuple:
    """The CNEC page's map and controls for one day; a failed load becomes the banner."""
    try:
        inputs = cnec_day(day)
        intervals = inputs.market_day.market_time_units()
        interval = intervals[min(max(interval_index or 0, 0), len(intervals) - 1)]
        chosen = inputs.external_constraints[
            inputs.external_constraints.source_id.astype(str).eq(str(selected))
            & inputs.external_constraints.interval.eq(interval)]
        if len(chosen) == 1:
            inputs = replace(inputs, adjacent=virtual_attribution.load_interval(day, interval, chosen.hub.iloc[0]))
        rendered = cnec_page.render(
            inputs, cnec_geometries(inputs, interval_index or 0),
            interval_index or 0, selected, mapbox_token=mapbox_token(), basemap=basemap()
        )
    except Exception as e:  # noqa: BLE001 — every loader failure must reach the page
        logging.exception('Loading the CNEC day %s failed', day)
        return (no_update,) * 6 + (f'Could not load {day}: {e}', True) + (no_update,) * 5
    return (
        rendered.figure,
        rendered.interval_max,
        rendered.interval_marks,
        rendered.interval_value,
        rendered.constraint_options,
        rendered.constraint_value,
        '',
        False,
        f'Reference: {rendered.reference or "unavailable"}',
        rendered.interval_value == 0,
        rendered.interval_value == rendered.interval_max,
        None,
        day,
    )


@app.callback(
    Output('cnec-active-ready', 'data'),
    Input('cnec-date', 'value'),
    Input('cnec-retry', 'n_clicks'))
def load_cnec_constraints(day: str, retries: int) -> dict:
    try:
        _cnec_days.pop(day, None)
        jao.load_active_day(day)
        return {'day': day, 'request': retries}
    except Exception as error:
        logging.exception('Loading CNEC constraints for %s failed', day)
        return {'day': day, 'request': retries, 'error': str(error)}


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
        electricity_maps.load_day(day)
        return active
    except Exception as error:
        logging.exception('Loading CNEC prices for %s failed', day)
        return {**active, 'error': str(error)}


app.clientside_callback(
    """function(day, active, prices, retries) {
        if (!active || active.day !== day || active.request !== retries) return 'Loading binding constraints…';
        if (!prices || prices.day !== day || prices.request !== retries) return 'Loading prices for the 12 Core zones…';
        return 'Locating binding lines and drawing the map…';
    }""",
    Output('cnec-progress', 'children'),
    Input('cnec-date', 'value'),
    Input('cnec-active-ready', 'data'),
    Input('cnec-prices-ready', 'data'),
    Input('cnec-retry', 'n_clicks'))


@app.callback(
    Output('cnec-map', 'figure'),
    Output('cnec-interval', 'max'),
    Output('cnec-interval', 'marks'),
    Output('cnec-interval', 'value'),
    Output('cnec-constraint', 'options'),
    Output('cnec-constraint', 'value'),
    Output('cnec-status', 'children'),
    Output('cnec-status', 'is_open'),
    Output('cnec-reference-zone', 'children'),
    Output('cnec-previous', 'disabled'),
    Output('cnec-next', 'disabled'),
    Output('cnec-map', 'clickData'),
    Output('cnec-view-day', 'data'),
    Input('cnec-map', 'clickData'),
    Input('cnec-previous', 'n_clicks'),
    Input('cnec-next', 'n_clicks'),
    Input('cnec-date', 'value'),
    Input('cnec-interval', 'value'),
    Input('cnec-constraint', 'value'),
    Input('cnec-prices-ready', 'data'),
    State('cnec-constraint', 'options'),
    State('cnec-view-day', 'data'))
def update_cnec(click, previous, next_, day: str, interval_index: int, selected: str | None, ready: dict | None, options, viewed_day):
    if not ready or ready['day'] != day:
        raise PreventUpdate
    if 'error' in ready:
        return (no_update,) * 6 + (f"Could not load {day}: {ready['error']}", True) + (no_update,) * 5
    if viewed_day != day:
        interval_index, selected = 0, None
    elif ctx.triggered_id == 'cnec-map':
        if not click:
            raise PreventUpdate
        selected = cnec_page.clicked_selection(click, options or [], selected)
    elif ctx.triggered_id == 'cnec-previous':
        interval_index = cnec_page.advance_interval(MarketDay.on(day), interval_index or 0, -1)
    elif ctx.triggered_id == 'cnec-next':
        interval_index = cnec_page.advance_interval(MarketDay.on(day), interval_index or 0, 1)
    return render_cnec(day, interval_index, selected)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    app.run(debug=True)
