import json
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


RECORDER = Path(__file__).resolve().parents[1] / "quota.py"
RESET = int(datetime.now(timezone.utc).timestamp()) + 3600


def window(percent, *, reset=RESET, duration=300):
    return {"usedPercent": percent, "windowDurationMins": duration, "resetsAt": reset}


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

    def seed_primary(self, observations):
        self.record(response())
        header = self.read_log()[0]
        with self.log.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(header)
            for at, quota in observations:
                writer.writerow([
                    at.isoformat(timespec="microseconds"), "test-account", "codex",
                    quota["windowDurationMins"], quota["usedPercent"], quota["resetsAt"], "", "", "",
                ])

    def read_log(self):
        with self.log.open(encoding="utf-8", newline="") as stream:
            return list(csv.reader(stream))

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
        summaries = self.record(payload)
        primary = summaries["codex"]["primary"]
        secondary = summaries["codex"]["secondary"]
        self.assertEqual(primary["remainingPercent"], 85)
        self.assertEqual(primary["observedCount"], 2)
        self.assertEqual(secondary["remainingPercent"], 70)
        self.assertEqual(secondary["observedCount"], 1)
        self.assertEqual(summaries["other-bucket"], {"primary": None, "secondary": None})
        self.assertEqual(primary["observedLastAt"], secondary["observedLastAt"])
        observed = datetime.fromisoformat(primary["observedLastAt"])
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
        self.assertEqual(self.record(payload)["legacy"]["primary"]["observedCount"], 1)
        del payload["rateLimitsByLimitId"]
        self.assertEqual(self.record(payload)["legacy"]["primary"]["observedCount"], 2)

    def test_incomplete_windows_leave_available_sibling(self):
        for incomplete in ({"usedPercent": 12, "resetsAt": RESET}, window(12) | {"resetsAt": None}):
            with self.subTest(incomplete=incomplete):
                payload = response(primary=incomplete)
                payload["rateLimitsByLimitId"]["codex"]["secondary"] = window(30)
                latest = self.record(payload)["codex"]
                self.assertIsNone(latest["primary"])
                self.assertEqual(latest["secondary"]["remainingPercent"], 70)

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
        header, *rows = self.read_log()
        self.assertEqual(len(rows), 8)
        self.assertEqual(sorted(int(row[header.index("primaryUsedPercent")]) for row in rows), list(range(8)))

    def test_append_after_missing_final_newline(self):
        self.record(response(primary=window(7)))
        self.log.write_bytes(self.log.read_bytes().rstrip(b"\r\n"))
        self.record(response(primary=window(8)))
        primary = self.record(response(primary=window(9)))["codex"]["primary"]
        self.assertEqual(primary["observedCount"], 3)
        self.assertEqual([row[4] for row in self.read_log()[1:]], ["7", "8", "9"])

    def test_dense_late_readings_preserve_the_baseline_and_temporal_split(self):
        now = datetime.now(timezone.utc)
        first = now - timedelta(hours=3)
        midpoint = now - timedelta(minutes=90)
        burst = now - timedelta(minutes=15)
        self.seed_primary([
            (first, window(10)),
            (midpoint, window(40)),
            *((burst + timedelta(seconds=i), window(50 + i / 10)) for i in range(105)),
        ])
        primary = self.record(response(primary=window(80)))["codex"]["primary"]
        self.assertEqual(primary["observedCount"], 108)
        self.assertEqual(datetime.fromisoformat(primary["observedFirstAt"]), first)
        last = datetime.fromisoformat(primary["observedLastAt"])
        observed_seconds = (last - first).total_seconds()
        seconds_until_reset = (datetime.fromtimestamp(RESET, timezone.utc) - last).total_seconds()
        self.assertEqual(primary["observedDurationSeconds"], observed_seconds)
        self.assertAlmostEqual(primary["burnRatePercentagePointsPerHour"], 70 * 3600 / observed_seconds)
        self.assertAlmostEqual(primary["secondsUntilReset"], seconds_until_reset, places=6)
        self.assertAlmostEqual(primary["sustainableRatePercentagePointsPerHour"], 20 * 3600 / seconds_until_reset)
        self.assertEqual(primary["remainingPercent"], 20)
        self.assertEqual(primary["resetsAt"], RESET)
        self.assertAlmostEqual(primary["windowElapsedPercent"], 100 * (1 - seconds_until_reset / 18000), places=2)
        shape = primary["shape"]
        self.assertEqual(datetime.fromisoformat(shape["splitAt"]), midpoint)
        self.assertEqual(shape["earlierRatePercentagePointsPerHour"], 20)
        later_seconds = (last - midpoint).total_seconds()
        self.assertAlmostEqual(shape["laterRatePercentagePointsPerHour"], 40 * 3600 / later_seconds)

    def test_only_matching_current_windows_contribute_and_reset_times_can_jitter(self):
        start = datetime.fromtimestamp(RESET - 300 * 60, timezone.utc)
        self.seed_primary([
            (start - timedelta(seconds=1), window(1)),
            (start, window(7, reset=RESET - 2)),
            (start + timedelta(minutes=1), window(45, reset=RESET - 3)),
            (start + timedelta(minutes=2), window(50, duration=60)),
            (start + timedelta(minutes=3), window(11, reset=RESET + 1)),
            (datetime.fromtimestamp(RESET, timezone.utc), window(17)),
        ])
        primary = self.record(response(primary=window(15)))["codex"]["primary"]
        self.assertEqual(primary["observedCount"], 3)
        self.assertEqual(datetime.fromisoformat(primary["observedFirstAt"]), start)

    def test_usage_decrease_starts_a_new_observed_run(self):
        now = datetime.now(timezone.utc)
        after_decrease = now - timedelta(hours=2)
        self.seed_primary([
            (now - timedelta(hours=3), window(80)),
            (after_decrease, window(4)),
            (now - timedelta(hours=1), window(7)),
        ])
        primary = self.record(response(primary=window(10)))["codex"]["primary"]
        self.assertEqual(primary["observedCount"], 3)
        self.assertEqual(datetime.fromisoformat(primary["observedFirstAt"]), after_decrease)
        self.assertAlmostEqual(primary["burnRatePercentagePointsPerHour"], 3, places=2)
        primary = self.record(response(primary=window(2)))["codex"]["primary"]
        self.assertEqual(primary["observedCount"], 1)
        self.assertIsNone(primary["burnRatePercentagePointsPerHour"])

    def test_one_timestamp_has_no_burn_rate_and_two_have_no_shape(self):
        primary = self.record(response(primary=window(9)))["codex"]["primary"]
        self.assertEqual(primary["observedCount"], 1)
        self.assertEqual(primary["observedFirstAt"], primary["observedLastAt"])
        self.assertEqual(primary["observedDurationSeconds"], 0)
        self.assertIsNone(primary["burnRatePercentagePointsPerHour"])
        self.assertIsNone(primary["shape"])

        at = datetime.now(timezone.utc) - timedelta(hours=1)
        self.seed_primary([(at, window(3)), (at, window(5))])
        primary = self.record(response(primary=window(9)))["codex"]["primary"]
        self.assertEqual(primary["observedCount"], 2)
        self.assertAlmostEqual(primary["burnRatePercentagePointsPerHour"], 4, places=2)
        self.assertIsNone(primary["shape"])

    def test_expired_reading_has_no_sustainable_rate(self):
        primary = self.record(response(primary=window(10, reset=RESET - 7200)))["codex"]["primary"]
        self.assertEqual(primary["remainingPercent"], 90)
        self.assertEqual(primary["secondsUntilReset"], 0)
        self.assertEqual(primary["observedCount"], 0)
        self.assertIsNone(primary["observedFirstAt"])
        self.assertIsNone(primary["observedLastAt"])
        self.assertIsNone(primary["sustainableRatePercentagePointsPerHour"])

    def test_small_increases_stay_live_and_accumulate_against_the_last_saved_reading(self):
        first = self.record(response(primary=window(0.4)))["codex"]["primary"]
        saved = self.log.read_bytes()
        for percent in (0.4, 0.5, 0.9):
            current = self.record(response(primary=window(percent)))["codex"]["primary"]
            self.assertEqual(current["remainingPercent"], 100 - percent)
            self.assertGreater(current["observedLastAt"], first["observedLastAt"])
            self.assertEqual(current["observedCount"], 2)
            self.assertEqual(self.log.read_bytes(), saved)
        self.record(response(primary=window(1.4)))
        self.assertEqual([row[4] for row in self.read_log()[1:]], ["0.4", "1.4"])

    def test_exact_decimal_point_increases_are_saved(self):
        for start, end in ((7.2, 8.2), (0.14, 1.14)):
            with self.subTest(start=start):
                self.record(response(bucket=str(start), primary=window(start)))
                self.record(response(bucket=str(start), primary=window(end)))
                self.assertEqual(self.read_log()[-1][4], str(end))

    def test_hourly_observation_is_saved_when_polled(self):
        now = datetime.now(timezone.utc)
        self.seed_primary([(now - timedelta(hours=1), window(7))])
        current = self.record(response(primary=window(7)))["codex"]["primary"]
        self.assertEqual(current["observedCount"], 2)
        self.assertEqual(current["burnRatePercentagePointsPerHour"], 0)
        self.assertEqual([row[4] for row in self.read_log()[1:]], ["7", "7"])

    def test_new_reset_and_small_usage_decrease_are_saved(self):
        self.record(response(primary=window(7)))
        self.record(response(primary=window(7, reset=RESET + 2)))
        self.assertEqual(len(self.read_log()), 2)
        self.record(response(primary=window(7, reset=RESET + 3)))
        self.record(response(primary=window(6.75, reset=RESET + 3)))
        self.record(response(primary=window(7, reset=RESET + 3)))
        self.assertEqual([(row[4], int(row[5])) for row in self.read_log()[1:]], [
            ("7", RESET), ("7", RESET + 3), ("6.75", RESET + 3),
        ])

    def test_secondary_usage_and_availability_changes_are_saved(self):
        payload = response(primary=window(7))
        limits = payload["rateLimitsByLimitId"]["codex"]
        self.record(payload)
        limits["secondary"] = window(20)
        self.record(payload)
        limits["secondary"] = window(21)
        self.record(payload)
        limits["secondary"] = None
        self.record(payload)
        self.assertEqual([row[7] for row in self.read_log()[1:]], ["", "20", "21", ""])


if __name__ == "__main__":
    unittest.main()
