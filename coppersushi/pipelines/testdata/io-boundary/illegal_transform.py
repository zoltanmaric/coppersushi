"""Negative fixture for the finite direct-I/O architecture check."""

import pandas as pd


def transform(path):
    return pd.read_csv(path)
