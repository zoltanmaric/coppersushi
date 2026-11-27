"""Select and audit frozen and witnessed DE–LU prices at each training decision."""
from collections.abc import Iterator
from datetime import date, datetime, timedelta
import json
from typing import TYPE_CHECKING, cast

from botocore.exceptions import BotoCoreError, ClientError
from pandera.typing.polars import DataFrame
import polars as pl
import pyarrow as pa

from coppersushi.pipelines.market_data.data_sources.parquet import SCHEMA_VERSION
from coppersushi.pipelines.market_data.data_sources.prices import resolve_day
from coppersushi.pipelines.market_data.edition_models import object_visible_by
from coppersushi.pipelines.market_data.resolution import FORECAST_POLICY, ConflictingPrices, PriceUnavailable
from forecasts.inputs.fresh_sources import required_lag_dates
from forecasts.inputs.input_config import PRICE_LAG_DAYS
from forecasts.inputs.prices import PriceHistory, PriceVersions, read_prices, select_history
from forecasts.market import BERLIN, cutoff, quarters

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

UTC_TIME = pl.Datetime("us", "UTC")
_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    "valid_utc": UTC_TIME, "price_eur_mwh": pl.Float64, "source": pl.String,
    "policy_id": pl.String, "snapshot_id": pl.String, "version_id": pl.String,
    "raw_key": pl.String, "timing_evidence": pl.String, "source_update_utc": UTC_TIME,
    "retrieved_at_utc": UTC_TIME, "archive_evidence": pl.String, "reason": pl.String,
}


def _days(start: date, stop: date) -> Iterator[date]:
    for index in range((stop - start).days):
        yield start + timedelta(days=index)


class TrainingEditions:
    """Quarterly training inputs pinned to a snapshot or a witnessed free-source edition."""

    def __init__(self, client: "S3Client", bucket: str, snapshot_id: str, prices: pa.Table,
                 start: date, fit_day: date, *, history_start: date | None = None) -> None:
        self.client = client
        self.bucket = bucket
        self.snapshot_id = snapshot_id
        self.start = start
        self.fit_day = fit_day
        self.history_start = history_start or (start - timedelta(days=max(PRICE_LAG_DAYS)))
        if self.history_start > start or start >= fit_day or not snapshot_id:
            raise ValueError("Training needs a pinned snapshot and an ordered history, start and fit day")
        self._prices = read_prices(prices).with_columns(
            pl.col("valid_utc").dt.convert_time_zone(str(BERLIN)).dt.date().alias("_day")
        ).partition_by("_day", include_key=False, as_dict=True)
        self._cache: dict[tuple[date, datetime, bool], pl.DataFrame] = {}
        self._visible: dict[date, datetime] = {}
        # One listing per namespace covers absent historical days and editions backfilled
        # after their historical deadlines. Do not treat failed listings as empty coverage.
        self._inventory_error = ""
        try:
            self._inventory()
        except (ClientError, BotoCoreError, ValueError, OSError) as error:
            self._inventory_error = f"Archive inventory failed in {bucket}: {error}"

    def _inventory(self) -> None:
        paginator = self.client.get_paginator("list_objects_v2")
        for prefix in (f"market-data/editions/v{SCHEMA_VERSION}/", "market-data/outcomes/"):
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                for item in page.get("Contents", []):
                    key = item["Key"]
                    if key.endswith("/"):
                        continue
                    day = date.fromisoformat(key.removeprefix(prefix).split("/", 1)[0])
                    visible = object_visible_by(item["LastModified"])
                    if day not in self._visible or self._visible[day] > visible:
                        self._visible[day] = visible

    def _select(self, day: date, deadline: datetime, live: bool) -> pl.DataFrame:
        key = (day, deadline, live)
        if key in self._cache:
            return self._cache[key]
        reason = self._inventory_error
        archive = {}
        if not reason and day in self._visible and self._visible[day] <= deadline:
            try:
                archive = {result.interval: result for result in resolve_day(
                    self.client, self.bucket, day, ("DE-LU",), deadline, FORECAST_POLICY)}
            except (ClientError, BotoCoreError, ValueError, OSError) as error:
                reason = f"Archive resolution failed for {day} at {deadline.isoformat()}: {error}"
                if isinstance(error, ConflictingPrices):
                    reason += " " + json.dumps([item.model_dump(mode="json") for item in error.evidence])
        grid = list(quarters(day, day + timedelta(days=1)))
        frozen = {}
        snapshot_errors: dict[datetime, str] = {}
        candidates = self._prices.get((day,))
        if not reason and not live and candidates is not None:
            needed = [t for t in grid if t not in archive or isinstance(archive[t], PriceUnavailable)]
            if needed:
                versions = cast(DataFrame[PriceVersions], candidates.filter(pl.col("valid_utc").is_in(needed)))
                try:
                    selected = select_history(versions, day + timedelta(days=1), deadline)
                    frozen = {row["valid_utc"]: row for row in selected.iter_rows(named=True)}
                except ValueError:
                    # An ambiguous frozen quarter must not hide the remaining coverage.
                    for (interval,), group in versions.partition_by("valid_utc", as_dict=True).items():
                        try:
                            selected = select_history(cast(DataFrame[PriceVersions], group),
                                                      day + timedelta(days=1), deadline)
                        except ValueError as error:
                            snapshot_errors[interval] = (
                                f"Snapshot {self.snapshot_id} selection failed for {day}, "
                                f"{interval.isoformat()} at cutoff {deadline.isoformat()}: {error}; "
                                f"candidate versions {group['version_id'].to_list()}")
                        else:
                            frozen.update((row["valid_utc"], row) for row in selected.iter_rows(named=True))
        rows = []
        for interval in grid:
            row: dict[str, object] = {"valid_utc": interval, "policy_id": FORECAST_POLICY.id}
            result = archive.get(interval)
            if reason:
                row.update(source="error", reason=reason)
            elif interval in snapshot_errors:
                row.update(source="error", reason=snapshot_errors[interval], snapshot_id=self.snapshot_id)
                if result:
                    row["archive_evidence"] = result.model_dump_json()
            elif result is not None and not isinstance(result, PriceUnavailable):
                row.update(source="archive", price_eur_mwh=float(result.price),
                           archive_evidence=result.model_dump_json())
            else:
                absence = result.reason if result else "No archive edition visible by cutoff"
                if result:
                    row["archive_evidence"] = result.model_dump_json()
                version = frozen.get(interval)
                if version is not None:
                    row.update({name: version[name] for name in (
                        "price_eur_mwh", "raw_key", "version_id", "timing_evidence",
                        "source_update_utc", "retrieved_at_utc")})
                    row["snapshot_id"] = self.snapshot_id
                if version is not None and version["price_eur_mwh"] is not None:
                    row.update(source="snapshot", reason=absence)
                else:
                    unavailable = ("live selection requires a witnessed edition" if live
                                   else f"no eligible non-null price in snapshot {self.snapshot_id}")
                    row.update(source="missing", reason=f"{absence}; {unavailable}")
            rows.append(row)
        frame = pl.DataFrame(rows, schema=_SCHEMA)
        self._cache[key] = frame
        return frame

    def feature_audit(self, day: date, deadline: datetime, *, live: bool = False) -> pl.DataFrame:
        """Select the four physical lag-day grids at this exact decision time."""
        if deadline.utcoffset() is None or deadline > cutoff(day):
            raise ValueError("Feature cutoff must be aware and at or before the issue deadline")
        return pl.concat([self._select(lag_day, deadline, live) for lag_day in required_lag_dates(day)]
                         ).with_columns(pl.lit(day).alias("delivery_day"),
                                        pl.lit(deadline).cast(UTC_TIME).alias("cutoff"),
                                        pl.lit("feature").alias("purpose"))

    def _label_audit(self, day: date, deadline: datetime) -> pl.DataFrame:
        frames = [self._select(source_day, deadline, False).with_columns(
            pl.lit("reference" if source_day < self.start else "label").alias("purpose"))
            for source_day in _days(self.history_start, day)]
        return pl.concat(frames).with_columns(pl.lit(day).alias("delivery_day"),
                                              pl.lit(deadline).cast(UTC_TIME).alias("cutoff"))

    def audit(self) -> pl.DataFrame:
        """Inventory every required historical decision and fit-time warmup/label quarter."""
        frames = [self.feature_audit(day, cutoff(day)) for day in _days(self.start, self.fit_day)]
        return pl.concat([*frames, self._label_audit(self.fit_day, cutoff(self.fit_day))], how="diagonal")

    def price_history(self, day: date, deadline: datetime, *, live: bool = False,
                      earliest_day: date | None = None) -> DataFrame[PriceHistory]:
        if earliest_day is None:
            if live or deadline != cutoff(day):
                raise ValueError("Training labels require the historical issue cutoff")
            frame = self._label_audit(day, deadline)
        else:
            frame = self.feature_audit(day, deadline, live=live).filter(
                pl.col("valid_utc").dt.convert_time_zone(str(BERLIN)).dt.date() >= earliest_day)
        failed = frame.filter(pl.col("source").is_in(["error", "missing"]))
        if failed.height:
            row = failed.row(0, named=True)
            raise ValueError(f"{failed.height} unavailable quarters for {day} at {deadline.isoformat()}; "
                             f"first {row['valid_utc']}: {row['reason']}")
        return PriceHistory.validate(frame.select("valid_utc", "price_eur_mwh"))
