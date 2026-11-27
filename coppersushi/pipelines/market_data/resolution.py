"""Resolve one archive snapshot under an explicit consumer policy, without external I/O."""
from collections import defaultdict, deque
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Sequence
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict

from coppersushi.pipelines.market_data.edition_models import PriceRow, SpreadRow, PublishedEdition
from coppersushi.pipelines.market_day import MarketDay


type PolicyId = Literal["cnec-v2", "forecast-free-v1"]


class SourcePolicy(BaseModel):
    """Pinned ordered direct publishers and permission to reconstruct missing quarters."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    id: PolicyId
    direct: tuple[str, ...]
    allow_spreads: bool

    @property
    def publishers(self) -> frozenset[str]:
        return frozenset((*self.direct, "jao") if self.allow_spreads else self.direct)


# Version 2 follows the original Critical Elements price selection, which predates this archive.
CNEC_POLICY = SourcePolicy(id="cnec-v2", direct=("entsoe", "smard", "electricity_maps"), allow_spreads=True)
FORECAST_POLICY = SourcePolicy(id="forecast-free-v1", direct=("entsoe", "smard"), allow_spreads=True)


class Evidence(BaseModel):
    """One source row, its original receipt, and the edition that exposed it to the reader."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    publisher: str
    attempt_id: UUID
    edition_key: str
    interval: AwareDatetime
    zone: str
    destination: str | None
    value: Decimal
    received_at: AwareDatetime
    visible_at: AwareDatetime
    source_created_at: AwareDatetime | None = None
    source_updated_at: AwareDatetime | None
    upstream_source: str | None


    @property
    def available_at(self) -> datetime:
        """Earliest cutoff that admits this row under the archive and publisher clocks."""
        return max(self.visible_at, self.source_updated_at or self.visible_at)


class ResolvedPrice(BaseModel):
    """The EUR/MWh auction outcome with replayable source evidence, in derivation order."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    interval: AwareDatetime
    zone: str
    policy_id: PolicyId
    price: Decimal
    evidence: tuple[Evidence, ...]

    @property
    def available_at(self) -> datetime:
        return max(row.available_at for row in self.evidence)


class PublishedPrice(ResolvedPrice):
    kind: Literal["published"] = "published"


class DerivedPrice(ResolvedPrice):
    """The first evidence row is the observed anchor, followed by all signed spread rows."""

    kind: Literal["derived"] = "derived"


class PriceUnavailable(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["unavailable"] = "unavailable"
    zone: str
    interval: AwareDatetime
    policy_id: PolicyId
    reason: str
    attempt_ids: tuple[UUID, ...]
    connected_zones: tuple[str, ...] = ()


class ConflictingPrices(ValueError):
    """Eligible observations imply different prices for the same interval."""

    def __init__(self, zone: str, interval: datetime, evidence: Sequence[Evidence], *,
                 implied_price: Decimal | None = None) -> None:
        self.evidence = tuple(evidence)
        self.zone = zone
        self.interval = interval
        self.implied_price = implied_price
        detail = f" (anchored spread implies {implied_price} EUR/MWh)" if implied_price is not None else ""
        super().__init__(f"Conflicting SDAC prices for {zone} at {interval.isoformat()}{detail}: "
                         + ", ".join(f"{row.zone}/{row.destination or 'direct'} {row.value} "
                                     f"from {row.publisher} attempt {row.attempt_id}" for row in evidence))


type PriceResult = PublishedPrice | DerivedPrice | PriceUnavailable
type Table = tuple[PublishedEdition, Sequence[PriceRow | SpreadRow]]


def resolve_editions(day: date, zones: tuple[str, ...], cutoff: datetime, policy: SourcePolicy,
                     tables: Sequence[Table]) -> list[PriceResult]:
    """Resolve each requested zone and native interval using only eligible editions."""
    if cutoff.utcoffset() is None:
        raise ValueError("A replay cutoff requires a timezone")
    direct: dict[datetime, dict[str, list[Evidence]]] = defaultdict(lambda: defaultdict(list))
    spreads: dict[datetime, list[Evidence]] = defaultdict(list)
    versions: dict[tuple[datetime, str, str, str | None], list[Evidence]] = defaultdict(list)
    empty_direct: dict[str, set[UUID]] = defaultdict(set)
    for edition, rows in tables:
        receipt = edition.receipt
        if receipt.delivery_day != day or edition.available_at > cutoff:
            continue
        if receipt.publisher not in policy.publishers:
            continue
        if not rows and receipt.publisher in policy.direct:
            empty_direct[receipt.zone].add(receipt.attempt_id)
        for row in rows:
            evidence = Evidence(
                publisher=receipt.publisher, attempt_id=receipt.attempt_id, edition_key=edition.key,
                interval=row.interval, zone=row.zone if isinstance(row, PriceRow) else row.origin,
                destination=None if isinstance(row, PriceRow) else row.destination,
                value=row.price if isinstance(row, PriceRow) else row.difference,
                source_created_at=row.source_created_at, source_updated_at=row.source_updated_at,
                upstream_source=row.upstream_source,
                received_at=receipt.received_at, visible_at=edition.available_at,
            )
            if evidence.available_at > cutoff:
                continue
            versions[row.interval, receipt.publisher, evidence.zone, evidence.destination].append(evidence)
    for (interval, _, zone, destination), observations in versions.items():
        latest = _latest(observations)
        if destination is None:
            direct[interval][zone].extend(latest)
        else:
            spreads[interval].extend(latest)

    results: list[PriceResult] = []
    for time in MarketDay.on(day).market_time_units():
        for zone in zones:
            results.append(_resolve_interval(zone, time.to_pydatetime(), policy, direct[time],
                                             spreads[time], empty_direct))
    return results


def _latest(observations: list[Evidence]) -> list[Evidence]:
    """Select per-interval revisions; a partial response never withdraws an unrelated quarter."""
    stamped = [row for row in observations if row.source_updated_at is not None]
    observed = [row for row in observations if row.source_updated_at is None]
    if stamped:
        newest_update = max(row.source_updated_at for row in stamped if row.source_updated_at is not None)
        stamped = [row for row in stamped if row.source_updated_at == newest_update]
    if observed:
        newest_receipt = max(row.received_at for row in observed)
        observed = [row for row in observed if row.received_at == newest_receipt]
        # Between stamped and unstamped editions, receipt is the common ordering evidence.
        if stamped:
            stamped_receipt = max(row.received_at for row in stamped)
            if stamped_receipt > newest_receipt:
                observed = []
            elif stamped_receipt < newest_receipt:
                stamped = []
    # Keep conflicting values sharing a revision; equivalent retries need just one witness.
    distinct: dict[Decimal, Evidence] = {}
    for row in sorted(stamped + observed, key=lambda row: (row.visible_at, str(row.attempt_id))):
        distinct.setdefault(row.value, row)
    return list(distinct.values())


def _published(zone: str, interval: datetime, policy: SourcePolicy, candidates: list[Evidence]) -> PublishedPrice:
    if len({row.value for row in candidates}) != 1:
        raise ConflictingPrices(zone, interval, candidates)
    chosen = min(candidates, key=lambda row: (policy.direct.index(row.publisher), str(row.attempt_id)))
    return PublishedPrice(zone=zone, interval=interval, policy_id=policy.id,
                          price=chosen.value, evidence=(chosen,))


def _resolve_interval(target: str, interval: datetime, policy: SourcePolicy,
                      direct: dict[str, list[Evidence]], spreads: list[Evidence],
                      empty_direct: dict[str, set[UUID]]) -> PriceResult:
    published = None
    if target in direct:
        published = _published(target, interval, policy, direct[target])
        if not spreads or any(row.publisher != "electricity_maps" for row in direct[target]):
            return published

    # Walk from the requested zone so unrelated components cannot block this result.
    # offset[z] is price[z] minus price[target]. Each path preserves the published orientation.
    edges: dict[str, list[tuple[str, Decimal, Evidence]]] = defaultdict(list)
    for row in spreads:
        assert row.destination is not None
        edges[row.zone].append((row.destination, row.value, row))
        edges[row.destination].append((row.zone, -row.value, row))
    paths: dict[str, tuple[Decimal, tuple[Evidence, ...]]] = {target: (Decimal(0), ())}
    queue = deque([target])
    anchors: list[DerivedPrice] = []
    while queue:
        zone = queue.popleft()
        offset, path = paths[zone]
        # An anchor can also lead to farther anchors.
        if zone != target and zone in direct:
            anchor = _published(zone, interval, policy, direct[zone])
            implied = anchor.price - offset
            chain = anchor.evidence + path[::-1]
            if published is not None and published.price != implied:
                raise ConflictingPrices(target, interval, published.evidence + chain, implied_price=implied)
            anchors.append(DerivedPrice(zone=target, interval=interval, policy_id=policy.id,
                                        price=implied, evidence=chain))
        for other, delta, row in sorted(edges[zone], key=lambda edge: edge[0]):
            value = offset + delta
            if other not in paths:
                paths[other] = value, path + (row,)
                queue.append(other)
            elif paths[other][0] != value:
                raise ConflictingPrices(target, interval, paths[other][1] + path + (row,))

    if published is not None:
        return published
    if not anchors:
        attempts = {row.attempt_id for zone in paths for _, _, row in edges[zone]}
        for zone in paths:
            attempts.update(empty_direct.get(zone, ()))
        return PriceUnavailable(zone=target, interval=interval, policy_id=policy.id,
                                attempt_ids=tuple(sorted(attempts)), connected_zones=tuple(sorted(paths.keys() - {target})),
                                reason="No eligible direct price or connected eligible absolute anchor")
    if len({candidate.price for candidate in anchors}) != 1:
        raise ConflictingPrices(target, interval, [row for candidate in anchors for row in candidate.evidence])
    return min(anchors, key=lambda result: (len(result.evidence), policy.direct.index(result.evidence[0].publisher),
                                            result.evidence[0].zone))
