"""The v1 snapshot wire format and manifest predate the shared Pandera models."""
import json
from pathlib import Path
import unittest

import pyarrow as pa

from forecasts.inputs.schemas import SCHEMAS, describe


class StorageContractTests(unittest.TestCase):
    def test_generated_contracts_match_frozen_v1_schemas_and_manifests(self) -> None:
        fixture = Path(__file__).parent / "fixtures/v1-input-contracts.json"
        expected = json.loads(fixture.read_text())
        self.assertEqual({name: describe(name) for name in SCHEMAS}, expected)
        wire_types = {"string": pa.string(), "double": pa.float64(), "int16": pa.int16(),
                      "timestamp[us, tz=UTC]": pa.timestamp("us", tz="UTC")}
        for source, contract in expected.items():
            fields = [pa.field(column["name"], wire_types[column["type"]], nullable=column["nullable"],
                               metadata={"unit": column["unit"]} if column["unit"] else None)
                      for column in contract["columns"]]
            with self.subTest(source=source):
                self.assertTrue(pa.schema(fields).equals(SCHEMAS[source], check_metadata=True))
