"""The numerical acceptance check must detect errors in either method or the UTC grid."""
import copy
from datetime import date, timedelta
import json
from pathlib import Path
import unittest

from forecasts.config import RunConfig
from forecasts.market import quarters
from forecasts.operations.compare import compare


class ParityTests(unittest.TestCase):
    def test_mutations(self) -> None:
        config = RunConfig.from_dict(json.loads((Path(__file__).parents[2] / "run-config.json").read_bytes()))
        day = date(2026, 11, 24)
        oracle = dict(delivery_date=day.isoformat(), input_cutoff="2026-11-23T10:00:00Z",
                      snapshot_id=config.snapshot_id, training_snapshot_id=config.snapshot_id,
                      fit_month="2026-11-01", method=config.model_method, quantiles=list(config.quantiles),
                      quarters=[dict(delivery_utc=ts.isoformat(), prices=[0.0]*5, reference=[0.0]*5)
                                for ts in quarters(day, day + timedelta(days=1))])
        self.assertEqual(compare(oracle, oracle, config), {"prices": 0, "reference": 0})
        for field in ("prices", "reference"):
            for column in range(5):
                with self.subTest(method=field, column=column):
                    changed = copy.deepcopy(oracle)
                    changed["quarters"][-1][field][column] += 0.1
                    with self.assertRaises(AssertionError):
                        compare(oracle, changed, config)
        for modification in ("missing", "wrong_timestamp"):
            with self.subTest(modification=modification):
                changed = copy.deepcopy(oracle)
                if modification == "missing":
                    changed["quarters"].pop()
                else:
                    changed["quarters"][0]["delivery_utc"] = changed["quarters"][1]["delivery_utc"]
                with self.assertRaisesRegex(ValueError, "UTC delivery grid"):
                    compare(oracle, changed, config)
