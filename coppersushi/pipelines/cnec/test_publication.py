from coppersushi import REPO
"""Publication receipt evidence distinguishes missing data from no binding constraints."""
import pytest
from coppersushi.pipelines.cnec.readiness import PublicationReceipt
from coppersushi.pipelines.cnec.readiness import PublicationNotReady
from coppersushi.pipelines.cnec.readiness import REQUIRED_PUBLICATIONS
from coppersushi.pipelines.cnec.readiness import require_received
from coppersushi.pipelines.market_day import MarketDay
from coppersushi.pipelines.cnec import elements as cnecs


def receipts(day: MarketDay) -> list[PublicationReceipt]:
    return [PublicationReceipt(businessDayUtc=day.start_time_utc, page=page, status='Received')
            for page in REQUIRED_PUBLICATIONS]


@pytest.mark.parametrize('status', ['Expected', 'Pending'])
def test_missing_active_publication_waits_then_accepts_received(status: str) -> None:
    day = MarketDay.on('2026-11-07')
    rows = receipts(day)
    rows[0] = PublicationReceipt.model_validate({**rows[0].model_dump(), 'status': status})
    with pytest.raises(PublicationNotReady, match='Active FB Constraints'):
        require_received(day, rows)
    require_received(day, receipts(day))


def test_received_empty_binding_set_is_valid() -> None:
    day = MarketDay.on('2026-11-07')
    require_received(day, receipts(day))
    assert cnecs.active_constraints([]).empty
    assert cnecs.constraint_ptdfs([]).empty


def test_missing_or_wrong_day_receipts_cannot_publish() -> None:
    day = MarketDay.on('2026-11-07')
    for rows in ([], receipts(day)[1:], receipts(MarketDay.on('2026-11-06'))):
        with pytest.raises(PublicationNotReady):
            require_received(day, rows)


def test_duplicate_receipt_is_invalid_not_pending() -> None:
    day = MarketDay.on('2026-11-07')
    rows = receipts(day)
    with pytest.raises(ValueError, match='Duplicate'):
        require_received(day, rows + rows[:1])


def test_historical_policy_does_not_bypass_missing_receipts(monkeypatch):
    from coppersushi.pipelines.cnec.data_sources import bundles
    day = MarketDay.on('2025-11-05')
    monkeypatch.setattr(bundles.jao, '_get',
                        lambda *args, **kwargs: [r.model_dump() for r in receipts(day)[1:]])
    with pytest.raises(PublicationNotReady, match='Active FB Constraints'):
        bundles.prepare(day, allow_partial_attribution=True)


def test_legacy_shadow_prices_receipt_identifies_active_fb_publication():
    day = MarketDay.on('2025-11-05')
    rows = receipts(day)
    rows[0] = rows[0].model_copy(update={'page':'Shadow Prices'})
    require_received(day, rows)
    with pytest.raises(PublicationNotReady, match='Active FB Constraints'):
        require_received(day, [rows[0].model_copy(update={'status':'Pending'}), *rows[1:]])


@pytest.mark.parametrize('status', ['Expected', 'Pending'])
def test_legacy_receipt_does_not_override_explicit_current_status(status):
    day = MarketDay.on('2025-11-05')
    rows = receipts(day)
    legacy = rows[0].model_copy(update={'page':'Shadow Prices'})
    rows[0] = rows[0].model_copy(update={'status':status})
    with pytest.raises(PublicationNotReady, match='Active FB Constraints'):
        require_received(day, [*rows, legacy])


@pytest.mark.parametrize('alpha', [-0.01, 1.01, float('inf')])
def test_attribution_boundary_rejects_out_of_range_alpha(alpha):
    from pathlib import Path
    import pandas as pd
    from pandera.errors import SchemaError
    from coppersushi.pipelines.data_model.cnec_attribution import AttributionContext
    path = REPO / 'coppersushi/pipelines/cnec/testdata/cnec-attribution/observed/context.csv'
    frame = pd.read_csv(path)
    frame.interval = pd.to_datetime(frame.interval, utc=True)
    with pytest.raises(SchemaError):
        AttributionContext.validate(frame.assign(alpha=alpha))


def test_interrupted_checkpoint_preserves_report_and_resume_skips_existing_manifest(tmp_path, monkeypatch):
    import sys
    from pathlib import Path
    from coppersushi.pipelines.cnec.data_sources import backfill
    monkeypatch.setattr(backfill.jao, '_pacer', backfill.jao.RequestPacer())
    report = tmp_path / 'report.jsonl'
    original = (REPO / 'coppersushi/pipelines/cnec/testdata/backfill/blocked.json').read_text()
    report.write_text(original)
    result = backfill.Coverage.model_validate_json(original).model_copy(
        update={'status':'eligible', 'errors':[]})
    monkeypatch.setattr(backfill, 'audit', lambda day: result.model_copy())
    monkeypatch.setattr(sys, 'argv', ['backfill', '2025-11-05', '2025-11-05',
                                    '--report', str(report), '--bucket', 'test'])
    published = []
    monkeypatch.setattr(backfill.bundles, 'is_published', lambda *args: bool(published))
    monkeypatch.setattr(backfill.bundles, 'prepare', lambda *args, **kwargs: object())
    monkeypatch.setattr(backfill.bundle, 'validate_publication', lambda *args, **kwargs: None)
    monkeypatch.setattr(backfill.bundles, 'publish', lambda *args, **kwargs: published.append(True))
    replace = Path.replace
    def interrupted_replace(source, target):
        if target == report:
            raise OSError('interrupted before checkpoint replacement')
        return replace(source, target)
    monkeypatch.setattr(Path, 'replace', interrupted_replace)
    with pytest.raises(OSError, match='interrupted'):
        backfill.main()
    assert report.read_text() == original
    assert len(published) == 1
    monkeypatch.setattr(Path, 'replace', replace)
    with pytest.raises(SystemExit) as exit:
        backfill.main()
    assert exit.value.code == 0
    assert len(published) == 1
    assert backfill.Coverage.model_validate_json(report.read_text().splitlines()[-1]).status == 'published'
