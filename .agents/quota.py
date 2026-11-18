"""Record a quota tool response with `python3 .agents/quota.py record` on JSON stdin.

The default log is ~/.local/state/agent-quota/usage.csv. Save changes in window or
availability, decreases from the saved value, increases of at least one percentage
point, or an observation after an hour when polled. Summaries always use the live
reading. Window start is nominal (reset minus duration); coverage reports only
actual observations, with no assumed zero-usage baseline. Rates describe that
coverage, not a forecast; the agent chooses the model.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import fcntl
import json
import os
from pathlib import Path
import sys
from typing import TypedDict


class UsageWindow(TypedDict):
    """Usage and reset time for one available quota window."""

    windowDurationMins: int
    usedPercent: int | float
    resetsAt: int


QuotaWindows = tuple[UsageWindow | None, UsageWindow | None]
RESET_JITTER_SECONDS = 2
MIN_SAVE_CHANGE_PERCENTAGE_POINTS = 1
MAX_SAVE_GAP = timedelta(hours=1)


class BurnShape(TypedDict):
    """Earlier/later observed rates, split near mid-coverage; not predicted acceleration."""

    splitAt: str
    earlierRatePercentagePointsPerHour: float
    laterRatePercentagePointsPerHour: float


class WindowSummary(TypedDict):
    """Quota headroom and observed rates for an agent to judge model affordability."""

    remainingPercent: int | float
    resetsAt: int
    windowElapsedPercent: float
    observedFirstAt: str | None
    observedLastAt: str | None
    observedCount: int
    observedDurationSeconds: float
    burnRatePercentagePointsPerHour: float | None
    secondsUntilReset: float
    sustainableRatePercentagePointsPerHour: float | None
    shape: BurnShape | None


@dataclass(frozen=True)
class SavedBucket:
    """Latest persisted snapshot of a quota bucket."""

    at: datetime
    windows: QuotaWindows


@dataclass(frozen=True)
class TimedUsage:
    """Used percentage measured at a specific time."""

    at: datetime
    used_percent: int | float

    def rate_to(self, later: TimedUsage) -> float:
        hours = (later.at - self.at).total_seconds() / 3600
        return (later.used_percent - self.used_percent) / hours


def parse_window(value: object, name: str) -> UsageWindow | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object or null")

    duration = value.get("windowDurationMins")
    percent = value.get("usedPercent")
    resets_at = value.get("resetsAt")
    if duration is not None and (type(duration) is not int or duration <= 0):
        raise ValueError(f"{name}.windowDurationMins must be a positive integer")
    if percent is not None and (type(percent) not in (int, float) or not 0 <= percent <= 100):
        raise ValueError(f"{name}.usedPercent must be a number from 0 to 100")
    if resets_at is not None and (type(resets_at) is not int or not 0 < resets_at <= 253402300799):
        raise ValueError(f"{name}.resetsAt must be a Unix timestamp in seconds")
    if duration is None or percent is None or resets_at is None:
        return None
    return UsageWindow(windowDurationMins=duration, usedPercent=percent, resetsAt=resets_at)


def parse_reading(value: object) -> tuple[str, dict[str, QuotaWindows]]:
    if not isinstance(value, dict):
        raise ValueError("Quota response must be an object")
    account = value.get("accountId")
    if not isinstance(account, str) or not account.strip():
        raise ValueError("accountId must be a nonempty string")

    buckets = value.get("rateLimitsByLimitId")
    if buckets is None:
        legacy = value.get("rateLimits")
        if legacy is None:
            return account, {}
        if not isinstance(legacy, dict):
            raise ValueError("rateLimits must be an object or null")
        bucket_id = legacy.get("limitId")
        if not isinstance(bucket_id, str) or not bucket_id.strip():
            raise ValueError("rateLimits.limitId must be a nonempty string")
        buckets = {bucket_id: legacy}
    if not isinstance(buckets, dict):
        raise ValueError("rateLimitsByLimitId must be an object or null")

    windows = {}
    for bucket, limits in buckets.items():
        if not isinstance(bucket, str) or not bucket.strip():
            raise ValueError("Quota bucket ID must be a nonempty string")
        if not isinstance(limits, dict):
            raise ValueError("Quota bucket must be an object")
        windows[bucket] = (
            parse_window(limits.get("primary"), "primary"),
            parse_window(limits.get("secondary"), "secondary"),
        )
    return account, windows


HEADER = (
    "observedAt", "accountId", "limitId",
    "primaryWindowDurationMins", "primaryUsedPercent", "primaryResetsAt",
    "secondaryWindowDurationMins", "secondaryUsedPercent", "secondaryResetsAt",
)


def window_cells(window: UsageWindow | None) -> tuple[str, str, str]:
    if window is None:
        return "", "", ""
    return str(window["windowDurationMins"]), str(window["usedPercent"]), str(window["resetsAt"])


def window_from_cells(cells: list[str]) -> UsageWindow | None:
    duration, percent, resets_at = cells
    if not any(cells):
        return None
    return parse_window(
        {"windowDurationMins": int(duration), "usedPercent": json.loads(percent), "resetsAt": int(resets_at)},
        "Stored quota window",
    )


def window_start(window: UsageWindow) -> int:
    return window["resetsAt"] - window["windowDurationMins"] * 60


def same_window(first: UsageWindow, second: UsageWindow) -> bool:
    return (
        first["windowDurationMins"] == second["windowDurationMins"]
        and abs(first["resetsAt"] - second["resetsAt"]) <= RESET_JITTER_SECONDS
    )


def should_save(at: datetime, windows: QuotaWindows, previous: SavedBucket | None) -> bool:
    """Keep discontinuities, accumulated usage increases and hourly observations when polled."""

    if previous is None or at - previous.at >= MAX_SAVE_GAP:
        return True
    for current, saved in zip(windows, previous.windows):
        if current is None or saved is None:
            if current is not saved:
                return True
        else:
            if (
                not same_window(current, saved)
                or current["usedPercent"] < saved["usedPercent"]
                or Decimal(str(current["usedPercent"])) - Decimal(str(saved["usedPercent"]))
                >= MIN_SAVE_CHANGE_PERCENTAGE_POINTS
            ):
                return True
    return False


def collect_observation(
    observations: list[TimedUsage], at: datetime, reading: UsageWindow | None, current: UsageWindow,
) -> None:
    if (
        reading is not None
        and same_window(reading, current)
        and window_start(current) <= at.timestamp() < current["resetsAt"]
    ):
        observations.append(TimedUsage(at, reading["usedPercent"]))


def summarize_window(
    current: UsageWindow, observed_at: datetime, observations: list[TimedUsage],
) -> WindowSummary:
    collect_observation(observations, observed_at, current, current)
    run: list[TimedUsage] = []
    for observation in sorted(observations, key=lambda sample: sample.at):
        if run and observation.used_percent < run[-1].used_percent:
            run.clear()
        if run and observation.at == run[-1].at:
            run[-1] = observation
        else:
            run.append(observation)

    first = run[0] if run else None
    last = run[-1] if run else None
    duration = 0.0
    burn_rate = None
    shape = None
    if first and last and first.at < last.at:
        span = last.at - first.at
        duration = span.total_seconds()
        burn_rate = first.rate_to(last)
        if len(run) >= 3:
            midpoint = first.at + span / 2
            split = min(run[1:-1], key=lambda sample: abs(sample.at - midpoint))
            shape = BurnShape(
                splitAt=split.at.isoformat(timespec="microseconds"),
                earlierRatePercentagePointsPerHour=first.rate_to(split),
                laterRatePercentagePointsPerHour=split.rate_to(last),
            )

    remaining = 100 - current["usedPercent"]
    observed_epoch = observed_at.timestamp()
    starts_at = window_start(current)
    duration_seconds = current["windowDurationMins"] * 60
    elapsed_seconds = min(duration_seconds, max(0, observed_epoch - starts_at))
    seconds_until_reset = max(0.0, round(current["resetsAt"] - observed_epoch, 6))
    sustainable_rate = remaining * 3600 / seconds_until_reset if seconds_until_reset else None
    return WindowSummary(
        remainingPercent=remaining,
        resetsAt=current["resetsAt"],
        windowElapsedPercent=100 * elapsed_seconds / duration_seconds,
        observedFirstAt=first.at.isoformat(timespec="microseconds") if first else None,
        observedLastAt=last.at.isoformat(timespec="microseconds") if last else None,
        observedCount=len(run),
        observedDurationSeconds=duration,
        burnRatePercentagePointsPerHour=burn_rate,
        secondsUntilReset=seconds_until_reset,
        sustainableRatePercentagePointsPerHour=sustainable_rate,
        shape=shape,
    )


def record(value: object, log_path: Path) -> dict[str, dict[str, WindowSummary | None]]:
    account, windows = parse_reading(value)
    if not windows:
        return {}

    log_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    observations: dict[str, tuple[list[TimedUsage], list[TimedUsage]]] = {
        bucket: ([], []) for bucket in windows
    }
    saved: dict[str, SavedBucket] = {}
    descriptor = os.open(log_path, os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, "a+", encoding="utf-8", newline="") as log:
        fcntl.flock(log.fileno(), fcntl.LOCK_EX)
        observed_at = datetime.now(timezone.utc)
        log.seek(0)
        reader = csv.reader(log, strict=True)
        header = next(reader, None)
        if header is not None and tuple(header) != HEADER:
            raise ValueError("Unexpected quota CSV header")
        for row in reader:
            if len(row) != len(HEADER):
                raise ValueError("Invalid quota CSV row")
            bucket = row[2]
            if row[1] != account or bucket not in windows:
                continue
            at = datetime.fromisoformat(row[0])
            if at.tzinfo is None:
                raise ValueError("Stored observation time must have a UTC offset")
            if at > observed_at:
                continue
            prior_windows = window_from_cells(row[3:6]), window_from_cells(row[6:9])
            saved[bucket] = SavedBucket(at, prior_windows)
            for prior, current, samples in zip(prior_windows, windows[bucket], observations[bucket]):
                if current is not None:
                    collect_observation(samples, at, prior, current)

        observed_iso = observed_at.isoformat(timespec="microseconds")
        new_rows = [
            [observed_iso, account, bucket, *window_cells(pair[0]), *window_cells(pair[1])]
            for bucket, pair in windows.items()
            if should_save(observed_at, pair, saved.get(bucket))
        ]
        if new_rows:
            log.seek(0, os.SEEK_END)
            if log.tell():
                log.seek(log.tell() - 1)
                if log.read(1) not in ("\n", "\r"):
                    log.write("\n")
            writer = csv.writer(log)
            if header is None:
                writer.writerow(HEADER)
            writer.writerows(new_rows)
    return {
        bucket: {
            name: summarize_window(current, observed_at, samples) if current is not None else None
            for name, current, samples in zip(("primary", "secondary"), pair, observations[bucket])
        }
        for bucket, pair in windows.items()
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Read a get_usage_limits JSON response from stdin. Store material quota updates "
            "and print usage and observed trends for each reported current window."
        ),
        epilog="Invalid input or a log error exits with status 1 and a message on stderr.",
    )
    parser.add_argument("command", choices=("record",))
    parser.add_argument(
        "--log",
        type=Path,
        default=Path("~/.local/state/agent-quota/usage.csv"),
        help="CSV log path (default: %(default)s)",
    )
    args = parser.parse_args()
    try:
        summaries = record(json.load(sys.stdin), args.log.expanduser())
    except (ValueError, OSError, RuntimeError, csv.Error) as error:
        parser.exit(1, f"{parser.prog}: {error}\n")
    print(json.dumps(summaries))


if __name__ == "__main__":
    main()
