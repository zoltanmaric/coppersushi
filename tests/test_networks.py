from pathlib import Path

import pytest

from coppersushi import networks

FIXTURE = Path(__file__).parent / "fixtures" / "networks" / "v1-sample.nc"


def test_pointer_is_reported_readably(tmp_path):
    pointer = tmp_path / "x.nc"
    pointer.write_text("version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 1\n")
    with pytest.raises(RuntimeError, match="git lfs pull"):
        networks.load(pointer)


def test_real_file_opens():
    assert len(networks.load(FIXTURE).buses) == 13


def test_solved_network_is_named_by_its_day():
    assert networks.solved("2013-07-17") == networks.NETWORKS_DIR / "opf-2013-07-17.nc"


def test_candidate_carries_day_and_pin():
    assert networks.candidate("2013-07-17", "bccf56e8d5e8cf69") == networks.CANDIDATES_DIR / "opf-2013-07-17-bccf56e8.nc"
