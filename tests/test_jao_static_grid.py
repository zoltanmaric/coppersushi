import pandas as pd
import pytest

from coppersushi import REPO, static_grid
from coppersushi.data_sources import jao_static_grid

FIXTURES = REPO / "tests" / "fixtures" / "static-grid"


def sheet(name: str) -> pd.DataFrame:
    return pd.read_csv(FIXTURES / name)


def written(directory) -> jao_static_grid.Model:
    jao_static_grid.write_release(
        directory,
        static_grid.transformers(sheet("transformers-sample.csv")),
        static_grid.branches(sheet("lines-sample.csv"), sheet("tielines-sample.csv")),
    )
    return jao_static_grid.read_release(directory)


def test_write_and_load_round_trip(tmp_path):
    model = written(tmp_path)
    assert not model.transformers.empty and not model.branches.empty
    assert model.transformers.is_pst.any()
    assert model.branches.is_tieline.any()


def test_the_boolean_flags_survive_the_csv(tmp_path):
    """Bool columns written as True/False are the round trip's easiest thing to silently invert."""
    tr = written(tmp_path).transformers.set_index("eic")
    assert tr.loc["99T-BRAVO-PS001B"].is_pst
    assert not tr.loc["99T-CHARL-TR001C"].is_pst
    assert not tr.loc["99T-FOXTR-TR001F"].x_physical
    assert tr.loc["99T-CHARL-TR001C"].x_physical


def test_a_blank_eic_survives_the_csv_as_missing_rather_than_the_string_nan(tmp_path):
    branches = written(tmp_path).branches
    assert branches.eic.isna().sum() == 2
    assert not branches.eic.eq("nan").any()


def test_a_short_download_is_refused():
    release = jao_static_grid.RELEASES[static_grid.RELEASE]
    with pytest.raises(RuntimeError, match="expected 1727357"):
        jao_static_grid.check_download(release, b"truncated")


def test_a_workbook_from_another_release_is_refused():
    """The zip lives in a folder named for its upload month, so only the workbook dates it."""
    with pytest.raises(RuntimeError, match="not the 2024-03-29 release"):
        jao_static_grid.check_workbook(
            "2024-03-29",
            "20240916_Core Static Grid Model_for publication.xlsx",
            list(jao_static_grid.WORKBOOK_SHEETS),
        )


def test_a_workbook_missing_a_sheet_is_refused():
    with pytest.raises(RuntimeError, match="expected"):
        jao_static_grid.check_workbook("2024-03-29", "20240329_x.xlsx", ["Lines", "Transformers"])


def test_the_release_directory_is_named_for_the_release_not_the_upload_month():
    assert jao_static_grid.release_dir(static_grid.RELEASE).name == "2024-03-29"
    assert jao_static_grid.RELEASES[static_grid.RELEASE].workbook.startswith("20240329")
