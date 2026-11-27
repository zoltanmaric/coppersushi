"""Publish the exact input versions for a deployed forecast configuration."""
import argparse
import hashlib
import json
from pathlib import Path

from typing import TYPE_CHECKING

import boto3
from botocore.exceptions import ClientError

from forecasts.inputs.snapshot import read_local
from forecasts.operations.jobs import Settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


def put_pin(client: "S3Client", bucket: str, key: str, raw: bytes) -> dict[str, str]:
    digest = hashlib.sha256(raw).hexdigest()
    try:
        version = client.put_object(Bucket=bucket, Key=key, Body=raw, IfNoneMatch="*")["VersionId"]
    except ClientError as exc:
        if exc.response["ResponseMetadata"]["HTTPStatusCode"] != 412:
            raise
        existing = client.get_object(Bucket=bucket, Key=key)
        if hashlib.sha256(existing["Body"].read()).hexdigest() != digest:
            raise ValueError(f"Stored bytes disagree with content key {key}") from exc
        version = existing["VersionId"]
    if not version or version == "null":
        raise ValueError(f"Versioning is required for {key}")
    return {"bucket": bucket, "key": key, "sha256": digest, "version_id": version}


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
    client = boto3.client("s3")
    manifest, _ = read_local(args.snapshot)
    names = [entry["file"] for entry in manifest["files"].values()] + ["manifest.json"]
    files = {name: put_pin(client, args.bucket, f"snapshots/{manifest['snapshot_id']}/{name}", (args.snapshot / name).read_bytes())
             for name in names}
    config = args.config.read_bytes()
    cfg = put_pin(client, args.bucket, f"inputs/{hashlib.sha256(config).hexdigest()}/config.json", config)
    settings = Settings(bucket=args.bucket, snapshot_id=manifest["snapshot_id"], snapshot_files=files,
                        config=cfg, image_digest=args.image_digest, replay=args.replay,
                        archive_bucket=args.archive_bucket, publication_time=args.publication_time)
    raw = settings.model_dump_json().encode()
    print(json.dumps(put_pin(client, args.bucket, f"inputs/{hashlib.sha256(raw).hexdigest()}/settings.json", raw)))


if __name__ == "__main__":
    main()
