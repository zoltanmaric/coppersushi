"""Scheduled publication inputs and outcomes."""
from datetime import timedelta
from pydantic import AwareDatetime, BaseModel, ConfigDict
from coppersushi.market_day import MARKET_TZ, MarketDay


class PublicationJob(BaseModel):
    """Scheduled instant pins the delivery day across delayed executions and retries."""
    model_config = ConfigDict(extra='forbid')
    started_at: AwareDatetime

    @property
    def day(self) -> MarketDay:
        return MarketDay.on(self.started_at.astimezone(MARKET_TZ).date() + timedelta(days=1))


class PublicationResult(BaseModel):
    """Readiness drives the workflow's wait loop; unexpected failures still raise."""
    ready: bool
    day: str


