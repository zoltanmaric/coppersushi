import subprocess
from pathlib import Path

import pytest

from coppersushi import networks, pypsa_eur


def test_pin_file_parses_to_url_and_sha():
    pin = pypsa_eur._read_pin()
    assert pin.url.endswith("/pypsa-eur.git")
    assert len(pin.sha) == 40 and int(pin.sha, 16)


def test_sibling_env_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("PYPSA_EUR_DIR", str(tmp_path))
    assert pypsa_eur._sibling_dir() == tmp_path


def test_sibling_sits_beside_the_main_checkout(monkeypatch, tmp_path):
    monkeypatch.delenv("PYPSA_EUR_DIR", raising=False)
    repo = tmp_path / "github" / "repo"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    assert pypsa_eur._sibling_dir(repo) == tmp_path / "github" / "pypsa-eur"


def test_checkout_refuses_modified_tracked_files(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("x")
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    tracked.write_text("y")
    with pytest.raises(RuntimeError, match="uncommitted"):
        pypsa_eur._checkout(pypsa_eur.Pin("url", "0" * 40), tmp_path)


def test_checkout_needs_a_git_checkout(tmp_path):
    with pytest.raises(FileNotFoundError):
        pypsa_eur._checkout(pypsa_eur.Pin("url", "0" * 40), tmp_path)


def test_promote_copies_the_candidate_to_the_days_network(monkeypatch, tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    networks_dir = tmp_path / "networks"
    networks_dir.mkdir()
    candidate = networks_dir / "candidates" / "opf-2013-07-17-bccf56e8.nc"
    candidate.parent.mkdir()
    candidate.write_bytes(b"net")
    monkeypatch.setattr(pypsa_eur.shedding, "reject", lambda n: None)
    monkeypatch.setattr(pypsa_eur.networks, "load", lambda path: path)
    monkeypatch.setattr(pypsa_eur, "REPO", tmp_path)
    monkeypatch.setattr(networks, "NETWORKS_DIR", networks_dir)

    promoted = pypsa_eur.promote(candidate)

    assert promoted == networks_dir / "opf-2013-07-17.nc" and promoted.read_bytes() == b"net"
    staged = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=tmp_path, capture_output=True, text=True).stdout
    assert "networks/opf-2013-07-17.nc" in staged

