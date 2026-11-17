"""Frozen Polish export-cap investigation served independently of daily publications."""
from datetime import date, datetime, time, timedelta, UTC
from typing import Literal, Self
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, AwareDatetime, model_validator
from coppersushi.pipelines.market_day import MarketDay, MARKET_TZ
from coppersushi.pipelines.cnec.reserves import AvailableReserve


class BindingInterval(BaseModel):
    """One inferred binding quarter and its independently timed reserve observations."""
    model_config = ConfigDict(extra='forbid')
    utc: AwareDatetime
    date: date
    index: int = Field(ge=0, le=99)
    shadow: FiniteFloat = Field(gt=0.01)
    required: AvailableReserve
    procured: AvailableReserve
    cap: FiniteFloat = Field(ge=0)
    price: FiniteFloat

    @model_validator(mode='after')
    def consistent(self) -> Self:
        calendar = MarketDay.on(self.date).market_time_units()
        if self.index >= len(calendar) or calendar[self.index] != self.utc:
            raise ValueError('Quarter-hour identity does not match its market calendar')
        cutoff = datetime.combine(self.date-timedelta(days=1), time(10,30), MARKET_TZ).astimezone(UTC)
        for observation in (self.required,self.procured):
            if observation.published_at >= cutoff or min(observation.products)<0 or abs(sum(observation.products)-observation.mw)>1e-7:
                raise ValueError('Invalid pre-submission reserve observation')
        return self


class Coverage(BaseModel):
    """Observed population, with missing evidence kept outside both binding classes."""
    model_config = ConfigDict(extra='forbid')
    expected: int = Field(gt=0)
    observed: int = Field(ge=0)
    unknown: int = Field(ge=0)
    binding: int = Field(ge=0)
    nonbinding: int = Field(ge=0)
    shortfall_binding: int = Field(ge=0)
    no_shortfall_binding: int = Field(ge=0)


class SourceArtifact(BaseModel):
    """Content identity and known retrieval time; labels never contain local paths."""
    label: str
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    retrieved_at: AwareDatetime | None
    url: str | None


class Investigation(BaseModel):
    """Fixed study population and audited binding rows, pinned to map generations."""
    model_config = ConfigDict(extra='forbid')
    version: Literal[1] = 1
    start: date
    end: date
    coverage: Coverage
    rows: list[BindingInterval]
    generations: dict[str, str]
    sources: list[SourceArtifact]
    overlap_verified: int

    @model_validator(mode='after')
    def complete(self) -> Self:
        if self.end < self.start:
            raise ValueError('Reversed study window')
        days=[self.start+timedelta(days=i) for i in range((self.end-self.start).days+1)]
        c=self.coverage
        expected=sum(len(MarketDay.on(d).market_time_units()) for d in days)
        if c.expected!=expected or c.observed!=expected or c.unknown or c.binding+c.nonbinding!=expected:
            raise ValueError('Study coverage is incomplete; do not publish a complete-population graphic')
        if set(self.generations)!={str(d) for d in days}:
            raise ValueError('Map coverage does not cover every study day')
        if any(len(g)!=24 or any(c not in '0123456789abcdef' for c in g) for g in self.generations.values()):
            raise ValueError('Invalid immutable map generation')
        if len(self.rows)!=c.binding or len({r.utc for r in self.rows})!=len(self.rows):
            raise ValueError('Binding rows are missing or duplicated')
        if any(r.date not in days for r in self.rows):
            raise ValueError('Binding row outside study window')
        shortfall=sum(r.required.mw>r.procured.mw for r in self.rows)
        if c.shortfall_binding!=shortfall or c.no_shortfall_binding!=len(self.rows)-shortfall:
            raise ValueError('Graphic and table populations disagree')
        return self


class StudyManifest(BaseModel):
    """Pointer to one immutable fixed-window investigation artifact."""
    model_config = ConfigDict(extra='forbid')
    version: Literal[1]
    generation: str = Field(pattern=r'^[0-9a-f]{24}$')
