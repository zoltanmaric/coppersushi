from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from coppersushi.pipelines.market_data.data_sources.editions import publish_edition, read_editions
from coppersushi.pipelines.market_data.data_sources.parquet import encode_table
from coppersushi.pipelines.market_data.data_sources.responses import read_day_diagnostics, save_diagnostic, save_response
from coppersushi.pipelines.market_data.edition_models import PriceRow, SpreadRow
from coppersushi.pipelines.market_data.response_models import AttemptOutcome, Poll
from coppersushi.pipelines.market_data.test_receipts import MemoryS3

DAY = date(2026, 11, 20)
QUARTER = datetime(2026, 11, 19, 23, tzinfo=UTC)
T = datetime(2026, 11, 19, 10, tzinfo=UTC)  # 11:00 Berlin


class ArchiveS3(MemoryS3):
    def __init__(self):
        super().__init__()
        self.interrupt_receipt = False
        self.now = T
        self.modified = {}
        self.lose_ack = None
        self.interrupt_edition = False
        self.reads = []

    def put_object(self, **request):
        key = request["Key"]
        if self.interrupt_edition and key.endswith(".parquet"):
            self.interrupt_edition = False
            raise TimeoutError("interrupted before edition PUT")
        super().put_object(**request)
        self.modified[key] = self.now.replace(microsecond=0)
        if self.lose_ack and self.lose_ack in key:
            self.lose_ack = None
            raise TimeoutError("lost S3 acknowledgement after PUT")

    def get_object(self, **request):
        return {**super().get_object(**request), "LastModified": self.modified[request["Key"]]}

    def head_object(self, **request):
        self.reads.append(request["Key"])
        return super().head_object(**request)

    def get_paginator(self, operation):
        assert operation == "list_objects_v2"
        return self

    def paginate(self, *, Bucket, Prefix):
        return [{"Contents": [{"Key": key, "LastModified": self.modified[key]}]}
                for key in sorted(self.objects) if key.startswith(Prefix)]


def landed(store, publisher="entsoe", zone="DE-LU", at=None):
    poll = Poll(publisher=publisher, zone=zone, attempt_id=uuid4(),
                dataset="day_ahead_border_spreads" if publisher == "jao" else "day_ahead_auction_prices",
                delivery_day=DAY)
    return save_response(store, "test", poll, b"synthetic response",
                         received_at=at if at is not None else store.now, http_status=200)


def price(value="40", zone="DE-LU"):
    return PriceRow(interval=QUARTER, zone=zone, price=Decimal(value))


def spread(origin, destination, difference):
    return SpreadRow(interval=QUARTER, origin=origin, destination=destination, difference=Decimal(difference))


def publish(store, publisher, zone, rows):
    receipt = landed(store, publisher, zone)
    publish_edition(store, "test", receipt, rows)
    return receipt


def test_interrupted_publication_leaves_raw_only_then_later_cutoffs_include_correction():
    store = ArchiveS3()
    store.now = T - timedelta(minutes=2)
    receipt = landed(store)
    store.interrupt_edition = True
    with pytest.raises(TimeoutError, match="before edition PUT"):
        publish_edition(store, "test", receipt, [price()])
    assert list(store.objects) == [f"market-data/attempts/{receipt.attempt_id}"]
    assert read_editions(store, "test", DAY, T) == []
    assert read_day_diagnostics(store, "test", DAY, T) == []

    store.now = T + timedelta(minutes=4, milliseconds=500)
    publish_edition(store, "test", receipt, [price()])
    key = f"market-data/editions/v1/{DAY}/{receipt.attempt_id}.parquet"
    assert sorted(store.objects) == [f"market-data/attempts/{receipt.attempt_id}", key]
    assert store.metadata[key] == {"schema-version": "1", "attempt-id": str(receipt.attempt_id)}
    assert not store.reads
    assert read_editions(store, "test", DAY, T) == []
    assert read_editions(store, "test", DAY, store.now) == []
    after_write = T + timedelta(minutes=4, seconds=1)
    (edition, rows), = read_editions(store, "test", DAY, after_write)
    assert edition.receipt == receipt and edition.key == key
    assert edition.published_at == T + timedelta(minutes=4)
    assert edition.available_at == after_write
    assert rows == [price()]

    store.now = T + timedelta(hours=1)
    correction = publish(store, "entsoe", "DE-LU", [price("42")])
    assert read_editions(store, "test", DAY, store.now) == [(edition, rows)]
    revisions = read_editions(store, "test", DAY, store.now + timedelta(seconds=1))
    assert {edition.receipt.attempt_id: values for edition, values in revisions} == {
        receipt.attempt_id: [price()], correction.attempt_id: [price("42")],
    }
    assert read_editions(store, "test", DAY, after_write) == [(edition, rows)]
    assert read_editions(store, "test", DAY, T) == []


def test_lost_ack_and_reencoding_preserve_first_publication():
    store = ArchiveS3()
    receipt = landed(store)
    rows = [price(), price("41").model_copy(update={"interval": QUARTER + timedelta(minutes=15)})]
    reordered = rows[::-1]
    assert encode_table(receipt, rows) != encode_table(receipt, reordered)
    store.lose_ack = "/editions/"
    with pytest.raises(TimeoutError, match="lost S3 acknowledgement"):
        publish_edition(store, "test", receipt, rows)
    key = f"market-data/editions/v1/{DAY}/{receipt.attempt_id}.parquet"
    initial_body = store.objects[key]
    assert not store.reads
    assert read_editions(store, "test", DAY, T) == []
    first_publication = read_editions(store, "test", DAY, T + timedelta(seconds=1))
    store.now += timedelta(minutes=15)
    publish_edition(store, "test", receipt, reordered)
    assert store.objects[key] == initial_body
    assert store.modified[key] == T
    assert read_editions(store, "test", DAY, T + timedelta(seconds=1)) == first_publication
    with pytest.raises(ValueError, match="Conflicting edition"):
        publish_edition(store, "test", receipt, [price("42")])
    conflicting_receipt = receipt.model_copy(update={"body_sha256": "a" * 64})
    with pytest.raises(ValueError, match="Conflicting edition"):
        publish_edition(store, "test", conflicting_receipt, rows)
    assert store.objects[key] == initial_body


def test_receipt_cutoff_is_independent_of_s3_publication_clock():
    store = ArchiveS3()
    received_at = T + timedelta(seconds=5, milliseconds=500)
    receipt = landed(store, at=received_at)
    publish_edition(store, "test", receipt, [price()])
    assert read_editions(store, "test", DAY, received_at - timedelta(microseconds=1)) == []
    (edition, _), = read_editions(store, "test", DAY, received_at)
    assert edition.available_at == received_at


def test_late_diagnostic_is_discoverable_only_after_its_own_publication():
    store = ArchiveS3()
    receipt = landed(store)
    cutoff = T + timedelta(minutes=1)
    assert read_day_diagnostics(store, "test", DAY, cutoff) == []

    store.now = T + timedelta(minutes=2, milliseconds=500)
    scope = receipt.model_dump(include=set(Poll.model_fields))
    failure = AttemptOutcome(**scope, completed_at=T, outcome="failed", rows=0, diagnostic="invalid currency")
    save_diagnostic(store, "test", failure)
    assert read_day_diagnostics(store, "test", DAY, cutoff) == []
    assert read_day_diagnostics(store, "test", DAY, store.now) == []
    assert read_editions(store, "test", DAY, store.now) == []

    visible_cutoff = T + timedelta(minutes=2, seconds=1)
    store.now += timedelta(minutes=1)
    save_diagnostic(store, "test", failure)
    assert read_day_diagnostics(store, "test", DAY, visible_cutoff) == [failure]
    assert read_editions(store, "test", DAY, visible_cutoff) == []


def test_empty_editions_and_spreads_are_visible_without_outcome_objects():
    store = ArchiveS3()
    empty = publish(store, "entsoe", "DE-LU", [])
    edge = spread("DE-LU", "AT", "-2.40")
    spreads = publish(store, "jao", "CORE", [edge])
    cutoff = T + timedelta(seconds=1)
    entries = read_editions(store, "test", DAY, cutoff)
    assert {edition.receipt.attempt_id: rows for edition, rows in entries} == {
        empty.attempt_id: [], spreads.attempt_id: [edge],
    }
    assert len(store.objects) == 4
    assert read_day_diagnostics(store, "test", DAY, cutoff) == []


def test_invalid_rows_and_corrupt_edition_fail():
    store = ArchiveS3()
    bad = landed(store)
    with pytest.raises(ValueError, match="native market grid"):
        publish_edition(store, "test", bad, [price().model_copy(update={"interval": QUARTER + timedelta(minutes=1)})])
    assert read_editions(store, "test", DAY, T + timedelta(seconds=1)) == []
    good = publish(store, "smard", "DE-LU", [price()])
    key = f"market-data/editions/v1/{DAY}/{good.attempt_id}.parquet"
    store.objects[key] = b"corrupted"
    with pytest.raises(ValueError, match="Invalid Parquet edition"):
        read_editions(store, "test", DAY, T + timedelta(seconds=1))
