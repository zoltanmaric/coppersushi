"""Issue-time availability shared by normalized input revisions."""
from datetime import datetime

import polars as pl


def available_at(deadline: datetime, *, live: bool) -> pl.Expr:
    """Require timely updates and receipts at the inclusive, timezone-aware cutoff.

    Historical replay accepts an explicitly assumed or documented publication time.
    For witnessed revisions, the receipt must precede or equal
    the cutoff. Live issuance requires this receipt for every source.
    """
    if deadline.utcoffset() is None:
        raise ValueError("Source selection requires a timezone-aware cutoff")
    update = pl.col("source_update_utc")
    evidence = pl.col("timing_evidence")
    timely_receipt = pl.col("retrieved_at_utc") <= deadline
    receipt_required = pl.lit(live) | (evidence == "witnessed")
    return (evidence.is_in(["witnessed", "documented", "assumed"])
            & (update.is_null() | (update <= deadline))
            & (~receipt_required | timely_receipt.fill_null(False)))
