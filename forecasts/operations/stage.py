"""Publish the exact input versions for a deployed forecast configuration."""
import argparse
import hashlib
from pathlib import Path

import boto3

from forecasts.inputs.snapshot import read_local
from forecasts.operations.artifacts import Artifacts
from forecasts.operations.jobs import Settings

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--image-digest", required=True)
    parser.add_argument("--archive-bucket")
    parser.add_argument("--replay")
    parser.add_argument("--publication-time")
    args = parser.parse_args()
    store = Artifacts(boto3.client("s3"), args.bucket, None)
    manifest, _ = read_local(args.snapshot)
    names = [entry["file"] for entry in manifest["files"].values()] + ["manifest.json"]
    files = {name: store.retain(f"snapshots/{manifest['snapshot_id']}/{name}", (args.snapshot / name).read_bytes())
             for name in names}
    config = args.config.read_bytes()
    cfg = store.retain(f"inputs/{hashlib.sha256(config).hexdigest()}/config.json", config)
    settings = Settings(bucket=args.bucket, snapshot_id=manifest["snapshot_id"], snapshot_files=files,
                        config=cfg, image_digest=args.image_digest, replay=args.replay,
                        archive_bucket=args.archive_bucket, publication_time=args.publication_time)
    raw = settings.model_dump_json().encode()
    print(store.retain(f"inputs/{hashlib.sha256(raw).hexdigest()}/settings.json", raw).model_dump_json())


if __name__ == "__main__":
    main()
