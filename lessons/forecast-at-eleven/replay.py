"""Replay the lesson's two illustrative editions for one delivery quarter."""

import argparse
from datetime import time

# Local publication times for the same DE–LU delivery quarter tomorrow.
EDITIONS = ((time(10, 36), 80), (time(11, 16), 65))


def edition_at(cutoff: time) -> tuple[time, int] | None:
    return next(
        (edition for edition in reversed(EDITIONS) if edition[0] <= cutoff), None
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "cutoff", type=time.fromisoformat, help="Local decision time, e.g. 11:00"
    )
    cutoff = parser.parse_args().cutoff
    edition = edition_at(cutoff)
    if edition is None:
        print("No edition was available.")
    else:
        published, price = edition
        print(f"Tomorrow 18:00–18:15 | published {published:%H:%M} | €{price}/MWh")
