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


def test_the_pst_flag_survives_the_csv(tmp_path):
    """A bool column written as True/False is the round trip's easiest thing to silently invert."""
    model = written(tmp_path)
    assert model.transformers[model.transformers.eic == "19T0000000063830"].is_pst.all()
    assert not model.transformers[model.transformers.eic == "30T-ROSI400AT--1"].is_pst.any()


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


def test_the_committed_release_is_the_one_in_force_on_the_day():
    model = jao_static_grid.load_release()
    assert len(model.transformers) == 520
    elements = pd.read_csv(REPO / "data" / "jao" / "2024-08-29" / "elements.csv")
    monitored = set(elements[elements.element_type.isin(("Transformer", "PST"))].eic)
    assert monitored <= set(model.transformers.eic)
