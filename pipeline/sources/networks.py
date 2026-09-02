"""Open PyPSA networks stored under ``networks/`` (Git LFS objects)."""

from pathlib import Path

import pypsa


def load(path: Path) -> pypsa.Network:
    """Open a network file, failing readably when it is still a Git LFS pointer."""
    if path.stat().st_size < 1024 and path.read_bytes().startswith(b"version https://git-lfs"):
        raise RuntimeError(f"{path} is a Git LFS pointer; run `git lfs pull` (see README)")
    return pypsa.Network(path)
