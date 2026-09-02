import subprocess
from pathlib import Path

import pytest

from pipeline.sources import pypsa_eur


def test_pin_file_parses_to_url_and_sha():
    pin = pypsa_eur.read_pin()
    assert pin.url.endswith("/pypsa-eur.git")
    assert len(pin.sha) == 40 and int(pin.sha, 16)


def test_sibling_env_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("PYPSA_EUR_DIR", str(tmp_path))
    assert pypsa_eur.sibling_dir() == tmp_path


def test_sibling_sits_beside_the_main_checkout(monkeypatch, tmp_path):
    monkeypatch.delenv("PYPSA_EUR_DIR", raising=False)
    repo = tmp_path / "github" / "repo"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    assert pypsa_eur.sibling_dir(repo) == tmp_path / "github" / "pypsa-eur"


def test_checkout_refuses_modified_tracked_files(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("x")
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    tracked.write_text("y")
    with pytest.raises(RuntimeError, match="uncommitted"):
        pypsa_eur.checkout(pypsa_eur.Pin("url", "0" * 40), tmp_path)


def test_checkout_needs_a_git_checkout(tmp_path):
    with pytest.raises(FileNotFoundError):
        pypsa_eur.checkout(pypsa_eur.Pin("url", "0" * 40), tmp_path)


def test_solved_network_is_named_by_its_day():
    assert pypsa_eur.network_filename("2013-07-17") == "opf-2013-07-17.nc"


