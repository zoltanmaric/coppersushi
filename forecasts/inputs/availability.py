"""Issue-time availability shared by normalized input revisions."""
from datetime import datetime

import polars as pl


def _timing_checks(deadline: datetime, live: bool) -> dict[str, pl.Expr]:
    """List each timing condition that excludes a version at the inclusive cutoff.

    Historical replay accepts an explicitly assumed or documented publication time.
    For witnessed revisions, the receipt must precede or equal
    the cutoff. Live issuance requires this receipt for every source.
    """
    if deadline.utcoffset() is None:
        raise ValueError("Source selection requires a timezone-aware cutoff")
    update = pl.col("source_update_utc")
    evidence = pl.col("timing_evidence")
    receipt = pl.col("retrieved_at_utc")
    receipt_required = pl.lit(live) | (evidence == "witnessed")
    return {
        "unknown timing evidence": ~evidence.is_in(["witnessed", "documented", "assumed"]).fill_null(False),
        "source update after cutoff": update > deadline,
        "required receipt missing": receipt_required & receipt.is_null(),
        "receipt after cutoff": receipt_required & (receipt > deadline),
    }


def timing_rejections(deadline: datetime, *, live: bool) -> pl.Expr:
    """Explain each timing rule that excluded a candidate."""
    return pl.concat_list([
        pl.when(test).then(pl.lit(reason)) for reason, test in _timing_checks(deadline, live).items()
    ]).list.drop_nulls()


def available_at(deadline: datetime, *, live: bool) -> pl.Expr:
    """Select versions satisfying every timing condition."""
    return ~pl.any_horizontal([test.fill_null(False) for test in _timing_checks(deadline, live).values()])
