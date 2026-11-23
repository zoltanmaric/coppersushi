"""Read source records under the historical or live availability contract."""
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from typing import cast

from pandera.typing.polars import DataFrame
import polars as pl
import pyarrow as pa

from forecasts.inputs.availability import available_at
from forecasts.inputs.input_config import FIELDS, WEATHER_LOCATIONS
from forecasts.inputs.input_types import DemandVersion, PriceSeries, Row
from forecasts.inputs.prices import PriceHistory, PriceVersions, latest_versions, read_prices, select_history
from forecasts.inputs.schemas import SCHEMAS
from forecasts.inputs.sources import COUNTRY
from forecasts.market import BERLIN, UTC, issue_deadline

LOCATIONS = {location.name.lower() for location in WEATHER_LOCATIONS}


class InputReader:
    """Read retained price versions without building model features."""

    def __init__(self, tables: Mapping[str, pa.Table]) -> None:
        self._prices = read_prices(tables["prices"])

    def price_history(self, day: date, deadline: datetime, *, live: bool = False,
                      earliest_day: date | None = None) -> DataFrame[PriceHistory]:
        """Select prices for earlier delivery days available by the given cutoff."""
        candidates = self._prices
        if earliest_day is not None:
            candidates = cast(DataFrame[PriceVersions], candidates.filter(
                pl.col("valid_utc").dt.convert_time_zone(str(BERLIN)).dt.date() >= earliest_day))
        selected = select_history(candidates, day, deadline, live)
        return PriceHistory.validate(selected.select("valid_utc", "price_eur_mwh"))

    def realized_prices(self) -> PriceSeries:
        """Read the latest retained prices for retrospective scoring or diagnostics."""
        return dict(latest_versions(self._prices).select("valid_utc", "price_eur_mwh").iter_rows())


def select_records(tables: Mapping[str, pa.Table | list[Row]], day: date, live: bool = False, issue_time: datetime | None = None) -> dict[str, list[Row]]:
    """Select source versions eligible for a delivery day and its issue time."""
    deadline = issue_deadline(day, live, issue_time)
    records = {name: table.to_pylist() if hasattr(table, "to_pylist") else table for name, table in tables.items() if name != "prices"}
    selected = select_covariates(records, day, deadline, live)
    price_input = tables["prices"]
    price_table = price_input if isinstance(price_input, pa.Table) else pa.Table.from_pylist(price_input, schema=SCHEMAS["prices"])
    selected["prices"] = select_history(read_prices(price_table), day, deadline, live).to_dicts()
    return selected


def select_covariates(records: Mapping[str, list[Row]], day: date, deadline: datetime,
                       live: bool) -> dict[str, list[Row]]:
    """Read eligible weather and demand records for the archived-source diagnostic."""
    selected: dict[str, list[Row]] = {"weather": [], "demand": []}
    for row in _available_rows("weather", records["weather"], deadline, live):
        if (row["model"] != "icon_eu" or row["lead_hours"] != 48 or row["data_kind"] != "forecast"
                or row["location"] not in LOCATIONS or row["variable"] not in FIELDS
                or row["valid_utc"].astimezone(BERLIN).date() != day
                or row["source_valid_utc"] - timedelta(hours=48) > deadline):
            continue
        selected["weather"].append(row)
    for row in _available_rows("demand", records["demand"], deadline, live):
        if (row["area_code"] == COUNTRY and row["valid_utc"].astimezone(BERLIN).date() == day
                and row["source_update_utc"] is not None):
            selected["demand"].append(row)
    selected["weather"] = _latest_rows(selected["weather"], ["valid_utc", "location", "variable"], "value")
    return selected


def select_demand(versions: list[DemandVersion], deadline: datetime) -> tuple[float | None, datetime | None, str]:
    """Select the latest nonmissing version eligible by the issue deadline."""
    usable = [v for v in versions if v["updated"] is not None and v["updated"] <= deadline and v["value"] is not None
              and v.get("eligible_at_issue", True)]
    if usable:
        latest = max(v["updated"] for v in usable if v["updated"] is not None)
        selected = [v for v in usable if v["updated"] == latest]
        if len({v["value"] for v in selected}) != 1:
            raise ValueError("Conflicting demand values at the same update time")
        return selected[0]["value"], latest, "usable"
    reason = "absent" if not versions else "late_or_missing_update_or_value"
    return None, None, reason


def _available_rows(source: str, records: list[Row], deadline: datetime, live: bool) -> list[Row]:
    table = pa.Table.from_pylist(records, schema=SCHEMAS[source])
    frame = pl.from_arrow(table)
    assert isinstance(frame, pl.DataFrame)
    return frame.filter(available_at(deadline, live=live)).to_dicts()


def _latest_rows(rows: list[Row], keys: Sequence[str], value: str) -> list[Row]:
    """Keep latest weather versions, with the same tie rules as prices.

    Missing updates rank oldest. Reject conflicting values at any equal update,
    even if a newer revision supersedes them. Equal-value ties retain the last
    input record. Unlike demand selection, a missing value can be the latest.
    """
    selected: dict[tuple[object, ...], Row] = {}
    seen: dict[tuple[object, ...], object] = {}
    earliest = datetime.min.replace(tzinfo=UTC)
    for row in rows:
        key = tuple(row[k] for k in keys)
        revision = (*key, row["source_update_utc"])
        if revision in seen and seen[revision] != row[value]:
            raise ValueError("Conflicting source values at the same update time")
        seen[revision] = row[value]
        prior = selected.get(key)
        update = (row["source_update_utc"] is not None, row["source_update_utc"] or earliest)
        if prior is not None:
            previous = (prior["source_update_utc"] is not None, prior["source_update_utc"] or earliest)
            if update < previous:
                continue
        selected[key] = row
    return list(selected.values())
