"""Archived execution, reproduction and local tracking."""
import os
from pathlib import Path

from forecasts.provenance import ROOT


def data_root() -> Path:
    """Resolve the shared directory for run artifacts, workflow metadata and tracking."""
    return Path(os.environ.get("FORECAST_DATA_ROOT", ROOT / "data/forecasts")).resolve()
