"""Security verification rejects policies that protect only part of the bucket."""
import json
from pathlib import Path
import unittest

from forecasts.storage import requires_tls


class StorageTests(unittest.TestCase):
    def test_tls_policy_covers_every_principal_operation_and_resource(self):
        policies = json.loads((Path(__file__).parent / "fixtures/bucket-policies.json").read_text())
        self.assertTrue(requires_tls(policies["complete"], "fixture-bucket"))
        for name in ("delete_only", "bucket_only", "specific_principal", "extra_condition"):
            with self.subTest(name=name):
                self.assertFalse(requires_tls(policies[name], "fixture-bucket"))


if __name__ == "__main__":
    unittest.main()
