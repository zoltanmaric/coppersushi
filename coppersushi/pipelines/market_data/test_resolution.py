from datetime import timedelta
from decimal import Decimal

import pytest

from coppersushi.pipelines.market_data.data_sources.editions import read_editions
from coppersushi.pipelines.market_data.data_sources.prices import resolve_day
from coppersushi.pipelines.market_data.data_sources.responses import read_day_diagnostics, save_diagnostic
from coppersushi.pipelines.market_data.edition_models import SpreadRow
from coppersushi.pipelines.market_data.response_models import AttemptOutcome
from coppersushi.pipelines.market_data.resolution import (
    CNEC_POLICY, FORECAST_POLICY, ConflictingPrices, DerivedPrice, PriceUnavailable, PublishedPrice,
)
from coppersushi.pipelines.market_data.test_editions import ArchiveS3, DAY, QUARTER, T, landed, price, publish


def spread(origin, destination, difference):
    return SpreadRow(interval=QUARTER, origin=origin, destination=destination, difference=Decimal(difference))


def first(store, cutoff, zone="DE-LU", policy=FORECAST_POLICY):
    return resolve_day(store, "test", DAY, (zone,), cutoff, policy)[0]


def test_late_spreads_and_licensed_anchors_are_not_eligible_for_forecast():
    store = ArchiveS3()
    anchor = publish(store, "electricity_maps", "AT", [price("-12", "AT")])
    store.now += timedelta(minutes=15)
    edges = publish(store, "jao", "CORE", [spread("AT", "HU", "2.01"), spread("RO", "HU", "-3")])
    cutoff = store.now + timedelta(seconds=1)
    assert isinstance(first(store, cutoff, "RO"), PriceUnavailable)
    assert isinstance(first(store, T + timedelta(minutes=1), "RO", CNEC_POLICY), PriceUnavailable)
    derived = first(store, cutoff, "RO", CNEC_POLICY)
    assert isinstance(derived, DerivedPrice)
    assert derived.price == Decimal("-6.99")
    assert [e.attempt_id for e in derived.evidence] == [anchor.attempt_id, edges.attempt_id, edges.attempt_id]
    assert [(e.zone, e.destination) for e in derived.evidence] == [("AT", None), ("AT", "HU"), ("RO", "HU")]


def test_conflicting_direct_values_remain_visible_with_both_receipts():
    store = ArchiveS3()
    a = publish(store, "entsoe", "DE-LU", [price()])
    b = publish(store, "smard", "DE-LU", [price("41")])
    with pytest.raises(ConflictingPrices) as failure:
        first(store, T + timedelta(seconds=1))
    assert {row.attempt_id for row in failure.value.evidence} == {a.attempt_id, b.attempt_id}


def test_november_20_slovak_quote_is_checked_against_the_czech_anchor():
    store = ArchiveS3()
    quote = publish(store, "electricity_maps", "SK", [price("40", "SK")])
    anchor = publish(store, "electricity_maps", "CZ", [price("35", "CZ")])
    cutoff = T + timedelta(seconds=1)
    assert first(store, cutoff, "SK", CNEC_POLICY).evidence[0].attempt_id == quote.attempt_id

    store.now += timedelta(minutes=1)
    edges = publish(store, "jao", "CORE", [spread("CZ", "SK", "7")])
    with pytest.raises(ConflictingPrices) as failure:
        first(store, store.now + timedelta(seconds=1), "SK", CNEC_POLICY)
    conflict = failure.value
    assert (conflict.zone, conflict.interval, conflict.implied_price) == ("SK", QUARTER, Decimal("42"))
    receipts = [quote.attempt_id, anchor.attempt_id, edges.attempt_id]
    assert [row.attempt_id for row in conflict.evidence] == receipts
    assert all(str(receipt) in str(conflict) for receipt in receipts)
    assert first(store, cutoff, "SK", CNEC_POLICY).price == Decimal("40")

    store.now += timedelta(minutes=1)
    corrected = publish(store, "electricity_maps", "SK", [price("42", "SK")])
    checked = first(store, store.now + timedelta(seconds=1), "SK", CNEC_POLICY)
    assert isinstance(checked, PublishedPrice) and checked.evidence[0].attempt_id == corrected.attempt_id


def test_delayed_failed_outcome_does_not_change_a_historical_missing_result():
    store = ArchiveS3()
    receipt = landed(store)
    cutoff = T + timedelta(minutes=1)
    missing = first(store, cutoff)

    store.now = T + timedelta(minutes=2, milliseconds=500)
    outcome = AttemptOutcome(**receipt.model_dump(include={
        "attempt_id", "publisher", "zone", "dataset", "delivery_day"}), completed_at=T,
        outcome="failed", rows=0, diagnostic="invalid currency")
    save_diagnostic(store, "test", outcome)
    assert first(store, cutoff) == missing
    assert first(store, store.now) == missing

    visible_cutoff = T + timedelta(minutes=2, seconds=1)
    store.now += timedelta(minutes=1)
    save_diagnostic(store, "test", outcome)
    visible = first(store, visible_cutoff)
    assert visible.attempt_ids == (receipt.attempt_id,)
    assert "invalid currency" in visible.reason


def test_missing_result_reports_failed_poll_and_identifies_the_selected_alternate():
    store = ArchiveS3()
    bad = landed(store)
    save_diagnostic(store, "test", AttemptOutcome(**bad.model_dump(include={
        "attempt_id", "publisher", "zone", "dataset", "delivery_day"}), completed_at=T,
        outcome="failed", rows=0, diagnostic="invalid currency"))
    result = first(store, T + timedelta(seconds=1))
    assert bad.attempt_id in result.attempt_ids and "invalid currency" in result.reason
    good = publish(store, "smard", "DE-LU", [price()])
    cutoff = T + timedelta(seconds=1)
    selected = first(store, cutoff)
    assert isinstance(selected, PublishedPrice) and selected.evidence[0].attempt_id == good.attempt_id


def test_disagreeing_anchored_paths_fail_without_overwriting_direct_prices():
    store = ArchiveS3()
    a = publish(store, "entsoe", "AT", [price("49", "AT")])
    b = publish(store, "entsoe", "CZ", [price("50", "CZ")])
    edges = publish(store, "jao", "CORE", [spread("AT", "DE-LU", "2"), spread("CZ", "DE-LU", "2")])
    cutoff = T + timedelta(seconds=1)
    with pytest.raises(ConflictingPrices) as failure:
        first(store, cutoff)
    assert {row.attempt_id for row in failure.value.evidence} == {a.attempt_id, b.attempt_id, edges.attempt_id}
    assert first(store, cutoff, "AT").price == Decimal("49")


@pytest.mark.parametrize("publisher", ["entsoe", "electricity_maps"])
def test_chained_anchors_must_agree_under_the_consumer_policy(publisher):
    store = ArchiveS3()
    near = publish(store, "entsoe", "AT", [price("50", "AT")])
    far = publish(store, publisher, "CZ", [price("60", "CZ")])
    edges = publish(store, "jao", "CORE", [spread("DE-LU", "AT", "0"), spread("AT", "CZ", "0")])
    cutoff = T + timedelta(seconds=1)

    with pytest.raises(ConflictingPrices) as failure:
        first(store, cutoff, policy=CNEC_POLICY)
    conflict = failure.value
    assert (conflict.zone, conflict.interval) == ("DE-LU", QUARTER)
    assert [(row.zone, row.destination, row.attempt_id) for row in conflict.evidence] == [
        ("AT", None, near.attempt_id),
        ("DE-LU", "AT", edges.attempt_id),
        ("CZ", None, far.attempt_id),
        ("AT", "CZ", edges.attempt_id),
        ("DE-LU", "AT", edges.attempt_id),
    ]

    if publisher == "electricity_maps":
        derived = first(store, cutoff)
        assert isinstance(derived, DerivedPrice) and derived.price == Decimal("50")
        assert [row.attempt_id for row in derived.evidence] == [near.attempt_id, edges.attempt_id]


def test_consistent_spread_cycles_keep_the_shortest_eligible_anchor():
    store = ArchiveS3()
    near = publish(store, "entsoe", "AT", [price("50", "AT")])
    publish(store, "entsoe", "CZ", [price("54", "CZ")])
    edges = publish(store, "jao", "CORE", [
        spread("DE-LU", "AT", "2"), spread("AT", "CZ", "4"),
        spread("CZ", "HU", "3"), spread("HU", "AT", "-7"),
    ])
    derived = first(store, T + timedelta(seconds=1))
    assert isinstance(derived, DerivedPrice) and derived.price == Decimal("48")
    assert [row.attempt_id for row in derived.evidence] == [near.attempt_id, edges.attempt_id]


def test_later_stale_or_partial_poll_preserves_newest_known_interval():
    store = ArchiveS3()
    fresh = price().model_copy(update={"source_updated_at": T - timedelta(hours=1)})
    accepted = publish(store, "entsoe", "DE-LU", [fresh])
    store.now += timedelta(minutes=1)
    stale = price("20").model_copy(update={"source_updated_at": T - timedelta(hours=2)})
    publish(store, "entsoe", "DE-LU", [stale])
    store.now += timedelta(minutes=1)
    later = price("60").model_copy(update={"interval": QUARTER + timedelta(minutes=15)})
    publish(store, "entsoe", "DE-LU", [later])
    chosen = first(store, store.now + timedelta(seconds=1))
    assert chosen.price == Decimal("40") and chosen.evidence[0].attempt_id == accepted.attempt_id


def test_forecast_skips_corrupt_excluded_edition_while_full_audit_fails():
    store = ArchiveS3()
    publish(store, "entsoe", "DE-LU", [price()])
    excluded = publish(store, "electricity_maps", "DE-LU", [price()])
    key = f"market-data/editions/v1/{DAY}/{excluded.attempt_id}.parquet"
    store.objects[key] = b"invalid parquet"
    cutoff = T + timedelta(seconds=1)
    assert first(store, cutoff).price == Decimal("40")
    assert key not in store.reads
    with pytest.raises(ValueError, match="Invalid Parquet edition"):
        read_editions(store, "test", DAY, cutoff)
    with pytest.raises(ValueError, match="Invalid Parquet edition"):
        first(store, cutoff, policy=CNEC_POLICY)


def test_reported_availability_matches_cutoff_for_each_contributing_row():
    store = ArchiveS3()
    updated = T + timedelta(minutes=7)
    publish(store, "entsoe", "AT", [price("40", "AT").model_copy(update={"source_updated_at": updated})])
    spread_updated = updated + timedelta(minutes=2)
    publish(store, "jao", "CORE", [spread("AT", "DE-LU", "2").model_copy(update={"source_updated_at": spread_updated})])
    assert isinstance(first(store, updated - timedelta(microseconds=1), "AT"), PriceUnavailable)
    direct = first(store, updated, "AT")
    assert direct.available_at == updated
    assert direct.evidence[0].visible_at == T + timedelta(seconds=1)
    assert isinstance(first(store, spread_updated - timedelta(microseconds=1)), PriceUnavailable)
    derived = first(store, spread_updated)
    assert derived.price == Decimal("42") and derived.available_at == spread_updated


def test_missing_quarter_cites_only_reachable_anchor_failures_and_spreads():
    store = ArchiveS3()
    croatian = landed(store, "entsoe", "HR")
    failure = AttemptOutcome(**croatian.model_dump(include={"publisher", "dataset", "delivery_day", "zone", "attempt_id"}),
                             completed_at=T, outcome="failed", rows=0, diagnostic="Croatian request failed")
    save_diagnostic(store, "test", failure)
    publish(store, "entsoe", "FR", [price("30", "FR")])
    link = publish(store, "jao", "CORE", [spread("DE-LU", "HR", "2")])
    cutoff = T + timedelta(seconds=1)
    connected, disconnected, *_ = resolve_day(store, "test", DAY, ("DE-LU",), cutoff, FORECAST_POLICY)
    assert set(connected.attempt_ids) == {croatian.attempt_id, link.attempt_id}
    assert "Croatian request failed" in connected.reason
    assert disconnected.attempt_ids == () and "Croatian request failed" not in disconnected.reason
    assert read_day_diagnostics(store, "test", DAY, cutoff) == [failure]


def test_empty_direct_edition_explains_only_visible_and_reachable_missing_prices() -> None:
    store = ArchiveS3()
    empty = publish(store, "smard", "DE-LU", [])
    assert first(store, T).attempt_ids == ()
    cutoff = T + timedelta(seconds=1)
    missing = first(store, cutoff)
    assert isinstance(missing, PriceUnavailable)
    assert missing.attempt_ids == (empty.attempt_id,)

    link = publish(store, "jao", "CORE", [spread("DE-LU", "AT", "2")])
    connected, disconnected, *_ = resolve_day(store, "test", DAY, ("AT",), cutoff, FORECAST_POLICY)
    assert isinstance(connected, PriceUnavailable)
    assert set(connected.attempt_ids) == {empty.attempt_id, link.attempt_id}
    assert disconnected.attempt_ids == ()
