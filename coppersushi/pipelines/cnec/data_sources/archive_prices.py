"""Read the complete Core zone table and preserve its private decision evidence."""
from datetime import datetime
from hashlib import sha256
from typing import cast

import boto3
import pandas as pd
from pandera.typing import DataFrame

from coppersushi.pipelines.cnec.models import RegionalPriceDecision
from coppersushi.pipelines.cnec.prices import IncompletePrices, check_complete
from coppersushi.pipelines.cnec.spread_prices import SOURCE
from coppersushi.pipelines.data_model.market import CORE_ZONES, ZonalPrices
from coppersushi.pipelines.market_data.data_sources.prices import resolve_day
from coppersushi.pipelines.data_sources.s3 import put_once
from coppersushi.pipelines.market_data.resolution import (
    CNEC_POLICY, DerivedPrice, PriceUnavailable, PublishedPrice,
)
from coppersushi.pipelines.market_day import MarketDay

ARCHIVE_ZONES = tuple("DE-LU" if zone == "DE" else zone for zone in CORE_ZONES)


class RegionalPricesUnavailable(IncompletePrices):
    """Failed regional selection with evidence for every affected zone and interval."""

    def __init__(self, decision: RegionalPriceDecision, missing: list[PriceUnavailable]) -> None:
        self.decision = decision
        self.missing = missing
        first = missing[0]
        super().__init__(
            f"{decision.day}: {len(missing)} unavailable archive zone intervals; "
            f"first {first.zone} at {first.interval.isoformat()} ({first.reason})"
        )


def load_day(day: MarketDay, bucket: str, cutoff: datetime) -> tuple[DataFrame[ZonalPrices], RegionalPriceDecision]:
    """Require one eligible absolute or anchored price for every zone interval."""
    resolved = resolve_day(boto3.client("s3"), bucket, day.date, ARCHIVE_ZONES, cutoff, CNEC_POLICY)
    missing = [result for result in resolved if isinstance(result, PriceUnavailable)]
    if missing:
        decision = RegionalPriceDecision(day=day.date, cutoff=cutoff, policy=CNEC_POLICY.id, prices=list(missing))
        raise RegionalPricesUnavailable(decision, missing)
    decision = RegionalPriceDecision(day=day.date, cutoff=cutoff, policy=CNEC_POLICY.id, prices=resolved)
    selected = cast(list[PublishedPrice | DerivedPrice], resolved)
    prices = ZonalPrices.validate(pd.DataFrame.from_records([
        (price.interval, "DE" if price.zone == "DE-LU" else price.zone, float(price.price),
         SOURCE if isinstance(price, DerivedPrice) else price.evidence[0].publisher)
        for price in selected
    ], columns=["interval", "zone", "price", "source"]))
    check_complete(prices, day, CORE_ZONES)
    return prices, decision


def retain_failed_decision(bucket: str, decision: RegionalPriceDecision) -> str:
    """Persist scheduled failures privately, outside the Step Functions result limit."""
    body = decision.model_dump_json().encode()
    key = f"market-data/decisions/cnec/{decision.day}/incomplete-{sha256(body).hexdigest()}.json"
    put_once(boto3.client("s3"), bucket, key, body)
    return key
