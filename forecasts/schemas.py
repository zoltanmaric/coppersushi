"""Versioned input schemas; UTC times remain distinct from availability evidence."""
import math
import pyarrow as pa
from forecasts.dataset import FIELDS

VERSION = 1
UTC_TIME = pa.timestamp("us", tz="UTC")


def field(name, kind, nullable=False, unit=None):
    return pa.field(name, kind, nullable=nullable, metadata={"unit": unit} if unit else None)


COMMON = [
    field("valid_utc", UTC_TIME),
    field("source_update_utc", UTC_TIME, True),
    field("retrieved_at_utc", UTC_TIME, True),
    field("timing_evidence", pa.string()),
    field("version_id", pa.string()),
    field("raw_key", pa.string()),
]
SCHEMAS = {
    "prices": pa.schema(COMMON + [field("price_eur_mwh", pa.float64(), True, "EUR/MWh")]),
    "weather": pa.schema(COMMON + [
        field("source_valid_utc", UTC_TIME), field("location", pa.string()),
        field("variable", pa.string()), field("value", pa.float64(), True),
        field("unit", pa.string()), field("model", pa.string()),
        field("lead_hours", pa.int16()), field("data_kind", pa.string()),
    ]),
    "demand": pa.schema(COMMON + [field("area_code", pa.string()), field("demand_mw", pa.float64(), True, "MW")]),
}
KEYS = {"prices": ["valid_utc", "version_id"], "weather": ["valid_utc", "location", "variable", "version_id"], "demand": ["valid_utc", "area_code", "version_id"]}


def describe(name):
    return {"version": VERSION, "row_key": KEYS[name], "columns": [
        {"name": f.name, "type": str(f.type), "nullable": f.nullable,
         "unit": f.metadata[b"unit"].decode() if f.metadata and b"unit" in f.metadata else None} for f in SCHEMAS[name]
    ]}


def validate(name, table):
    if not table.schema.equals(SCHEMAS[name], check_metadata=True):
        raise ValueError(f"Schema mismatch: {name}")
    for f in SCHEMAS[name]:
        if not f.nullable and table[f.name].null_count:
            raise ValueError(f"Required column contains null: {name}/{f.name}")
        if pa.types.is_floating(f.type) and any(v is not None and not math.isfinite(v) for v in table[f.name].to_pylist()):
            raise ValueError(f"Non-finite value: {name}/{f.name}")
    rows = table.to_pylist()
    keys = [tuple(r[k] for k in KEYS[name]) for r in rows]
    if len(set(keys)) != len(keys):
        raise ValueError(f"Duplicate input row key: {name}")
    if any(r["timing_evidence"] not in {"witnessed", "documented", "assumed", "unknown"} for r in rows):
        raise ValueError(f"Unknown timing evidence: {name}")
    if name == "weather" and any(r["variable"] in FIELDS and r["unit"] != FIELDS[r["variable"]] for r in rows):
        raise ValueError("Weather units differ from the source contract")
    return table
