"""Grade the reader's retrieved edition against a frozen local forecast."""
import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from forecasts.config import RunConfig
from forecasts.market import quarters
from forecasts.provenance import digest


def compare(oracle: dict, actual: dict, config: RunConfig) -> dict[str, float]:
    for field in ("delivery_date", "input_cutoff", "snapshot_id", "training_snapshot_id", "fit_month", "method", "quantiles"):
        if actual[field] != oracle[field]:
            raise ValueError(f"{field} differs from pinned local issue")
    if actual["method"] != config.model_method or actual["quantiles"] != list(config.quantiles):
        raise ValueError("Expected registered CatBoost method and quantiles")
    day = date.fromisoformat(oracle["delivery_date"])
    expected = [q.isoformat() for q in quarters(day, day + timedelta(days=1))]
    for forecast in (oracle, actual):
        if [row["delivery_utc"] for row in forecast["quarters"]] != expected:
            raise ValueError("Incomplete or incorrect UTC delivery grid")
    differences = {}
    for method in ("prices", "reference"):
        local, cloud = (np.asarray([row[method] for row in forecast["quarters"]], dtype=float)
                        for forecast in (oracle, actual))
        if any(values.shape != (len(expected), 5) or not np.isfinite(values).all() for values in (local, cloud)):
            raise ValueError(f"Expected five finite {method} prices per quarter")
        np.testing.assert_allclose(cloud, local, atol=config.tolerance.absolute, rtol=config.tolerance.relative)
        differences[method] = float(np.max(np.abs(cloud - local)))
    return differences


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("oracle", "actual", "config"):
        parser.add_argument("--" + arg, required=True, type=Path)
    parser.add_argument("--oracle-sha256", required=True)
    args = parser.parse_args()
    if digest(args.oracle) != args.oracle_sha256:
        parser.error("Local oracle checksum mismatch")
    print(json.dumps(compare(json.loads(args.oracle.read_bytes()), json.loads(args.actual.read_bytes()),
                             RunConfig.from_dict(json.loads(args.config.read_bytes())))))
