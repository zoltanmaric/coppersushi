"""Publication receipt evidence distinguishes missing data from no binding constraints."""
import pytest
from coppersushi.publication.readiness import PublicationReceipt, PublicationNotReady, REQUIRED_PUBLICATIONS, require_received
from coppersushi.market_day import MarketDay
from coppersushi import cnecs


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
    from coppersushi.publication.data_sources import bundles
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
