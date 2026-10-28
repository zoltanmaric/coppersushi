"""Configuration boundaries reject malformed settings and preserve saved artifacts."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import date
import json
from pathlib import Path
import pickle
import unittest

from forecasts.config import RunConfig, SnapshotId
from forecasts.features import FEATURES

CONFIG = Path(__file__).resolve().parents[1] / "run-config.json"


class ConfigTests(unittest.TestCase):
    def test_saved_json_round_trip_and_metaflow_serialization(self) -> None:
        saved = json.loads(CONFIG.read_text())
        saved["features"] = FEATURES
        saved = json.loads(json.dumps(saved, sort_keys=True))
        config = RunConfig.from_dict(saved)
        self.assertIs(type(config.train_start), date)
        self.assertIsInstance(config.snapshot_id, SnapshotId)
        self.assertEqual(json.loads(json.dumps(config.to_dict())), saved)
        self.assertEqual(pickle.loads(pickle.dumps(config)), config)
        with self.assertRaises(FrozenInstanceError):
            config.train_start = date(2000, 1, 1)  # type: ignore[misc]  # Exercise frozen runtime enforcement.
        with self.assertRaises(TypeError):
            config.features["prices"] = ()  # type: ignore[index]  # Exercise read-only mapping enforcement.
        with self.assertRaises(ValueError):
            replace(config, train_start="2025-10-15")  # type: ignore[arg-type]  # Reject invalid runtime input.
        with self.assertRaises(ValueError):
            replace(config, evaluation_start=date(2025, 1, 1))

    def test_rejects_invalid_dates_ids_contracts_and_numeric_settings(self) -> None:
        original = json.loads(CONFIG.read_text())
        changes = [
            (("history_start",), "20251001"),
            (("train_start",), "2027-01-01"),
            (("end_exclusive",), "2026-10-02"),
            (("snapshot_id",), "not-a-digest"),
            (("schema_version",), True),
            (("refit",), "daily"),
            (("quantiles",), [.1, .5, .9]),
            (("features",), {"prices": ["target"]}),
            (("unexpected",), 1),
            (("reference_min_errors",), 0),
            (("catboost", "iterations"), True),
            (("catboost", "depth"), 17),
            (("catboost", "learning_rate"), "0.05"),
            (("catboost", "random_strength"), float("nan")),
            (("catboost", "loss_function"), "RMSE"),
            (("catboost", "unknown_option"), 1),
            (("bootstrap", "block_days"), 0),
            (("tolerance", "absolute"), -1),
        ]
        for path, value in changes:
            with self.subTest(path=path, value=value):
                data = deepcopy(original)
                target = data
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                with self.assertRaises(ValueError):
                    RunConfig.from_dict(data)


if __name__ == "__main__":
    unittest.main()
