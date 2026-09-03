"""Source adapter for the solved PyPSA-Eur networks under ``networks/`` (Git LFS objects).

``pipeline.sinks.solved_networks`` produces them; this module only names and locates them.
"""

from pathlib import Path

REPO = Path(__file__).parents[2]
NETWORKS_DIR = REPO / "networks"
CANDIDATES_DIR = NETWORKS_DIR / "candidates"  # gitignored; promote() sanctions a candidate into NETWORKS_DIR


def candidate_filename(snapshot_start: str, sha: str) -> str:
    """Candidates carry the day and the pin they came from, e.g. ``opf-2013-07-17-bccf56e8.nc``."""
    return f"opf-{snapshot_start}-{sha[:8]}.nc"


def network_filename(snapshot_start: str) -> str:
    """Solved networks are named by the day they cover, e.g. ``opf-2013-07-17.nc``."""
    return f"opf-{snapshot_start}.nc"


def solved_network(snapshot_start: str) -> Path:
    """Path of a solved day's network in ``networks/`` (a Git LFS object)."""
    return NETWORKS_DIR / network_filename(snapshot_start)
