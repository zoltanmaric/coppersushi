"""The shelf of solved networks under ``networks/`` (Git LFS objects): where they are, and how to open them."""

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

import pypsa

REPO = Path(__file__).parents[1]
NETWORKS_DIR = REPO / "networks"
CANDIDATES_DIR = NETWORKS_DIR / "candidates"  # gitignored
_CANDIDATE = re.compile(r"opf-(\d{4}-\d{2}-\d{2})-[0-9a-f]{8}-[0-9a-f]{8}-[A-Za-z0-9._-]+")
_EXPERIMENT = re.compile(r"[A-Za-z0-9._-]+")


def solved(day: str) -> Path:
    """A sanctioned day's network, named by the day it covers: ``networks/opf-2013-07-17.nc``."""
    return NETWORKS_DIR / f"opf-{day}.nc"


def candidate(day: str, sha: str, config: bytes, experiment: str | None = None) -> Path:
    """An unsanctioned solve, named by its day, the PyPSA-Eur pin, the config digest and a label.

    ``experiment`` tells apart runs that share a day, pin and config; it defaults to the UTC time
    of the call, to the second. It becomes part of a filename and a URL, so it is restricted to
    letters, digits, dot, dash and underscore.
    """
    if experiment is None:
        experiment = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    elif not _EXPERIMENT.fullmatch(experiment):
        raise ValueError(f"experiment {experiment!r} must match {_EXPERIMENT.pattern}")
    digest = hashlib.sha256(config).hexdigest()[:8]
    return CANDIDATES_DIR / f"opf-{day}-{sha[:8]}-{digest}-{experiment}.nc"


def day_of(candidate: Path) -> str:
    """The day a candidate covers, read back from its name."""
    if not (match := _CANDIDATE.fullmatch(candidate.stem)):
        raise ValueError(f"{candidate.name} is not a candidate name (opf-<day>-<pin>-<config>-<experiment>.nc)")
    return match[1]


def load(path: Path) -> pypsa.Network:
    """Open a network file, failing readably when it is still a Git LFS pointer."""
    if path.stat().st_size < 1024 and path.read_bytes().startswith(b"version https://git-lfs"):
        raise RuntimeError(f"{path} is a Git LFS pointer; run `git lfs pull` (see README)")
    return pypsa.Network(path)
