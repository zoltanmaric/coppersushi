import logging
import os
from pathlib import Path

import pandas as pd

import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output, ctx, no_update
import dash_bootstrap_components as dbc

from coppersushi import bidding_zones, cnec_geometry, cnec_page, map_style, power_flow
from coppersushi.data_model.cnec_price_map import MappedCnecElements
from coppersushi.data_sources import electricity_maps, jao, mapbox_styles, networks, osm_locator
from coppersushi.market_day import MarketDay

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
    'v1': lambda: networks.load(networks.NETWORKS_DIR / 'opf-2013-07-17-v1.nc'),
    'opf-2013': lambda: networks.load(networks.solved('2013-07-17')),
    'opf-2024': lambda: networks.load(networks.solved('2024-08-29')),
}
# Unsanctioned solves are viewable at /candidates/<file stem>
NETWORK_LOADERS.update({
    f'candidates/{path.stem}': (lambda path=path: networks.load(path))
    for path in sorted(networks.CANDIDATES_DIR.glob('*.nc'))
})
CNEC_ROUTE = 'cnec'  # /cnec, or /cnec/<delivery day> to open on one day
ZONE_SHAPES_FROM = '2024-08-29'  # Any solved network carries the same country polygons
_cache: dict[str, tuple[go.Figure, pd.Index]] = {}
_zones: dict[str, pd.DataFrame] = {}
_geometries: dict[str, MappedCnecElements] = {}
_geometry_generation: tuple[tuple[str, str], ...] | None = None
_cnec_days: dict[str, cnec_page.Day] = {}
_basemap: dict[str, dict] = {}


def mapbox_token() -> str:
    """From the environment (deploys) or the gitignored secrets file (README: Mapbox token)."""
    return os.environ.get('MAPBOX_TOKEN') or Path('.secrets/.mapbox_token').read_text().strip()


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
    """The Core bidding zones' polygons, read off a solved network's country shapes."""
    if 'core' not in _zones:
        shapes = networks.load(networks.solved(ZONE_SHAPES_FROM)).shapes
        _zones['core'] = bidding_zones.core_zone_shapes(shapes)
    return _zones['core']


def cnec_geometries(required_day: str | None = None) -> MappedCnecElements:
    """Element geometry from every cached JAO domain day, not from the day on screen.

    Which substations an element joins does not change by delivery day, while the domain
    feed for the next day is published hours before its auction clears. Building geometry
    from whatever days are cached therefore lets a day whose own domain feed is absent
    still draw its binding elements. Where cached days disagree, the latest day's ends win.
    """
    global _geometry_generation
    requested = None
    if required_day and not jao.domain_generation(required_day):
        requested = jao.load_day(required_day)
    days = sorted(day.name for day in jao.JAO_DIR.iterdir() if jao.day_dir(day.name).is_dir())
    generation = tuple(
        (day, token) for day in days if (token := jao.domain_generation(day)) is not None
    )
    if 'core' not in _geometries or generation != _geometry_generation:
        cached = [
            requested.element_ends
            if requested is not None and day == required_day
            else jao.load_day(day).element_ends
            for day, _ in generation
        ]
        if not cached:
            raise RuntimeError(
                f'no current, complete JAO domain day cached under {jao.JAO_DIR}; run '
                '`python -m coppersushi.data_sources.jao fetch <day>`'
            )
        _geometries['core'] = cnec_geometry.locate_elements(
            pd.concat(cached, ignore_index=True).drop_duplicates(
                ['eic', 'tso', 'name'], keep='last'
            ),
            osm_locator.read_csvs(),
            osm_locator.load_aliases(),
        )
        _geometry_generation = generation
    return _geometries['core']


def cnec_day(day: str) -> cnec_page.Day:
    """One delivery day's inputs, fetching the day's own feeds on first use."""
    mapped_elements = cnec_geometries(day)
    cached = _cnec_days.get(day)
    if cached is None or cached.mapped_elements is not mapped_elements:
        active = jao.load_active_day(day)
        _cnec_days[day] = cnec_page.Day(
            market_day=MarketDay.on(day),
            zones=core_zones(),
            mapped_elements=mapped_elements,
            constraints=active.constraints,
            ptdfs=active.ptdfs,
            external_constraints=active.external_constraints,
            prices=electricity_maps.load_day(day),
        )
    return _cnec_days[day]


def network_key_from_path(pathname: str) -> str:
    key = (pathname or '').strip('/')
    return key if key in NETWORK_LOADERS else 'v1'


def cnec_day_from_path(pathname: str) -> str | None:
    """The delivery day a `/cnec/<day>` path opens on, or None when it names no day."""
    parts = (pathname or '').strip('/').split('/')
    return parts[1] if len(parts) > 1 and parts[0] == CNEC_ROUTE else None


def is_cnec_path(pathname: str) -> bool:
    return (pathname or '').strip('/').split('/')[0] == CNEC_ROUTE


def network_layout() -> html.Div:
    return html.Div([
        dbc.Alert(id='status', color='danger', is_open=False, style={'margin': '0 1em'}),
        dcc.Loading(
            dcc.Graph(
                id='map',
                style={'height': '100%'},
                figure=dict(layout=dict(autosize=True)),
                config=dict(responsive=True, displayModeBar=False, scrollZoom=True)
            ),
            type='circle', delay_show=300, parent_style={'height': '90vh'},
            overlay_style={'visibility': 'visible', 'opacity': 0.4},
        ),
        html.Div(
            dcc.Slider(
                0, 1, step=1, value=0,
                id='snapshot-slider'
            )
        )
    ])


app.layout = html.Div([
    dcc.Location(id='url'),
    html.Div(
        [
            dcc.Link('2013 model (v1)', href='/', style={'marginRight': '1em'}),
            dcc.Link('2013 OPF on the 2025 grid', href='/opf-2013', style={'marginRight': '1em'}),
            dcc.Link('2024 OPF on the 2025 grid', href='/opf-2024', style={'marginRight': '1em'}),
            dcc.Link('Prices and binding CNECs', href=f'/{CNEC_ROUTE}'),  # No day: today's
        ],
        style={'padding': '0.4em 1em'}
    ),
    html.Div(id='page'),
])


@app.callback(Output('page', 'children'), Input('url', 'pathname'))
def show_page(pathname: str):
    if is_cnec_path(pathname):
        return cnec_page.layout(cnec_day_from_path(pathname), mapbox_token())
    return network_layout()


def render(pathname: str, snapshot_index: int, slider_moved: bool) -> tuple:
    """Figure, slider state and status banner for one view; a failed load becomes the banner."""
    network_key = network_key_from_path(pathname)
    try:
        fig, snapshots = figure_for(network_key)
    except Exception as e:  # noqa: BLE001 — every loader failure must reach the page
        logging.exception('Loading %s failed', network_key)
        return no_update, no_update, no_update, no_update, f'Could not load {network_key}: {e}', True
    if not slider_moved or snapshot_index >= len(snapshots):
        snapshot_index = min(6, len(snapshots) - 1)  # Midday by default
    marks = {
        idx: dict(label=str(snapshot.time()), style=dict(writingMode='vertical-rl'))
        for idx, snapshot in enumerate(snapshots)
    }
    return power_flow.show_snapshot(fig, snapshot_index), len(snapshots) - 1, marks, snapshot_index, '', False


@app.callback(
    Output('map', 'figure'),
    Output('snapshot-slider', 'max'),
    Output('snapshot-slider', 'marks'),
    Output('snapshot-slider', 'value'),
    Output('status', 'children'),
    Output('status', 'is_open'),
    Input('url', 'pathname'),
    Input('snapshot-slider', 'value'))
def update_figure(pathname: str, snapshot_index: int):
    return render(pathname, snapshot_index, ctx.triggered_id == 'snapshot-slider')


def render_cnec(day: str, interval_index: int, selected: str | None, reference_zone: str) -> tuple:
    """The CNEC page's map and controls for one day; a failed load becomes the banner."""
    try:
        rendered = cnec_page.render(
            cnec_day(day), interval_index or 0, selected, reference_zone, mapbox_token(), basemap()
        )
    except Exception as e:  # noqa: BLE001 — every loader failure must reach the page
        logging.exception('Loading the CNEC day %s failed', day)
        return (no_update,) * 6 + (f'Could not load {day}: {e}', True)
    return (
        rendered.figure,
        rendered.interval_max,
        rendered.interval_marks,
        rendered.interval_value,
        rendered.constraint_options,
        rendered.constraint_value,
        '',
        False,
    )


@app.callback(
    Output('cnec-map', 'figure'),
    Output('cnec-interval', 'max'),
    Output('cnec-interval', 'marks'),
    Output('cnec-interval', 'value'),
    Output('cnec-constraint', 'options'),
    Output('cnec-constraint', 'value'),
    Output('cnec-status', 'children'),
    Output('cnec-status', 'is_open'),
    Input('cnec-date', 'value'),
    Input('cnec-interval', 'value'),
    Input('cnec-constraint', 'value'),
    Input('cnec-reference-zone', 'value'))
def update_cnec(day: str, interval_index: int, selected: str | None, reference_zone: str):
    return render_cnec(day, interval_index, selected, reference_zone)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    app.run(debug=True)
