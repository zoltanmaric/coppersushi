"""The shelf of solved networks under ``networks/`` (Git LFS objects): where they are, and how to open them."""

import re
from pathlib import Path

import pypsa

REPO = Path(__file__).parents[1]
NETWORKS_DIR = REPO / "networks"
CANDIDATES_DIR = NETWORKS_DIR / "candidates"  # gitignored
_CANDIDATE = re.compile(r"opf-(\d{4}-\d{2}-\d{2})-[0-9a-f]{8}")


def solved(day: str) -> Path:
    """A sanctioned day's network, named by the day it covers: ``networks/opf-2013-07-17.nc``."""
    return NETWORKS_DIR / f"opf-{day}.nc"


def candidate(day: str, sha: str) -> Path:
    """An unsanctioned solve, named by its day and the PyPSA-Eur pin it came from: ``opf-2013-07-17-bccf56e8.nc``."""
    return CANDIDATES_DIR / f"opf-{day}-{sha[:8]}.nc"


def day_of(candidate: Path) -> str:
    """The day a candidate covers, read back from its name."""
    if not (match := _CANDIDATE.fullmatch(candidate.stem)):
        raise ValueError(f"{candidate.name} is not a candidate name (opf-<day>-<pin>.nc)")
    return match[1]


def load(path: Path) -> pypsa.Network:
    """Open a network file, failing readably when it is still a Git LFS pointer."""
    if path.stat().st_size < 1024 and path.read_bytes().startswith(b"version https://git-lfs"):
        raise RuntimeError(f"{path} is a Git LFS pointer; run `git lfs pull` (see README)")
    return pypsa.Network(path)
