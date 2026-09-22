"""Runs PyPSA-Eur in the pinned sibling checkout and sanctions candidates. Design: wiki/pypsa-eur-sibling.md."""

import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

import pandas as pd
import yaml

from coppersushi import REPO, shedding
from coppersushi.data_sources import networks
from coppersushi.market_day import MarketDay

logger = logging.getLogger(__name__)

# Overpass is a free public endpoint. `-call` fires one retrieval per core, which it answers with
# HTTP 429 and then by refusing connections outright; the rule declares no resource of its own, so
# the cap is applied from here rather than by patching the workflow.
OVERPASS_JOBS = 2

# The cached-http storage plugin already caches Zenodo and data.pypsa.org downloads, but by default
# it revalidates each one against the remote *while building the DAG* — so an endpoint being down
# stops the workflow starting even though the file is on disk. `versions.csv` pins every dataset, so
# the revalidation buys little and costs a hard dependency on services outside our control.
SKIP_REMOTE_CHECKS = "SNAKEMAKE_STORAGE_CACHED_HTTP_SKIP_REMOTE_CHECKS"


def _workflow_env() -> dict[str, str]:
    """The workflow's environment: serve cached downloads without revalidating, unless overridden."""
    return {SKIP_REMOTE_CHECKS: "True"} | dict(os.environ)

PIN_FILE = REPO / "pypsa-eur.pin"
CONFIG = REPO / "config" / "coppersushi.yaml"


class Pin(NamedTuple):
    url: str
    sha: str


def solve(experiment: str | None = None) -> Path:
    """Run PyPSA-Eur with our config; the solved network becomes a candidate, kept but rejected if it sheds load."""
    pin, sibling = _read_pin(), _sibling_dir()
    _checkout(pin, sibling)
    cmd = ["pixi", "run", "snakemake", "-call", "solve_elec_networks", "--configfile", str(CONFIG),
           "--resources", f"overpass={OVERPASS_JOBS}", "--set-resources", f"retrieve_osm_data_raw:overpass=1",
           # An interrupted run leaves its outputs flagged incomplete, and snakemake then refuses to
           # start at all rather than redoing them — which reads as a hang, not a failure. Those
           # outputs are known-suspect, so redoing them is always the right answer.
           "--rerun-incomplete"]
    logger.info("pypsa-eur: `%s` in %s — a first run downloads ~20 GB and takes about an hour; snakemake narrates each rule",
                " ".join(cmd), sibling)
    subprocess.run(cmd, cwd=sibling, check=True, env=_workflow_env())
    cfg = yaml.safe_load(CONFIG.read_text())
    solved = sorted((sibling / "results" / cfg["run"]["name"] / "networks").glob("*.nc"))
    if len(solved) != 1:
        raise RuntimeError(f"expected exactly one solved network, found {solved}")
    day = MarketDay.containing(datetime.fromisoformat(cfg["snapshots"]["start"])).date.isoformat()
    candidate = networks.candidate(day, pin.sha, CONFIG.read_bytes(), experiment)
    candidate.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(solved[0], candidate)
    shedding.reject(networks.load(candidate))
    logger.info("pypsa-eur: done — candidate %s; sanction it with `promote` to make it the day's network", candidate.name)
    return candidate


def snapshots(day: MarketDay) -> pd.DatetimeIndex:
    """The market day's hours as PyPSA snapshots.

    The single conversion point where an aware timestamp becomes naive: PyPSA snapshots are
    naive, meaning UTC (coppersushi/AGENTS.md, explicit-timezones).
    """
    return day.hours().tz_localize(None)


def config_window(day: MarketDay) -> tuple[str, str]:
    """The market day's window as naive-UTC strings, the form PyPSA-Eur's ``snapshots`` takes."""
    return tuple(moment.strftime("%Y-%m-%d %H:%M") for moment in (day.start_time_utc, day.end_time_utc))


def promote(candidate: Path) -> Path:
    """Sanction a candidate: copy it to ``networks/opf-<day>.nc`` (a Git LFS object once committed) and stage it."""
    day = networks.day_of(candidate)
    shedding.reject(networks.load(candidate))
    target = Path(shutil.copy2(candidate, networks.solved(day)))
    subprocess.run(["git", "add", str(target)], cwd=REPO, check=True)
    logger.info("promoted %s to %s (staged; committing sanctions it)", candidate.name, target.name)
    return target


def _read_pin(path: Path = PIN_FILE) -> Pin:
    """The pin file holds two non-comment lines: repository URL, then commit SHA."""
    lines = [line.strip() for line in path.read_text().splitlines()]
    url, sha = [line for line in lines if line and not line.startswith("#")]
    return Pin(url, sha)


def _sibling_dir(repo: Path = REPO) -> Path:
    """``$PYPSA_EUR_DIR`` if set, else ``pypsa-eur`` beside the main checkout."""
    if override := os.environ.get("PYPSA_EUR_DIR"):
        return Path(override)
    common_dir = Path(_git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    return common_dir.parent.parent / "pypsa-eur"


def _checkout(pin: Pin, sibling: Path) -> None:
    """Put the sibling at the pinned commit; refuse to touch a dirty checkout."""
    if not (sibling / ".git").exists():
        raise FileNotFoundError(f"{sibling} is not a git checkout; clone {pin.url} there first")
    if _git(sibling, "status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError(f"{sibling} has uncommitted changes to tracked files; refusing to move it to {pin.sha[:10]}")
    if _git(sibling, "rev-parse", "HEAD") != pin.sha:
        logger.info("pypsa-eur: checking out %s in %s", pin.sha[:10], sibling)
        _git(sibling, "fetch", "--quiet", pin.url, pin.sha)
        _git(sibling, "checkout", "--quiet", "--detach", pin.sha)
    head = _git(sibling, "rev-parse", "HEAD")
    if head != pin.sha:
        raise RuntimeError(f"{sibling} is at {head[:10]}, pin is {pin.sha[:10]}")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    match sys.argv[1:]:
        case ["solve"]:
            solve()
        case ["solve", experiment]:
            solve(experiment)
        case ["promote", candidate]:
            promote(Path(candidate))
        case _:
            sys.exit(f"usage: python -m {__spec__.name} solve [experiment] | promote <candidate.nc>")
