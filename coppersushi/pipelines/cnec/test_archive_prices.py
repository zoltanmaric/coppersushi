"""Archived prices reach the complete regional table and retain private evidence."""
from datetime import timedelta
from decimal import Decimal
import json
from unittest.mock import Mock
from uuid import UUID

import pytest

from coppersushi.pipelines.cnec.data_sources import archive_prices, bundles
from coppersushi.pipelines.cnec.models import DayBundle, MarketInterval
from coppersushi.pipelines.cnec.spread_prices import SOURCE
from coppersushi.pipelines.market_data.resolution import (
    CNEC_POLICY, DerivedPrice, Evidence, PriceUnavailable, PublishedPrice,
)
from coppersushi.pipelines.market_day import MarketDay


def test_complete_region_retains_an_anchored_price_and_private_decision(monkeypatch):
    day = MarketDay.on("2026-11-20")
    cutoff = day.start_time_utc - timedelta(hours=8)
    client = Mock()
    monkeypatch.setattr(archive_prices.boto3, "client", lambda service: client)
    monkeypatch.setattr(bundles.cache, "_client", lambda: client)
    results = []
    for time in day.market_time_units().to_pydatetime():
        for zone in archive_prices.ARCHIVE_ZONES:
            derived = zone == "SK"
            anchor = Evidence(
                publisher="entsoe", attempt_id=UUID(int=1), edition_key="source-edition",
                interval=time, zone="DE-LU" if derived else zone, destination=None, value=Decimal(100),
                received_at=cutoff, visible_at=cutoff, source_updated_at=None, upstream_source=None,
            )
            evidence = (anchor,)
            if derived:
                evidence += (Evidence(
                    publisher="jao", attempt_id=UUID(int=2), edition_key="spread-edition",
                    interval=time, zone="DE-LU", destination="SK", value=Decimal(10),
                    received_at=cutoff, visible_at=cutoff, source_updated_at=None, upstream_source=None,
                ),)
            model = DerivedPrice if derived else PublishedPrice
            results.append(model(
                interval=time, zone=zone, price=Decimal(110 if derived else 100),
                policy_id=CNEC_POLICY.id, evidence=evidence,
            ))
    resolver = Mock(return_value=results)
    monkeypatch.setattr(archive_prices, "resolve_day", resolver)
    prices, decision = archive_prices.load_day(day, "archive", cutoff)
    resolver.assert_called_once_with(client, "archive", day.date, archive_prices.ARCHIVE_ZONES, cutoff, CNEC_POLICY)
    assert len(prices) == 1152
    assert set(prices.loc[prices.zone.eq("SK"), "price"]) == {110}
    assert set(prices.loc[prices.zone.eq("SK"), "source"]) == {SOURCE}
    assert "DE" in set(prices.zone) and "DE-LU" not in set(prices.zone)

    interval = MarketInterval(index=0, label="00:00", prices={"DE": 100}, constraints=[],
                              alpha=1, caps=[], notes=[])
    bundle = DayBundle(day=day.date, labels=["00:00"], zones=[], elements={}, intervals=[interval],
                       price_range=[100, 110], price_decision=decision)
    writes = Mock()
    monkeypatch.setattr(bundles, "put_once", writes.private)
    client.put_object = writes.public
    generation = bundles.publish(bundle, "browser", archive_bucket="archive")
    first, *public_writes = writes.mock_calls
    assert first.args[:3] == (client, "archive", f"market-data/decisions/cnec/{day.date}/{generation}.json")
    selected = json.loads(first.args[3])
    assert selected["policy"] == CNEC_POLICY.id
    slovakia = next(row for row in selected["prices"] if row["zone"] == "SK")
    assert [row["edition_key"] for row in slovakia["evidence"]] == ["source-edition", "spread-edition"]
    assert all(write.kwargs["Key"].startswith("data/cnec/") for write in public_writes)
    assert public_writes[-1].kwargs["Key"].endswith("/manifest.json")
    assert "price_decision" not in bundle.model_dump_json()

    resolver.return_value = [PriceUnavailable(zone="SK", interval=day.start_time_utc,
                                               policy_id=CNEC_POLICY.id, reason="No eligible anchor",
                                               attempt_ids=(UUID(int=2),))]
    with pytest.raises(archive_prices.RegionalPricesUnavailable, match="SK.*No eligible anchor") as rejected:
        archive_prices.load_day(day, "archive", cutoff)
    assert rejected.value.missing == resolver.return_value
    assert rejected.value.decision.prices == resolver.return_value
