"""Source adapter for PyPSA-Eur: solves a network in the pinned sibling checkout.

PyPSA-Eur runs from ``../pypsa-eur`` next to the *main* checkout — resolved through
git's common directory, so every worktree shares one checkout and one data directory —
at the commit named in ``pypsa-eur.pin``. Design: wiki/pypsa-eur-sibling.md.
"""

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pypsa
import yaml


logger = logging.getLogger(__name__)

REPO = Path(__file__).parents[2]
PIN_FILE = REPO / "pypsa-eur.pin"
CONFIG = REPO / "config" / "coppersushi.yaml"
NETWORKS_DIR = REPO / "networks"
CANDIDATES_DIR = NETWORKS_DIR / "candidates"  # gitignored; promote() sanctions a candidate into NETWORKS_DIR


@dataclass(frozen=True)
class Pin:
    url: str
    sha: str


def read_pin(path: Path = PIN_FILE) -> Pin:
    """The pin file holds two non-comment lines: repository URL, then commit SHA."""
    lines = [line.strip() for line in path.read_text().splitlines()]
    url, sha = [line for line in lines if line and not line.startswith("#")]
    return Pin(url, sha)


def sibling_dir(repo: Path = REPO) -> Path:
    """``$PYPSA_EUR_DIR`` if set, else ``pypsa-eur`` beside the main checkout."""
    if override := os.environ.get("PYPSA_EUR_DIR"):
        return Path(override)
    common_dir = Path(_git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    return common_dir.parent.parent / "pypsa-eur"


def checkout(pin: Pin, sibling: Path) -> None:
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


def solve(config: Path = CONFIG, target: str = "solve_elec_networks") -> Path:
    """Run PyPSA-Eur to ``target`` with ``config`` and copy the solved network into ``networks/``."""
    pin, sibling = read_pin(), sibling_dir()
    checkout(pin, sibling)
    logger.info("pypsa-eur: snakemake %s with %s in %s — a first run downloads ~20 GB and takes about an hour; "
                "snakemake narrates each rule", target, config.name, sibling)
    subprocess.run(["pixi", "run", "snakemake", "-call", target, "--configfile", str(config.resolve())],
                   cwd=sibling, check=True)
    cfg = yaml.safe_load(config.read_text())
    solved = sorted((sibling / "results" / cfg["run"]["name"] / "networks").glob("*.nc"))
    if len(solved) != 1:
        raise RuntimeError(f"expected exactly one solved network, found {solved}")
    CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
    candidate = CANDIDATES_DIR / candidate_filename(cfg["snapshots"]["start"], pin.sha)
    target = Path(shutil.copy2(solved[0], candidate))
    reject_shedding(pypsa.Network(target))
    logger.info("pypsa-eur: done — candidate %s; sanction it with `promote` to make it the day's network", target.name)
    return target


def shed_energy(n: pypsa.Network) -> pd.Series:
    """Energy served by PyPSA-Eur's load-shedding pseudo-generators, in MWh per bus."""
    shedders = n.generators.index[n.generators.carrier == "load"]
    per_snapshot = n.generators_t.p.reindex(columns=shedders, fill_value=0.0)
    hours = n.snapshot_weightings.generators.reindex(per_snapshot.index, fill_value=1.0)
    return per_snapshot.mul(hours, axis=0).sum().groupby(n.generators.bus).sum()


def reject_shedding(n: pypsa.Network) -> None:
    """Fail loudly on any load shedding: a shed day is a misposed problem, not a result."""
    shed = shed_energy(n)
    shed = shed[shed > 0].sort_values(ascending=False)
    if not shed.empty:
        worst = ", ".join(f"{bus}: {mwh:,.0f} MWh" for bus, mwh in shed.head(5).items())
        raise RuntimeError(f"load shed at {len(shed)} buses, {shed.sum():,.0f} MWh in total — worst: {worst}")


def promote(candidate: Path) -> Path:
    """Sanction a candidate: copy it to ``networks/opf-<day>.nc`` (a Git LFS object once committed) and stage it."""
    day = candidate.stem.split("-", 1)[1].rsplit("-", 1)[0]
    target = Path(shutil.copy2(candidate, NETWORKS_DIR / network_filename(day)))
    subprocess.run(["git", "add", str(target)], cwd=REPO, check=True)
    logger.info("promoted %s to %s (staged; committing sanctions it)", candidate.name, target.name)
    return target


def candidate_filename(snapshot_start: str, sha: str) -> str:
    """Candidates carry the day and the pin they came from, e.g. ``opf-2013-07-17-bccf56e8.nc``."""
    return f"opf-{snapshot_start}-{sha[:8]}.nc"


def network_filename(snapshot_start: str) -> str:
    """Solved networks are named by the day they cover, e.g. ``opf-2013-07-17.nc``."""
    return f"opf-{snapshot_start}.nc"


def solved_network(snapshot_start: str) -> Path:
    """Path of a solved day's network in ``networks/`` (a Git LFS object)."""
    return NETWORKS_DIR / network_filename(snapshot_start)


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    if len(sys.argv) == 3 and sys.argv[1] == "promote":
        promote(Path(sys.argv[2]))
    else:
        solve()
