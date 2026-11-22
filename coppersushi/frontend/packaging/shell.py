"""Assemble the static app shells and their shared navigation."""
import json
from pathlib import Path
from typing import Literal

from coppersushi import REPO
from coppersushi.pipelines.cnec.support import FIRST_DAY


def navigation_html() -> str:
    return (Path(__file__).parent.parent / 'navigation.html').read_text()


def render_shell(token: str, *, embed: bool = False, view: Literal['cnec', 'opf', 'polish-cap', 'polish-cap-breakdown'] = 'cnec') -> str:
    """Build a date-independent shell with safely embedded browser configuration."""
    config = json.dumps({'min_day': FIRST_DAY.isoformat(), 'token': token} if view != 'opf' else {'token': token}).replace('<', r'\u003c')
    template = (REPO / 'coppersushi/frontend/index.html').read_text()
    template = template.replace('__APP_BUNDLE__', f"{'polish-cap' if view == 'polish-cap-breakdown' else view}-app")
    if view == 'opf':
        template = template.replace('Critical Elements ⚡️', 'Power Flow 🍣').replace('A tool that shows exactly why day-ahead prices split between countries.', 'Hourly optimal power flow on the European grid.').replace('/cnec"', '/opf-2024"').replace('critical-elements-preview.png', 'copper-sushi-screenshot.png')
    if view.startswith('polish-cap'):
        template = template.replace('Critical Elements ⚡️', 'Polish export caps').replace('A tool that shows exactly why day-ahead prices split between countries.', 'Investigate binding export caps and upward reserve procurement.').replace('/cnec\"', '/polish-export-caps\"')
    if view == 'polish-cap-breakdown':
        template = template.replace('<script src="/assets/plotly-mapbox-3.7.0.min.js"></script>', '')
    return template.replace('__APP_NAVIGATION__', navigation_html()).replace('__CNEC_EMBED__', str(embed).lower()).replace('__CNEC_CONFIG__', config)
