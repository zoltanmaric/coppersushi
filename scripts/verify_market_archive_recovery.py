"""Check the November 20 incident using a private archive, retained CNEC cache and official OKTE results."""
import argparse
import csv
import gzip
import io
import json
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import boto3

from coppersushi.pipelines.market_data.data_sources.editions import read_editions
from coppersushi.pipelines.market_data.edition_models import SpreadRow
from coppersushi.pipelines.market_data.resolution import (
    ConflictingPrices, DerivedPrice, PriceUnavailable, SourcePolicy, resolve_editions,
)

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


DAY = date(2026, 11, 20)
POLICY = SourcePolicy(id="nov20-incident-audit-v1", direct=("electricity_maps",), allow_spreads=True)


def verify_recovery(client: "S3Client", bucket: str, cutoff: datetime, cache_path: Path, okte_path: Path) -> None:
    """Compare the archive as read and a replay of the original direct-price gaps with independent truth."""
    cache = json.loads(gzip.decompress(cache_path.read_bytes()))
    expected = {}
    for cached in csv.DictReader(io.StringIO(cache[f"{DAY}.csv"])):
        key = ("DE-LU" if cached["zone"] == "DE" else cached["zone"], datetime.fromisoformat(cached["interval"]))
        if key in expected or cached["unit"] != "EUR/MWh":
            raise ValueError(f"Duplicate key or unexpected unit in retained cache at {key}")
        expected[key] = Decimal(cached["price"]), cached["source"] == "Derived from JAO border price spreads"
    settlements = {
        datetime.fromisoformat(entry["deliveryStart"]): entry["price"]
        for entry in json.loads(okte_path.read_text(), parse_float=Decimal)
        if entry["deliveryDay"] == DAY.isoformat() and entry["publicationStatus"] == "final"
    }
    if len(expected) != 1152 or len(settlements) != 96 or sum(derived for _, derived in expected.values()) != 384:
        raise ValueError("Expected 1,152 retained zone-quarters, 384 original gaps, and 96 final OKTE prices")
    zones = tuple(sorted({zone for zone, _ in expected}))
    tables = [(edition, rows) for edition, rows in read_editions(client, bucket, DAY, cutoff)
              if edition.receipt.publisher in (*POLICY.direct, "jao")]
    # Mask today's direct rows using the original cache's observed/derived designation.
    original_gaps = [(edition, [r for r in rows if isinstance(r, SpreadRow)
                                or ((r.zone, r.interval) in expected and not expected[r.zone, r.interval][1])])
                     for edition, rows in tables]
    counts: Counter[str] = Counter()
    for result in resolve_editions(DAY, zones, cutoff, POLICY, original_gaps):
        key = result.zone, result.interval
        value, was_derived = expected[key]
        if isinstance(result, PriceUnavailable) or result.price != value:
            raise ValueError(f"Retained gap pattern: unavailable or disagrees with retained CNEC at {key}")
        if isinstance(result, DerivedPrice) != was_derived:
            raise ValueError(f"Unexpected derivation at {key}")
        sources = [r.publisher for r in result.evidence]
        if sources[0] != "electricity_maps" or any(p != "jao" for p in sources[1:]):
            raise ValueError(f"Unexpected anchor or spread evidence at {key}")
        counts[result.kind] += 1
        if result.zone == "SK" and result.price != settlements[result.interval]:
            raise ValueError(f"Official OKTE price differs at {key}")
    print(f"Retained gap pattern: {counts['published']} published, {counts['derived']} derived, 96/96 OKTE matches.")

    # Reintroduce each disputed quote separately so the first conflict cannot hide the next eleven.
    rejected = set()
    for edition, rows in tables:
        for row in rows:
            if isinstance(row, SpreadRow):
                continue
            key = row.zone, row.interval
            value, was_derived = expected[key]
            if not was_derived or value == row.price:
                continue
            try:
                resolve_editions(DAY, (row.zone,), cutoff, POLICY, [*original_gaps, (edition, [row])])
            except ConflictingPrices as error:
                direct, anchor, *path = error.evidence
                if ((error.zone, error.interval) != key or error.implied_price != value
                        or direct.attempt_id != edition.receipt.attempt_id
                        or anchor.zone == row.zone or not path or any(edge.publisher != "jao" for edge in path)):
                    raise AssertionError(f"Unexpected conflict evidence for {key}") from error
                rejected.add(key)
            else:
                raise AssertionError(f"Accepted a disputed direct quote at {key}")
    if len(rejected) != 12:
        raise AssertionError(f"Expected twelve disputed zone-quarters, found {len(rejected)}")
    print("All 12 disputed direct quotes stopped with the quote, anchor and spread receipts.")


def main() -> None:
    """Run against an existing archive. All S3 requests are read-only."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--cutoff", type=datetime.fromisoformat, required=True)
    parser.add_argument("--core-cache", type=Path, required=True)
    parser.add_argument("--settlements", type=Path, required=True)
    args = parser.parse_args()
    verify_recovery(boto3.client("s3"), args.bucket, args.cutoff, args.core_cache, args.settlements)


if __name__ == "__main__":
    main()
