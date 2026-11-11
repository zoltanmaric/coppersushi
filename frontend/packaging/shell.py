"""Assemble the static app shells and their shared navigation."""
import json
from pathlib import Path
from typing import Literal

from coppersushi import REPO
from coppersushi.cnec_support import FIRST_DAY


def navigation_html() -> str:
    return (Path(__file__).parent.parent / 'navigation.html').read_text()


def render_shell(token: str, *, embed: bool = False, view: Literal['cnec', 'opf'] = 'cnec') -> str:
    """Build a date-independent shell with safely embedded browser configuration."""
    config = json.dumps({'min_day': FIRST_DAY.isoformat(), 'token': token} if view == 'cnec' else {'token': token}).replace('<', r'\u003c')
    template = (REPO / 'frontend/index.html').read_text()
    template = template.replace('__APP_BUNDLE__', f'{view}-app')
    if view == 'opf':
        template = template.replace('Critical Elements', 'Power Flow').replace('A tool that shows exactly why day-ahead prices split between countries.', 'Hourly optimal power flow on the European grid.').replace('/cnec"', '/opf-2024"').replace('critical-elements-preview.png', 'copper-sushi-screenshot.png')
    return template.replace('__APP_NAVIGATION__', navigation_html()).replace('__CNEC_EMBED__', str(embed).lower()).replace('__CNEC_CONFIG__', config)
