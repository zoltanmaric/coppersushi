from pathlib import Path

import pytest

from pipeline.sources import networks

FIXTURE = Path(__file__).parent / "fixtures" / "networks" / "v1-sample.nc"


def test_pointer_is_reported_readably(tmp_path):
    pointer = tmp_path / "x.nc"
    pointer.write_text("version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 1\n")
    with pytest.raises(RuntimeError, match="git lfs pull"):
        networks.load(pointer)


def test_real_file_opens():
    assert len(networks.load(FIXTURE).buses) == 13
