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



def test_day_reads_back_from_a_candidate_name():
    assert networks.day_of(networks.candidate("2013-07-17", "bccf56e8d5e8cf69")) == "2013-07-17"
    with pytest.raises(ValueError, match="not a candidate"):
        networks.day_of(networks.solved("2013-07-17"))
