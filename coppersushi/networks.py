"""The shelf of solved networks under ``networks/`` (Git LFS objects): where they are, and how to open them."""

from pathlib import Path

import pypsa

REPO = Path(__file__).parents[1]
NETWORKS_DIR = REPO / "networks"
CANDIDATES_DIR = NETWORKS_DIR / "candidates"  # gitignored; pypsa_eur.promote() sanctions a candidate into NETWORKS_DIR


def solved(day: str) -> Path:
    """A sanctioned day's network, named by the day it covers: ``networks/opf-2013-07-17.nc``."""
    return NETWORKS_DIR / f"opf-{day}.nc"


def candidate(day: str, sha: str) -> Path:
    """An unsanctioned solve, named by its day and the PyPSA-Eur pin it came from: ``opf-2013-07-17-bccf56e8.nc``."""
    return CANDIDATES_DIR / f"opf-{day}-{sha[:8]}.nc"


def load(path: Path) -> pypsa.Network:
    """Open a network file, failing readably when it is still a Git LFS pointer."""
    if path.stat().st_size < 1024 and path.read_bytes().startswith(b"version https://git-lfs"):
        raise RuntimeError(f"{path} is a Git LFS pointer; run `git lfs pull` (see README)")
    return pypsa.Network(path)
