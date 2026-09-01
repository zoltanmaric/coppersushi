"""Fixture: a timestamp constructed without stating its timezone."""

import pandas as pd


def snapshot() -> pd.Timestamp:
    return pd.Timestamp("2026-08-12 12:00")
