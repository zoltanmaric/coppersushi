import logging
import os
import re
import subprocess
from pathlib import Path

import pandas as pd
import pypsa
import pytest
import yaml

from coppersushi.data_sources import networks, pypsa_eur
from coppersushi.market_day import MarketDay

# Upstream's `atlite.default_cutout` in config/config.default.yaml; ours overrides it or inherits it.
UPSTREAM_DEFAULT_CUTOUT = "europe-2013-sarah3-era5"


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
    candidate = networks_dir / "candidates" / "opf-2013-07-17-bccf56e8-0f1e2d3c-20260909T001532Z.nc"
    candidate.parent.mkdir()
    candidate.write_bytes(b"net")
    monkeypatch.setattr(pypsa_eur, "reject_unfit", lambda path: None)
    monkeypatch.setattr(pypsa_eur, "REPO", tmp_path)
    monkeypatch.setattr(networks, "NETWORKS_DIR", networks_dir)

    promoted = pypsa_eur.promote(candidate)

    assert promoted == networks_dir / "opf-2013-07-17.nc" and promoted.read_bytes() == b"net"
    staged = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=tmp_path, capture_output=True, text=True).stdout
    assert "networks/opf-2013-07-17.nc" in staged


def test_reject_unfit_loads_each_network_once_and_runs_every_guard(monkeypatch, tmp_path):
    candidate = tmp_path / "opf-2024-08-29-bccf56e8-0f1e2d3c-20260909T001532Z.nc"
    base = tmp_path / "base.nc"
    loaded, guards = [], []
    monkeypatch.setattr(pypsa_eur, "_base_network", lambda: base)
    monkeypatch.setattr(pypsa_eur.networks, "load", lambda path: loaded.append(path) or path.stem)
    monkeypatch.setattr(pypsa_eur.shedding, "reject", lambda n: guards.append(("shedding", n)))
    monkeypatch.setattr(pypsa_eur.simplification, "expected_transformers", lambda n: 821)
    monkeypatch.setattr(pypsa_eur.simplification, "reject", lambda n, m: guards.append(("simplification", n, m)))
    monkeypatch.setattr(pypsa_eur, "_monitored_sites", lambda n, day: pd.Series(["relation/1"]))
    monkeypatch.setattr(
        pypsa_eur.simplification, "reject_removed_monitored", lambda b, s, sites: guards.append(("removed", b, s))
    )

    pypsa_eur.reject_unfit(candidate)

    assert loaded == [candidate, base]
    assert guards == [
        ("shedding", candidate.stem),
        ("simplification", candidate.stem, 821),
        ("removed", "base", candidate.stem),
    ]


def test_the_stub_check_is_skipped_loudly_while_the_buses_carry_no_name(caplog):
    n = pypsa.Network()
    n.add("Bus", "relation/1-380", v_nom=380.0)
    with caplog.at_level(logging.WARNING):
        assert pypsa_eur._monitored_sites(n, "2024-08-29") is None
    assert "osm_name" in caplog.text


def weather_year_mismatch(config: dict) -> str | None:
    """Report a cutout whose weather year is not the day's, or ``None`` if they agree."""
    cutout = config.get("atlite", {}).get("default_cutout", UPSTREAM_DEFAULT_CUTOUT)
    if not (match := re.search(r"europe-(\d{4})-", cutout)):
        return f"cannot read a year from cutout {cutout!r}"
    day = config["snapshots"]["start"]
    if match.group(1) != day[:4]:
        return f"cutout {cutout!r} is weather year {match.group(1)}, but the day is {day}"
    return None


def test_the_weather_year_follows_the_day():
    assert weather_year_mismatch(yaml.safe_load(pypsa_eur.CONFIG.read_text())) is None


def test_weather_year_check_detects_a_stale_cutout():
    stale = {"snapshots": {"start": "2024-08-29"}, "atlite": {"default_cutout": "europe-2013-sarah3-era5"}}
    assert weather_year_mismatch(stale) == (
        "cutout 'europe-2013-sarah3-era5' is weather year 2013, but the day is 2024-08-29"
    )


def test_weather_year_check_catches_the_inherited_default():
    """With no `atlite` key the run silently inherits upstream's 2013 cutout."""
    assert "2013" in weather_year_mismatch({"snapshots": {"start": "2024-08-29"}})


def test_the_config_window_is_the_market_day():
    """What config/coppersushi.yaml must carry: PyPSA-Eur snapshots are naive UTC."""
    assert pypsa_eur.config_window(MarketDay.on("2024-08-29")) == ("2024-08-28 22:00", "2024-08-29 22:00")
    assert pypsa_eur.config_window(MarketDay.on("2013-07-17")) == ("2013-07-16 22:00", "2013-07-17 22:00")


def test_snapshots_are_naive_utc_matching_the_hours():
    day = MarketDay.on("2024-08-29")
    snapshots = pypsa_eur.snapshots(day)
    assert snapshots.tz is None
    assert list(snapshots) == list(day.hours().tz_localize(None))


def test_the_config_has_no_duplicate_top_level_keys():
    """PyYAML keeps the last of two identical keys and discards the first, silently.

    A second `data:` block once threw away `data.wdpa.source: primary`, so the workflow
    fell back to an archive copy that stalls mid-download — a config change that read as
    additive but deleted a setting three sections above it.
    """
    top_level = re.findall(r"^([A-Za-z_][\w-]*):", pypsa_eur.CONFIG.read_text(), re.MULTILINE)
    duplicates = {key for key in top_level if top_level.count(key) > 1}
    assert not duplicates, f"config/coppersushi.yaml defines these keys twice: {sorted(duplicates)}"


def test_overpass_retrieval_is_capped_below_the_core_count(monkeypatch):
    """`-call` runs one retrieval per core, which Overpass answers with 429s and then refusals."""
    captured = {}

    real_run = pypsa_eur.subprocess.run

    def fake_run(cmd, **kwargs):
        if cmd[0] != "pixi":  # let the runner's own git calls through
            return real_run(cmd, **kwargs)
        captured["cmd"] = cmd
        raise SystemExit  # stop before the workflow does any work

    monkeypatch.setattr(pypsa_eur, "_checkout", lambda *a: None)
    monkeypatch.setattr(pypsa_eur.subprocess, "run", fake_run)
    with pytest.raises(SystemExit):
        pypsa_eur.solve()

    cmd = captured["cmd"]
    assert f"overpass={pypsa_eur.OVERPASS_JOBS}" in cmd
    assert "retrieve_osm_data_raw:overpass=1" in cmd
    assert pypsa_eur.OVERPASS_JOBS < os.cpu_count()


def test_cached_downloads_are_served_without_revalidating():
    """A down endpoint must not stop the DAG building when the file is already cached."""
    assert pypsa_eur._workflow_env()[pypsa_eur.SKIP_REMOTE_CHECKS] == "True"


def test_the_environment_still_wins_over_the_default(monkeypatch):
    monkeypatch.setenv(pypsa_eur.SKIP_REMOTE_CHECKS, "False")
    assert pypsa_eur._workflow_env()[pypsa_eur.SKIP_REMOTE_CHECKS] == "False"


def test_an_interrupted_run_does_not_block_the_next_one(monkeypatch):
    """Incomplete outputs make snakemake refuse to start, which looks like a hang, not a failure."""
    captured = {}
    real_run = pypsa_eur.subprocess.run

    def fake_run(cmd, **kwargs):
        if cmd[0] != "pixi":
            return real_run(cmd, **kwargs)
        captured["cmd"] = cmd
        raise SystemExit

    monkeypatch.setattr(pypsa_eur, "_checkout", lambda *a: None)
    monkeypatch.setattr(pypsa_eur.subprocess, "run", fake_run)
    with pytest.raises(SystemExit):
        pypsa_eur.solve()
    assert "--rerun-incomplete" in captured["cmd"]
