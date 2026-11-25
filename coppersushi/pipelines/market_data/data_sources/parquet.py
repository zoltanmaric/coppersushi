"""Encode and verify publisher editions at the Parquet boundary."""
from collections.abc import Sequence
from io import BytesIO

import polars as pl

from coppersushi.pipelines.market_data.edition_models import (
    ObservationTable, PriceRow, PriceTable, SpreadRow, SpreadTable,
)
from coppersushi.pipelines.market_data.response_models import ResponseReceipt
from coppersushi.pipelines.market_day import MarketDay

SCHEMA_VERSION = "1"
_EDITION_METADATA = {"schema_version": SCHEMA_VERSION, "auction": "SDAC", "unit": "EUR/MWh"}


def encode_table(receipt: ResponseReceipt, rows: Sequence[PriceRow | SpreadRow]) -> bytes:
    """Validate market identity, native intervals, row keys and storage types before writing."""
    model = _table_model(receipt)
    _validate_rows(receipt, rows)
    schema = {name: column.dtype.type for name, column in model.to_schema().columns.items()}
    frame = pl.DataFrame([row.model_dump() for row in rows], schema=schema)
    model.validate(frame)
    buffer = BytesIO()
    frame.write_parquet(buffer, metadata={**_EDITION_METADATA, "receipt": receipt.model_dump_json()})
    return buffer.getvalue()


def decode_table(data: bytes) -> tuple[ResponseReceipt, list[PriceRow | SpreadRow]]:
    """Recover an edition using the same schema and market rules enforced at write time."""
    metadata = pl.read_parquet_metadata(data)
    if any(metadata.get(key) != expected for key, expected in _EDITION_METADATA.items()) or "receipt" not in metadata:
        raise ValueError("Incorrect Parquet edition metadata")
    receipt = ResponseReceipt.model_validate_json(metadata["receipt"])
    model = _table_model(receipt)
    frame = pl.read_parquet(data)
    model.validate(frame)
    row_type = PriceRow if model is PriceTable else SpreadRow
    rows = [row_type.model_validate(row) for row in frame.iter_rows(named=True)]
    _validate_rows(receipt, rows)
    return receipt, rows


def _validate_rows(receipt: ResponseReceipt, rows: Sequence[PriceRow | SpreadRow]) -> None:
    valid_starts = frozenset(MarketDay.on(receipt.delivery_day).market_time_units())
    for row in rows:
        if row.interval not in valid_starts:
            raise ValueError(f"Interval {row.interval} is outside the native market grid for {receipt.delivery_day}")
        if isinstance(row, SpreadRow):
            if receipt.publisher != "jao" or row.origin == row.destination:
                raise ValueError("Invalid spread for this publisher receipt")
        elif receipt.publisher == "jao" or row.zone != receipt.zone:
            raise ValueError(f"Price zone {row.zone} does not match {receipt.zone}")


def _table_model(receipt: ResponseReceipt) -> type[ObservationTable]:
    return SpreadTable if receipt.publisher == "jao" else PriceTable
