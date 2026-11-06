"""Publisher receipt evidence for a complete Core market day."""
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict

from coppersushi.market_day import MarketDay


class PublicationReceipt(BaseModel):
    """JAO monitoring status for one publication and delivery-day midnight."""
    model_config = ConfigDict(extra='ignore')
    businessDayUtc: AwareDatetime
    page: str
    status: Literal['Expected', 'Pending', 'Received', 'Spanning/DFP']


class PublicationNotReady(RuntimeError):
    """Required publisher evidence or interval inputs have not all arrived."""


REQUIRED_PUBLICATIONS = ('Active FB Constraints', 'Allocation Constraints',
                         'Alpha factor from MCP', 'Net Position')


def require_received(day: MarketDay, receipts: list[PublicationReceipt]) -> None:
    """Sparse constraint rows are meaningful only after the publisher marks receipt."""
    current = [r for r in receipts if r.businessDayUtc == day.start_time_utc]
    pages = [r.page for r in current]
    if len(pages) != len(set(pages)):
        raise ValueError('Duplicate JAO monitoring publications for the delivery day')
    received = {r.page for r in current if r.status == 'Received'}
    missing = [page for page in REQUIRED_PUBLICATIONS if page not in received]
    if missing:
        raise PublicationNotReady(f'{day.date}: waiting for {", ".join(missing)}')
