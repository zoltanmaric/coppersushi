"""The one check that cannot be made against invented rows: do JAO's two publications agree?

`tests/test_static_grid.py` proves the mechanism on synthesised fixtures — that `s_nom`
computes √3 · U · Imax and that the join refuses to multiply rows. That is arithmetic, and
arithmetic is fine to test synthetically. What it cannot prove is that the workbook's
`Primary` and `Imax` describe the same quantity as the `fmax` the publication tool prints
for the same EIC. Two independent JAO publications agreeing to three digits is the evidence
that makes the Static Grid Model a rating source rather than a second guess, and it is only
evidence against JAO's own numbers.

JAO's terms forbid keeping those numbers in the tree (`data_sources/jao_static_grid.py`), so
this module skips unless both fetches have been run locally. A clean checkout runs green with
these skipped; a developer who has the data gets the assertion.
"""

import pandas as pd
import pytest

from coppersushi import REPO, static_grid
from coppersushi.data_sources import jao, jao_static_grid

DAY = "2024-08-29"
FETCH = (
    "python -m coppersushi.data_sources.jao_static_grid fetch"
    f" && python -m coppersushi.data_sources.jao fetch {DAY}"
)

RELEASE_DIR = jao_static_grid.release_dir(static_grid.RELEASE)
DAY_DIR = jao.day_dir(DAY)

pytestmark = pytest.mark.skipif(
    not (RELEASE_DIR.is_dir() and (DAY_DIR / "elements.csv").is_file()),
    reason=f"needs JAO's own data, which is not redistributable; run: {FETCH}",
)

# The day's monitored transformers whose nameplate MVA reproduces the feed's published fmax.
# The four that diverge are deliberately absent, and are not failures: the workbook is
# nameplate and the feed is the operational seasonal or dynamic value, so PST Roehrsdorf 441
# (1405 vs 1200.1), PST Vierraden 441 (1386 vs 1200.1), Mikulowa PST1 (1320 vs 831.4) and
# Mikulowa AT1 (605 vs 346.4) are a real distinction between two publications. Do not
# "fix" them by widening the tolerance until they pass.
AGREE = {
    "30T-ROSI400AT--1": 400.0,  # TR Rosiori 400/220 1 — the transformer that bound the day
    "30T-ARAD400AT3-F": 400.0,  # PST Arad 400/220 3
    "30T-UREC400AT--F": 400.0,  # PST Urechesti 400/220 1
    "14T-38220-WT041O": 1000.0,  # Westtirol 1 - Westtirol 2 WTRHU41
    "14T-38220-ZZ041D": 1200.0,  # Zell am Ziller 1 - Zell am Ziller 2 ZZRHU41
    "11T0-0000-0620-R": 1500.0,  # PST Gronau TR 441 E
}
MONITORED = 17  # Transformer and PST EICs the feed monitored that day, all present in the release


def monitored_with_s_nom() -> pd.DataFrame:
    """The day's monitored transformers, each with the feed's fmax and the workbook's s_nom."""
    elements = pd.read_csv(DAY_DIR / "elements.csv")
    points = elements[elements.element_type.isin(("Transformer", "PST"))]
    fmax = points.groupby("eic", as_index=False).fmax.max()
    return static_grid.join_on_eic(fmax, jao_static_grid.load_release().transformers)


def test_every_monitored_transformer_of_the_day_is_in_the_release():
    joined = monitored_with_s_nom()
    assert len(joined) == MONITORED
    assert joined.s_nom.notna().all()


def test_the_workbooks_nameplate_mva_reproduces_the_feeds_published_fmax():
    """√3 · Primary · Imax against a number JAO published separately, for the same EIC."""
    s_nom = monitored_with_s_nom().set_index("eic").s_nom
    for eic, fmax in AGREE.items():
        assert s_nom[eic] == pytest.approx(fmax, rel=0.005), eic


def test_most_of_the_day_agrees_within_a_few_per_cent():
    """A unit slip — kV read as V, or Imax taken at the secondary side — would show up here."""
    joined = monitored_with_s_nom()
    off_by = (joined.s_nom / joined.fmax - 1).abs()
    assert off_by.lt(0.08).sum() >= 13  # the other four are the nameplate-vs-operational rows
    assert off_by.lt(0.5).all()


def test_the_placeholder_transformer_rating_is_far_above_the_real_one():
    """PyPSA-Eur's `build_osm_network.py:1245` invents 4,425 MVA where JAO publishes 790."""
    s_nom = jao_static_grid.load_release().transformers.s_nom
    assert s_nom.median() == pytest.approx(789.8, abs=1.0)
    assert 4425 / s_nom.median() > 5


def test_the_fixtures_do_not_reproduce_jaos_own_values():
    """The synthesised fixtures must not have drifted back into being a copy of the release."""
    invented = pd.read_csv(REPO / "tests" / "fixtures" / "static-grid" / "transformers-sample.csv")
    real = jao_static_grid.load_release().transformers
    assert not set(invented.EIC_Code) & set(real.eic)
