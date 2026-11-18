import json
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timedelta
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


RECORDER = Path(__file__).resolve().parents[1] / "quota.py"
RESET = 2_000_000_000


def window(percent):
    return {"usedPercent": percent, "windowDurationMins": 300, "resetsAt": RESET}


def response(account="test-account", bucket="codex", primary=None):
    return {"accountId": account, "rateLimitsByLimitId": {bucket: {"primary": primary}}}


class QuotaTest(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.log = Path(directory) / "quota" / "usage.csv"

    def run_cli(self, payload):
        return subprocess.run(
            [sys.executable, str(RECORDER), "record", "--log", str(self.log)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=10,
        )

    def record(self, payload):
        result = self.run_cli(payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_history_is_separate_by_account_and_bucket(self):
        self.record(response(primary=window(7)))
        self.record(response(account="other-account", primary=window(9)))
        self.record(response(bucket="other-bucket", primary=window(11)))
        prior_log = self.log.read_bytes()
        payload = response(primary=window(15))
        payload["rateLimitsByLimitId"]["codex"]["secondary"] = window(30)
        payload["rateLimitsByLimitId"]["codex"]["limitId"] = "ignored"
        payload["rateLimitsByLimitId"]["other-bucket"] = {"secondary": None}
        payload["email"] = "unused-personal-field"
        history = self.record(payload)
        self.assertEqual([item["primary"] for item in history["codex"]], [window(15), window(7)])
        self.assertEqual([item["secondary"] for item in history["codex"]], [window(30), None])
        self.assertEqual([item["primary"] for item in history["other-bucket"]], [None, window(11)])
        self.assertEqual(history["codex"][0]["observedAt"], history["other-bucket"][0]["observedAt"])
        observed = datetime.fromisoformat(history["codex"][0]["observedAt"])
        self.assertEqual(observed.utcoffset(), timedelta(0))
        self.assertTrue(self.log.read_bytes().startswith(prior_log))
        self.assertNotIn(b"unused-personal-field", self.log.read_bytes())
        self.assertEqual(self.log.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.log.stat().st_mode & 0o777, 0o600)

    def test_legacy_fallback_with_missing_or_null_bucket_map(self):
        payload = {
            "accountId": "test-account",
            "rateLimits": {"limitId": "legacy", "primary": window(7)},
            "rateLimitsByLimitId": {},
        }
        self.assertEqual(self.record(payload), {})
        self.assertFalse(self.log.exists())
        payload["rateLimitsByLimitId"] = None
        self.assertEqual(self.record(payload)["legacy"][0]["primary"], window(7))
        del payload["rateLimitsByLimitId"]
        self.assertEqual(self.record(payload)["legacy"][0]["primary"], window(7))

    def test_incomplete_windows_leave_available_sibling(self):
        for incomplete in ({"usedPercent": 12, "resetsAt": RESET}, window(12) | {"resetsAt": None}):
            with self.subTest(incomplete=incomplete):
                payload = response(primary=incomplete)
                payload["rateLimitsByLimitId"]["codex"]["secondary"] = window(30)
                latest = self.record(payload)["codex"][0]
                self.assertIsNone(latest["primary"])
                self.assertEqual(latest["secondary"], window(30))

    def test_invalid_windows_reject_whole_response(self):
        for field, invalid in (
            ("usedPercent", -1),
            ("usedPercent", 101),
            ("usedPercent", True),
            ("resetsAt", 1.5),
            ("resetsAt", RESET * 1_000),
            ("windowDurationMins", "300"),
        ):
            with self.subTest(field=field, invalid=invalid):
                payload = response(primary=window(7))
                payload["rateLimitsByLimitId"]["invalid"] = {"primary": window(10) | {field: invalid}}
                result = self.run_cli(payload)
                self.assertEqual(result.returncode, 1)
                self.assertIn(field, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertFalse(self.log.exists())

    def test_concurrent_writes_persist(self):
        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(lambda percent: self.record(response(primary=window(percent))), range(8)))
        history = self.record(response())["codex"]
        self.assertEqual(sorted(item["primary"]["usedPercent"] for item in history[1:]), list(range(8)))

    def test_append_after_missing_final_newline(self):
        self.record(response(primary=window(7)))
        self.log.write_bytes(self.log.read_bytes().rstrip(b"\r\n"))
        self.record(response(primary=window(8)))
        history = self.record(response(primary=window(9)))["codex"]
        self.assertEqual([item["primary"]["usedPercent"] for item in history], [9, 8, 7])

    def test_history_is_bounded(self):
        self.record(response(primary=window(7)))
        with self.log.open(encoding="utf-8", newline="") as stream:
            header, row = csv.reader(stream)
        with self.log.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(header)
            writer.writerows([["2000-01-01T00:00:00+00:00", *row[1:]]] * 105)
            writer.writerow(row)
        history = self.record(response(primary=window(15)))["codex"]
        self.assertEqual(len(history), 20)
        self.assertEqual([item["primary"] for item in history[:2]], [window(15), window(7)])


if __name__ == "__main__":
    unittest.main()
