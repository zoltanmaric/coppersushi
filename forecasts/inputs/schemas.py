"""Normalized source revisions and their versioned Parquet storage contracts."""
from typing import Annotated

import pandera.polars as pa
from pandera.errors import SchemaError
import polars as pl
import pyarrow as arrow

from forecasts.inputs.input_config import FIELDS
from forecasts.inputs.input_types import Report

VERSION = 1
UTC = Annotated[pl.Datetime, "us", "UTC"]


class VersionedInput(pa.DataFrameModel):
    """A retained version, its delivery time, availability evidence and raw origin."""

    valid_utc: UTC
    source_update_utc: UTC = pa.Field(nullable=True)
    retrieved_at_utc: UTC = pa.Field(nullable=True)
    timing_evidence: str = pa.Field(isin=["witnessed", "documented", "assumed", "unknown"])
    version_id: str
    raw_key: str

    class Config:
        strict = True


class PriceVersions(VersionedInput):
    """A price revision for one delivery quarter, measured in EUR/MWh."""

    price_eur_mwh: float = pa.Field(nullable=True, metadata={"unit": "EUR/MWh"})

    class Config:
        unique = ["valid_utc", "version_id"]

    @pa.check("price_eur_mwh")
    def finite_prices(cls, data: pa.PolarsData) -> pl.LazyFrame:
        """Allow missing and negative prices, but reject NaN and infinity."""
        return data.lazyframe.select(pl.col("price_eur_mwh").is_finite())


class WeatherVersions(VersionedInput):
    """A weather forecast revision for a location, variable and valid time."""

    source_valid_utc: UTC
    location: str
    variable: str
    value: float = pa.Field(nullable=True)
    unit: str
    model: str
    lead_hours: pl.Int16
    data_kind: str

    class Config:
        unique = ["valid_utc", "location", "variable", "version_id"]

    @pa.check("value")
    def finite_values(cls, data: pa.PolarsData) -> pl.LazyFrame:
        """Allow missing observations but reject non-finite weather values."""
        return data.lazyframe.select(pl.col("value").is_finite())

    @pa.dataframe_check
    @classmethod
    def weather_units(cls, data: pa.PolarsData) -> pl.LazyFrame:
        """Require the provider's expected unit for each registered variable."""
        expected = pl.col("variable").replace_strict(FIELDS, default=pl.col("unit"))
        return data.lazyframe.select(pl.col("unit") == expected)


class DemandVersions(VersionedInput):
    """A load forecast revision for one area and delivery quarter."""

    area_code: str
    demand_mw: float = pa.Field(nullable=True, metadata={"unit": "MW"})

    class Config:
        unique = ["valid_utc", "area_code", "version_id"]

    @pa.check("demand_mw")
    def finite_values(cls, data: pa.PolarsData) -> pl.LazyFrame:
        """Allow missing observations but reject non-finite load values."""
        return data.lazyframe.select(pl.col("demand_mw").is_finite())


def describe(name: str) -> Report:
    """Describe the Pandera row key and the exact stored fields in the manifest."""
    return {"version": VERSION, "row_key": _MODELS[name].to_schema().unique, "columns": [
        {"name": f.name, "type": str(f.type), "nullable": f.nullable,
         "unit": f.metadata[b"unit"].decode() if f.metadata and b"unit" in f.metadata else None}
        for f in SCHEMAS[name]
    ]}


def validate(name: str, table: arrow.Table) -> arrow.Table:
    """Check the Parquet wire type and validate the actual normalized records."""
    if not table.schema.equals(SCHEMAS[name], check_metadata=True):
        raise ValueError(f"Schema mismatch: {name}")
    frame = pl.from_arrow(table)
    assert isinstance(frame, pl.DataFrame)
    try:
        _MODELS[name].validate(frame)
    except SchemaError as error:
        raise ValueError(f"Invalid {name}: {error}") from error
    return table


def _storage_schema(model: type[VersionedInput]) -> arrow.Schema:
    wire_types = {pl.String: arrow.string(), pl.Float64: arrow.float64(),
                  pl.Int16: arrow.int16(), pl.Datetime("us", "UTC"): arrow.timestamp("us", tz="UTC")}
    return arrow.schema([
        arrow.field(name, wire_types[column.dtype.type], nullable=column.nullable, metadata=column.metadata)
        for name, column in model.to_schema().columns.items()
    ])


_MODELS: dict[str, type[VersionedInput]] = {"prices": PriceVersions, "weather": WeatherVersions, "demand": DemandVersions}
SCHEMAS = {name: _storage_schema(model) for name, model in _MODELS.items()}
