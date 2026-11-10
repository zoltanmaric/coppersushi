"""Shared static navigation for the CNEC and Dash page shells."""
from pathlib import Path


def navigation_html() -> str:
    return Path(__file__).with_name('navigation.html').read_text()
