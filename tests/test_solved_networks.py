import subprocess
from pathlib import Path

import pandas as pd
import pypsa
import pytest

from pipeline.sinks import solved_networks


def test_pin_file_parses_to_url_and_sha():
    pin = solved_networks.read_pin()
    assert pin.url.endswith("/pypsa-eur.git")
    assert len(pin.sha) == 40 and int(pin.sha, 16)


def test_sibling_env_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("PYPSA_EUR_DIR", str(tmp_path))
    assert solved_networks.sibling_dir() == tmp_path


def test_sibling_sits_beside_the_main_checkout(monkeypatch, tmp_path):
    monkeypatch.delenv("PYPSA_EUR_DIR", raising=False)
    repo = tmp_path / "github" / "repo"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    assert solved_networks.sibling_dir(repo) == tmp_path / "github" / "pypsa-eur"


def test_checkout_refuses_modified_tracked_files(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("x")
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    tracked.write_text("y")
    with pytest.raises(RuntimeError, match="uncommitted"):
        solved_networks.checkout(solved_networks.Pin("url", "0" * 40), tmp_path)


def test_checkout_needs_a_git_checkout(tmp_path):
    with pytest.raises(FileNotFoundError):
        solved_networks.checkout(solved_networks.Pin("url", "0" * 40), tmp_path)


def test_promote_copies_the_candidate_to_the_days_network(monkeypatch, tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    networks = tmp_path / "networks"
    networks.mkdir()
    candidate = networks / "candidates" / "opf-2013-07-17-bccf56e8.nc"
    candidate.parent.mkdir()
    candidate.write_bytes(b"net")
    monkeypatch.setattr(solved_networks, "REPO", tmp_path)
    monkeypatch.setattr(solved_networks, "NETWORKS_DIR", networks)

    promoted = solved_networks.promote(candidate)

    assert promoted == networks / "opf-2013-07-17.nc" and promoted.read_bytes() == b"net"
    staged = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=tmp_path, capture_output=True, text=True).stdout
    assert "networks/opf-2013-07-17.nc" in staged


def _network_with_shedder(shed_mw: float) -> pypsa.Network:
    n = pypsa.Network()
    n.set_snapshots(pd.date_range("2024-07-17", periods=2, freq="2h"))
    n.snapshot_weightings.loc[:, :] = 2.0
    n.add("Bus", "b1")
    n.add("Generator", "b1 load", bus="b1", carrier="load", p_nom=1e9)
    n.add("Generator", "b1 gas", bus="b1", carrier="gas", p_nom=100)
    n.generators_t.p = pd.DataFrame({"b1 load": [shed_mw, 0.0], "b1 gas": [50.0, 50.0]}, index=n.snapshots)
    return n


def test_shed_energy_is_weighted_mwh_per_bus():
    assert solved_networks.shed_energy(_network_with_shedder(3.0)).to_dict() == {"b1": 6.0}


def test_reject_shedding_names_the_bus():
    with pytest.raises(RuntimeError, match="b1: 6 MWh"):
        solved_networks.reject_shedding(_network_with_shedder(3.0))
    solved_networks.reject_shedding(_network_with_shedder(0.0))
