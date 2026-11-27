"""Use reader-visible market editions for the free-source price baseline."""
from datetime import date, datetime

import boto3
import polars as pl
from pandera.typing.polars import DataFrame

from coppersushi.pipelines.market_data.data_sources.prices import resolve_day
from coppersushi.pipelines.market_data.resolution import FORECAST_POLICY, PriceUnavailable
from forecasts.inputs.fresh_sources import required_lag_dates
from forecasts.inputs.input_types import Report
from forecasts.inputs.prices import PriceHistory
from forecasts.market import BERLIN


class ArchiveHistory:
    """Selected price history and its exact edition evidence for one decision."""

    def __init__(self, bucket: str, day: date, cutoff: datetime) -> None:
        self.day = day
        self.cutoff = cutoff
        client = boto3.client("s3")
        self.results = [
            result
            for lag_day in required_lag_dates(day)
            for result in resolve_day(client, bucket, lag_day, ("DE-LU",), cutoff, FORECAST_POLICY)
        ]

    def input_manifest(self) -> Report:
        return {"policy": FORECAST_POLICY.id, "cutoff": self.cutoff.isoformat(),
                "prices": [result.model_dump(mode="json") for result in self.results]}

    def missing(self) -> list[PriceUnavailable]:
        return [result for result in self.results if isinstance(result, PriceUnavailable)]

    def price_history(self, day: date, deadline: datetime, *, live: bool = False,
                      earliest_day: date | None = None) -> DataFrame[PriceHistory]:
        """Expose archive selections to the historical feature code."""
        if day != self.day or deadline != self.cutoff:
            raise ValueError("Archived prices must use the delivery date and cutoff they were selected for")
        return PriceHistory.validate(pl.DataFrame(
            ((result.interval, float(result.price)) for result in self.results
             if not isinstance(result, PriceUnavailable)
             and (earliest_day is None or result.interval.astimezone(BERLIN).date() >= earliest_day)),
            schema={"valid_utc": pl.Datetime("us", "UTC"), "price_eur_mwh": pl.Float64},
            orient="row",
        ))
