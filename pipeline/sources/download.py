"""Observable HTTP download shared by the source adapters."""

import logging
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

def download(url: str, target: Path) -> Path:
    """Fetch ``url`` into ``target`` atomically, logging start, quarter milestones and completion."""
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    logger.info("%s: fetching %s", target.name, url)
    urllib.request.urlretrieve(url, partial, _log_progress(target.name))
    partial.replace(target)
    logger.info("%s: done (%.1f MB)", target.name, target.stat().st_size / 1e6)
    return target


def _log_progress(filename: str, step: float = 0.25):
    """`urlretrieve` hook logging progress at coarse milestones."""
    milestone = step

    def hook(blocks: int, block_size: int, total_size: int) -> None:
        nonlocal milestone
        if total_size <= 0:
            return
        while milestone < 1 and blocks * block_size / total_size >= milestone:
            logger.info("%s: %.0f%% of %.1f MB", filename, milestone * 100, total_size / 1e6)
            milestone += step

    return hook
