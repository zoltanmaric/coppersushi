import re
from pathlib import Path

import pytest

from coppersushi.data_sources import networks

FIXTURE = Path(__file__).parent / "fixtures" / "networks" / "v1-sample.nc"


def test_pointer_is_reported_readably(tmp_path):
    pointer = tmp_path / "x.nc"
    pointer.write_text("version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 1\n")
    with pytest.raises(RuntimeError, match="git lfs pull"):
        networks.load(pointer)


def test_real_file_opens():
    assert len(networks.load(FIXTURE).buses) == 13



def test_day_reads_back_from_a_candidate_name():
    assert networks.day_of(networks.candidate("2013-07-17", "bccf56e8d5e8cf69", b"config")) == "2013-07-17"
    with pytest.raises(ValueError, match="not a candidate"):
        networks.day_of(networks.solved("2013-07-17"))


def test_a_changed_config_is_a_different_candidate():
    """Same day, same pin, different config: iterating on config must not overwrite the last solve."""
    pin = "bccf56e8d5e8cf69"
    first = networks.candidate("2024-08-29", pin, b"costs:\n  year: 2050\n")
    second = networks.candidate("2024-08-29", pin, b"costs:\n  year: 2025\n")
    assert first != second
    assert networks.day_of(first) == networks.day_of(second) == "2024-08-29"


def test_the_same_config_is_the_same_candidate():
    pin = "bccf56e8d5e8cf69"
    config = b"costs:\n  year: 2025\n"
    assert networks.candidate("2024-08-29", pin, config, "run") == networks.candidate("2024-08-29", pin, config, "run")


def test_an_experiment_name_tells_apart_runs_of_the_same_config():
    pin, config = "bccf56e8d5e8cf69", b"costs:\n  year: 2025\n"
    first = networks.candidate("2024-08-29", pin, config, "no-outages")
    second = networks.candidate("2024-08-29", pin, config, "with-outages")
    assert first != second
    assert "no-outages" in first.name and "with-outages" in second.name
    assert networks.day_of(first) == networks.day_of(second) == "2024-08-29"


def test_without_an_experiment_the_name_carries_a_utc_timestamp():
    path = networks.candidate("2024-08-29", "bccf56e8d5e8cf69", b"config")
    stamp = path.stem.rsplit("-", 1)[1]
    assert re.fullmatch(r"\d{8}T\d{6}Z", stamp), stamp
    assert networks.day_of(path) == "2024-08-29"


def test_an_experiment_name_cannot_escape_the_candidates_directory():
    for bad in ["../../etc/passwd", "a/b", "two words", ""]:
        with pytest.raises(ValueError, match="experiment"):
            networks.candidate("2024-08-29", "bccf56e8d5e8cf69", b"config", bad)
