from coppersushi import REPO
"""Publication receipt evidence distinguishes missing data from no binding constraints."""
import pytest
from coppersushi.pipelines.cnec.readiness import PublicationReceipt
from coppersushi.pipelines.cnec.readiness import PublicationNotReady
from coppersushi.pipelines.cnec.readiness import REQUIRED_PUBLICATIONS
from coppersushi.pipelines.cnec.readiness import require_received
from coppersushi.pipelines.market_day import MarketDay
from coppersushi.pipelines.jao import elements as cnecs


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


@pytest.fixture
def legacy_rebuild_inputs(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import pandas as pd
    from coppersushi.pipelines.cnec.data_sources import bundles, electricity_maps

    day = MarketDay.on('2025-11-05')
    monkeypatch.setattr(electricity_maps, 'CACHE_DIR', tmp_path)
    monkeypatch.delenv('COPPERSUSHI_CACHE_BUCKET', raising=False)
    monkeypatch.setattr(electricity_maps, 'fetch_day', lambda *args: pytest.fail('Fetched live prices'))
    monkeypatch.setattr(bundles.jao, '_get',
                        lambda *args, **kwargs: [row.model_dump() for row in receipts(day)])
    monkeypatch.setattr(bundles.jao, 'load_active_day',
                        lambda *args, **kwargs: SimpleNamespace(constraints=[], ptdfs=[]))
    monkeypatch.setattr(bundles.cnec_attribution, 'load_day', lambda *args, **kwargs: pd.DataFrame({
        'interval': day.market_time_units(), 'polish_alt': 1.0,
    }))
    return day


@pytest.mark.parametrize('invalid', [False, True], ids=['missing', 'invalid'])
def test_historical_rebuilds_require_retained_prices(tmp_path, monkeypatch, legacy_rebuild_inputs, invalid):
    import sys
    from coppersushi.pipelines.cnec.data_sources import backfill, bundles, electricity_maps

    day = legacy_rebuild_inputs
    key = day.date.isoformat()
    reason = 'Retained prices invalid' if invalid else 'No readable retained prices'
    if invalid:
        electricity_maps.day_path(key).write_text('interval,price\n2025-11-05T00:00:00Z,10\n')

    monkeypatch.setattr(sys, 'argv', ['bundles', key, '--directory', str(tmp_path),
                                    '--legacy-prices', '--refresh'])
    with pytest.raises(electricity_maps.RetainedPricesUnavailable, match=f'{reason} for {key}'):
        bundles.main()

    report = tmp_path / 'backfill.jsonl'
    previous = backfill.Coverage(day=day.date, expected_intervals=96, status='eligible')
    report.write_text(previous.model_dump_json(exclude={'retained_prices'}) + '\n')
    monkeypatch.setattr(backfill.jao, '_pacer', backfill.jao.RequestPacer())
    monkeypatch.setattr(sys, 'argv', ['backfill', key, key, '--report', str(report), '--legacy-prices'])
    with pytest.raises(SystemExit) as stopped:
        backfill.main()
    assert stopped.value.code == 1
    result = backfill.Coverage.model_validate_json(report.read_text().splitlines()[-1])
    assert result.day == day.date
    assert result.status == 'blocked'
    assert result.retained_prices
    assert f'{reason} for {key}' in result.errors[0]


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
    monkeypatch.setattr(backfill, 'audit', lambda day, **options: result.model_copy())
    monkeypatch.setattr(sys, 'argv', ['backfill', '2025-11-05', '2025-11-05',
                                    '--report', str(report), '--bucket', 'test', '--legacy-prices'])
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
    assert backfill.Coverage.model_validate_json(report.read_text().splitlines()[-1]).status == 'existing'


@pytest.mark.parametrize(('winner_day', 'expected_status'), [('2025-11-05', 'existing'), ('2025-11-06', 'blocked')])
def test_backfill_preserves_and_verifies_manifest_created_during_preparation(tmp_path, monkeypatch,
                                                                      winner_day, expected_status):
    import gzip
    from io import BytesIO
    import sys

    from botocore.exceptions import ClientError

    from coppersushi.pipelines.cnec.data_sources import backfill
    from coppersushi.pipelines.cnec.models import DayBundle, DayManifest, MarketInterval

    day = MarketDay.on('2025-11-05')
    manifest_key = f'data/cnec/v3/{day.date}/manifest.json'
    winner = DayManifest(day=MarketDay.on(winner_day).date, generation='f' * 24)
    winner_body = gzip.compress(winner.model_dump_json().encode())
    objects = {}
    events = []

    class Store:
        def head_object(self, *, Bucket, Key):
            assert Key == manifest_key and Key not in objects
            events.append('initial check')
            raise ClientError({'Error': {'Code': '404'}}, 'HeadObject')

        def put_object(self, *, Bucket, Key, Body, **options):
            if Key == manifest_key:
                events.append('manifest write')
                if options.get('IfNoneMatch') == '*' and Key in objects:
                    raise ClientError({'Error': {'Code': 'PreconditionFailed'},
                                       'ResponseMetadata': {'HTTPStatusCode': 412}}, 'PutObject')
            else:
                assert 'IfNoneMatch' not in options
            objects[Key] = Body

        def get_object(self, *, Bucket, Key):
            assert Key == manifest_key
            events.append('verify winner')
            return {'Body': BytesIO(objects[Key]), 'ContentEncoding': 'gzip'}

    def prepare(day, **options):
        events.append('prepare')
        objects[manifest_key] = winner_body
        labels = [timestamp.isoformat() for timestamp in day.market_time_units()]
        intervals = [MarketInterval(index=index, label=label, prices={}, constraints=[], alpha=0.5,
                                    caps=[], notes=[]) for index, label in enumerate(labels)]
        return DayBundle(day=day.date, labels=labels, zones=[], elements={}, intervals=intervals, price_range=[0, 0])

    monkeypatch.setattr(backfill.jao, '_pacer', backfill.jao.RequestPacer())
    monkeypatch.setattr(backfill.cache, '_client', Store)
    monkeypatch.setattr(backfill.bundles, 'prepare', prepare)
    monkeypatch.setattr(backfill, 'audit', lambda day, **options: backfill.Coverage(
        day=day.date, expected_intervals=96, status='eligible'))
    report = tmp_path / 'report.jsonl'
    monkeypatch.setattr(sys, 'argv', ['backfill', str(day.date), str(day.date), '--report', str(report),
                                     '--bucket', 'test', '--archive-bucket', 'test'])
    with pytest.raises(SystemExit) as stopped:
        backfill.main()
    assert stopped.value.code == int(expected_status == 'blocked')
    assert events == ['initial check', 'prepare', 'manifest write', 'verify winner']
    assert objects[manifest_key] == winner_body
    result = backfill.Coverage.model_validate_json(report.read_text())
    assert result.status == expected_status
    if expected_status == 'blocked':
        assert result.errors == ['publication: ValueError: Expected a manifest for 2025-11-05; found 2025-11-06']
    else:
        assert result.errors == []


def test_backfill_reports_existing_generation_separately_and_resumes_equivalent_cutoff(tmp_path, monkeypatch):
    import sys
    from datetime import datetime
    from coppersushi.pipelines.cnec.data_sources import backfill

    monkeypatch.setattr(backfill.jao, '_pacer', backfill.jao.RequestPacer())
    report = tmp_path / 'report.jsonl'
    explicit_cutoff = '2025-11-06T10:00:00+00:00'
    audits = []

    def audit(day, *, archive_bucket, price_cutoff):
        audits.append(price_cutoff)
        return backfill.Coverage(day=day.date, expected_intervals=96, status='eligible')

    monkeypatch.setattr(backfill, 'audit', audit)
    monkeypatch.setattr(backfill.bundles, 'is_published', lambda *args: True)
    command = ['backfill', '2025-11-05', '2025-11-05', '--report', str(report), '--bucket', 'test']

    def run(*options):
        monkeypatch.setattr(sys, 'argv', [*command, *options])
        with pytest.raises(SystemExit) as stopped:
            backfill.main()
        assert stopped.value.code == 0
        return backfill.Coverage.model_validate_json(report.read_text().splitlines()[-1])

    historical = run('--price-cutoff', explicit_cutoff)
    assert historical.status == 'existing'
    assert historical.price_cutoff == datetime.fromisoformat(explicit_cutoff)
    assert run('--price-cutoff', explicit_cutoff) == historical
    assert audits == [historical.price_cutoff]

    latest = run()
    assert latest.status == 'existing'
    assert latest.price_cutoff > historical.price_cutoff
    assert run() == latest
    assert audits == [historical.price_cutoff, latest.price_cutoff]

    assert run('--price-cutoff', explicit_cutoff) == historical
    assert audits == [historical.price_cutoff, latest.price_cutoff, historical.price_cutoff]
