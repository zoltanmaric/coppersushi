"""Denominators, directional cap effects and UTC interval alignment."""
from pathlib import Path
import pandas as pd
from scripts.polish_export_caps import classify, summarize, procurement_frame

FIXTURES = Path(__file__).parent / 'fixtures' / 'polish-export-caps'


def test_binding_requires_export_position_and_positive_price_effect():
    frame = classify(pd.read_csv(FIXTURES / 'intervals.csv'), 0.01)
    assert frame.binding_export.tolist() == [True, False, False, False]
    assert frame.binding_known.tolist() == [True, True, True, False]
    summary = summarize(frame).set_index(['cohort', 'comparison'])
    row = summary.loc[('zero_export_cap', 'all')]
    assert row.selected == 3
    assert row.comparable == 2
    assert row.lower == 1
    assert row.share == 0.5


def test_strict_prices_and_nonbinding_without_alternative():
    frame = pd.read_csv(FIXTURES / 'intervals.csv')
    frame.loc[0, 'DE'] = 100.005
    frame.loc[2, 'polish_alt'] = None
    result = classify(frame, 0.01)
    assert result.lower_DE.iloc[0] == True
    assert result.lower_CZ.iloc[1] == False
    assert result.binding_known.iloc[2] == True
    assert result.binding_export.iloc[2] == False


def test_procurement_clock_change_late_versions_and_missing_products():
    purchases, requirements = [], []
    for stamp in ['2026-10-25 01:00:00', '2026-10-25 02:00:00', '2026-10-25 03:00:00']:
        purchases.append(dict(dtime_utc=stamp, publication_ts_utc='2026-10-24 07:10:00', fcr_g=100, afrr_g=200, mfrrd_g=300, rr_g=400))
        requirements.append(dict(dtime_utc=stamp, publication_ts_utc='2026-10-24 06:00:00', fcrg=100, afrrg=200, frrg=300, rrg=400))
    purchases[1]['publication_ts_utc'] = '2026-10-24 10:00:00'  # Noon Warsaw: too late.
    purchases[2]['rr_g'] = None
    result = procurement_frame(purchases, requirements).sort_values('interval')
    assert len(result) == 12
    assert result.interval.is_unique
    assert result.interval.iloc[0] == pd.Timestamp('2026-10-25T00:00Z')
    assert result.procured_mw.iloc[:4].tolist() == [1000]*4
    assert result.procured_mw.iloc[4:].isna().all()
    assert result.required_mw.eq(1000).all()


def test_binding_position_uses_published_rounding_tolerance():
    frame = pd.read_csv(FIXTURES / 'intervals.csv')
    frame['polish_position'] = frame.polish_position.astype(float)
    frame.loc[0, 'polish_position'] = -0.1
    result = classify(frame, 0.01)
    assert result.binding_export.iloc[0] == True


def test_missing_procurement_stays_missing():
    requirements = [dict(dtime_utc='2026-11-13 19:00:00', publication_ts_utc='2026-11-12 06:00:00', fcrg=100, afrrg=200, frrg=300, rrg=400)]
    result = procurement_frame([], requirements)
    assert len(result) == 4
    assert result.procured_mw.isna().all()
    assert result.required_mw.eq(1000).all()


def test_plot_status_distinguishes_cap_levels_and_missing_attribution():
    from scripts.polish_export_caps_report import cap_status
    frame = pd.DataFrame(dict(cap_published=[False, True, True, True, True, True, True, True],
                              export_limit=[float('nan'), 0, 0, 500, 500, 0, 500, -100],
                              zero_export_cap=[False, True, True, False, False, True, False, False],
                              binding_known=[False, True, True, True, True, False, False, True],
                              binding_export=[False, False, True, False, True, False, False, False]))
    assert cap_status(frame).tolist() == ['No published cap', 'Zero cap · not binding',
                                         'Zero cap · binding', 'Positive cap · not binding',
                                         'Positive cap · binding', 'Zero cap · binding unknown',
                                         'Positive cap · binding unknown', 'Negative cap · not binding']


def test_reserve_satisfied_cases_include_equal_and_excess_not_missing():
    from scripts.polish_export_caps_report import reserve_satisfied_cases
    frame = pd.DataFrame(dict(interval=pd.date_range('2026-08-14', periods=5, freq='15min', tz='UTC'),
                              cap_published=[True, True, True, True, False],
                              procured_mw=[1000, 1100, 999, 1200, 1100],
                              required_mw=[1000, 1000, 1000, float('nan'), 1000]))
    result = reserve_satisfied_cases(frame)
    assert result.index.tolist() == [0, 1]
    assert result.purchased_above_required_mw.tolist() == [0, 100]


def test_retrieval_coverage_keeps_legacy_caches_undated(tmp_path):
    from scripts.polish_export_caps import retrieval_coverage
    from shutil import copyfile
    copyfile(FIXTURES / 'empty-pse.json', tmp_path / '2026-11-13-wmb.json')
    coverage = retrieval_coverage(tmp_path, ['2026-11-13'])
    assert coverage.dated_inputs == 0
    assert coverage.earliest_retrieval_utc is None
    assert coverage.latest_retrieval_utc is None
    assert not coverage.span_complete
    assert coverage.inputs[-1].status == 'undated'
    assert coverage.inputs[0].status == 'source_cache_missing'


def test_pse_cache_preserves_original_fetch_and_rejects_changed_bytes(tmp_path, monkeypatch):
    from scripts.polish_export_caps import pse, retrieval_coverage
    calls = []
    def fetch(url, timeout):
        calls.append(url)
        return (FIXTURES / 'empty-pse.json').open()
    monkeypatch.setattr('urllib.request.urlopen', fetch)
    assert pse('wmb', '2026-11-13', tmp_path) == []
    first = retrieval_coverage(tmp_path, ['2026-11-13'])
    assert first.dated_inputs == 1
    assert first.inputs[-1].retrieval.urls == calls
    assert first.earliest_retrieval_utc <= first.latest_retrieval_utc
    assert pse('wmb', '2026-11-13', tmp_path) == []
    assert len(calls) == 1
    assert retrieval_coverage(tmp_path, ['2026-11-13']) == first
    path = tmp_path / '2026-11-13-wmb.json'
    path.write_text(path.read_text() + '\n')
    assert retrieval_coverage(tmp_path, ['2026-11-13']).inputs[-1].status == 'provenance_mismatch'
