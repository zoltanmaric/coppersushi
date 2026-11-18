"""Record a quota tool response with `python3 .agents/quota.py record` on JSON stdin.

The default log is ~/.local/state/agent-quota/usage.csv.
"""

from __future__ import annotations

import argparse
from collections import deque
import csv
from datetime import datetime, timezone
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


def parse_reading(
    value: object,
) -> tuple[str, dict[str, tuple[UsageWindow | None, UsageWindow | None]]]:
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
    return UsageWindow(windowDurationMins=int(duration), usedPercent=json.loads(percent), resetsAt=int(resets_at))


def record(value: object, log_path: Path) -> dict[str, list[dict[str, object]]]:
    account, windows = parse_reading(value)
    if not windows:
        return {}

    log_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tails: dict[str, deque[list[str]]] = {bucket: deque(maxlen=20) for bucket in windows}
    descriptor = os.open(log_path, os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, "a+", encoding="utf-8", newline="") as log:
        fcntl.flock(log.fileno(), fcntl.LOCK_EX)
        observed_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        log.seek(0)
        reader = csv.reader(log, strict=True)
        header = next(reader, None)
        if header is not None and tuple(header) != HEADER:
            raise ValueError("Unexpected quota CSV header")
        for row in reader:
            if len(row) != len(HEADER):
                raise ValueError("Invalid quota CSV row")
            if row[1] == account and row[2] in tails:
                tails[row[2]].append(row)

        new_rows = []
        for bucket, (primary, secondary) in windows.items():
            row = [observed_at, account, bucket, *window_cells(primary), *window_cells(secondary)]
            new_rows.append(row)
            tails[bucket].append(row)
        history = {
            bucket: [
                {
                    "observedAt": row[0],
                    "primary": window_from_cells(row[3:6]),
                    "secondary": window_from_cells(row[6:9]),
                }
                for row in reversed(rows)
            ]
            for bucket, rows in tails.items()
        }
        log.seek(0, os.SEEK_END)
        if log.tell():
            log.seek(log.tell() - 1)
            if log.read(1) not in ("\n", "\r"):
                log.write("\n")
        writer = csv.writer(log)
        if header is None:
            writer.writerow(HEADER)
        writer.writerows(new_rows)
    return history


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Read a get_usage_limits JSON response from stdin. Store its quota windows "
            "and print up to 20 readings per reported bucket for that account, newest first."
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
        history = record(json.load(sys.stdin), args.log.expanduser())
    except (ValueError, OSError, RuntimeError, csv.Error) as error:
        parser.exit(1, f"{parser.prog}: {error}\n")
    print(json.dumps(history))


if __name__ == "__main__":
    main()
