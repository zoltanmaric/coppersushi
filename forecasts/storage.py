"""Provision private S3 storage and transfer verified, content-addressed snapshots.

AWS profiles belong to the user, never the repository. Account-specific state stays
under ignored data/forecasts; this module does not read or export credentials.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile

from forecasts.dataset import ROOT, PAYLOADS, digest, verify_payloads


def aws(profile, region, *args):
    result = subprocess.run(
        ["aws", "--profile", profile, "--region", region, "--no-cli-pager", "--output", "json", *args],
        check=True, capture_output=True, text=True, timeout=600,
        env={**os.environ, "AWS_RETRY_MODE": "standard", "AWS_MAX_ATTEMPTS": "3"},
    )
    return json.loads(result.stdout) if result.stdout.strip() else {}


def requires_tls(policy, bucket):
    resources = {f"arn:aws:s3:::{bucket}", f"arn:aws:s3:::{bucket}/*"}
    for statement in policy["Statement"]:
        action = statement.get("Action")
        resource = statement.get("Resource", [])
        if isinstance(resource, str):
            resource = [resource]
        condition = statement.get("Condition", {})
        if (statement.get("Effect") == "Deny"
                and statement.get("Principal") in ("*", {"AWS": "*"})
                and action in ("s3:*", ["s3:*"])
                and resources.issubset(resource)
                and condition in ({"Bool": {"aws:SecureTransport": "false"}}, {"Bool": {"aws:SecureTransport": False}})):
            return True
    return False


def verify_bucket(profile, region, bucket):
    block = aws(profile, region, "s3api", "get-public-access-block", "--bucket", bucket)["PublicAccessBlockConfiguration"]
    ownership = aws(profile, region, "s3api", "get-bucket-ownership-controls", "--bucket", bucket)
    encryption = aws(profile, region, "s3api", "get-bucket-encryption", "--bucket", bucket)
    versioning = aws(profile, region, "s3api", "get-bucket-versioning", "--bucket", bucket)
    status = aws(profile, region, "s3api", "get-bucket-policy-status", "--bucket", bucket)
    policy = json.loads(aws(profile, region, "s3api", "get-bucket-policy", "--bucket", bucket)["Policy"])
    if not all(block.get(k) is True for k in ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")):
        raise ValueError("S3 public access is not fully blocked")
    if ownership["OwnershipControls"]["Rules"] != [{"ObjectOwnership": "BucketOwnerEnforced"}]:
        raise ValueError("S3 ownership does not disable ACLs")
    if encryption["ServerSideEncryptionConfiguration"]["Rules"][0]["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"] != "AES256":
        raise ValueError("S3 encryption differs from template")
    if versioning.get("Status") != "Enabled" or status["PolicyStatus"]["IsPublic"]:
        raise ValueError("S3 versioning/privacy differs from template")
    if not requires_tls(policy, bucket):
        raise ValueError("S3 policy does not require TLS for every principal, operation and bucket/object resource")
    return {"public_access_blocked": True, "acl_disabled": True, "encryption": "AES256", "versioning": "Enabled", "tls_required": True}


def provision(args):
    print("Deploying forecast storage stack", flush=True)
    # Deploy's output is prose, unlike the other AWS CLI commands.
    subprocess.run(["aws", "--profile", args.profile, "--region", args.region, "--no-cli-pager",
                    "cloudformation", "deploy", "--template-file", str(ROOT / "forecasts/storage.json"),
                    "--stack-name", args.stack, "--no-fail-on-empty-changeset"], check=True, timeout=600)
    result = aws(args.profile, args.region, "cloudformation", "describe-stacks", "--stack-name", args.stack)
    bucket = next(o["OutputValue"] for o in result["Stacks"][0]["Outputs"] if o["OutputKey"] == "BucketName")
    checks = verify_bucket(args.profile, args.region, bucket)
    args.state.parent.mkdir(parents=True, exist_ok=True)
    args.state.write_text(json.dumps({"bucket": bucket, "region": args.region, "stack": args.stack, "verified": checks}, indent=2) + "\n")
    print("Private bucket verified; saved ignored local state", flush=True)


def upload(args):
    state = json.loads(args.state.read_text())
    bucket, region = state["bucket"], state["region"]
    verify_bucket(args.profile, region, bucket)
    inputs = verify_payloads(args.data_root)
    report_path = args.dataset_root / "report.json"
    report = json.loads(report_path.read_text())
    dataset = args.dataset_root / "quarters.csv"
    if digest(dataset) != report["dataset"]["sha256"] or report["inputs"] != inputs:
        raise ValueError("Dataset or input hashes do not match the report")
    files = [(args.data_root / path, f"inputs/{inputs[source]['sha256']}/{Path(path).name}") for source, path in PAYLOADS.items()]
    prefix = f"datasets/{report['dataset']['sha256']}"
    files += [(dataset, f"{prefix}/quarters.csv"), (report_path, f"{prefix}/reports/{digest(report_path)}.json")]
    uploaded = []
    for path, key in files:
        sha = digest(path)
        listing = aws(args.profile, region, "s3api", "list-objects-v2", "--bucket", bucket, "--prefix", key)
        if not any(item["Key"] == key for item in listing.get("Contents", [])):
            aws(args.profile, region, "s3api", "put-object", "--bucket", bucket, "--key", key,
                "--body", str(path), "--server-side-encryption", "AES256", "--if-none-match", "*",
                "--checksum-sha256", base64.b64encode(bytes.fromhex(sha)).decode(), "--metadata", f"sha256={sha}")
        head = aws(args.profile, region, "s3api", "head-object", "--bucket", bucket, "--key", key, "--checksum-mode", "ENABLED")
        if head["ContentLength"] != path.stat().st_size or head.get("ChecksumSHA256") != base64.b64encode(bytes.fromhex(sha)).decode():
            raise ValueError(f"Remote checksum/size mismatch: {key}")
        uploaded.append({"key": key, "sha256": sha, "bytes": head["ContentLength"], "version_id": head["VersionId"]})
        print(f"Verified {path.name}", flush=True)
    (args.state.parent / "aws-upload.json").write_text(json.dumps({"bucket": bucket, "objects": uploaded}, indent=2) + "\n")


def restore(args):
    manifest = json.loads((ROOT / "forecasts/evidence/payload-manifest.json").read_text())
    expected = {p["path"].removeprefix("data/forecasts/"): p for p in manifest["payloads"]}
    for relative in PAYLOADS.values():
        entry = expected[relative]
        path = args.data_root / relative
        if path.exists() and path.stat().st_size == entry["bytes"] and digest(path) == entry["sha256"]:
            print(f"Verified existing {path.name}", flush=True)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
            downloaded = Path(temporary.name)
        try:
            key = f"inputs/{entry['sha256']}/{path.name}"
            aws(args.profile, args.region, "s3api", "get-object", "--bucket", args.bucket,
                "--key", key, "--checksum-mode", "ENABLED", str(downloaded))
            if downloaded.stat().st_size != entry["bytes"] or digest(downloaded) != entry["sha256"]:
                raise ValueError(f"Downloaded snapshot checksum mismatch: {relative}")
            downloaded.replace(path)
        finally:
            downloaded.unlink(missing_ok=True)
        print(f"Restored and verified {path.name}", flush=True)
    verify_payloads(args.data_root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, help="User-local AWS CLI profile; never commit its configuration")
    parser.add_argument("--region", default="eu-west-1")
    parser.add_argument("--state", type=Path, default=ROOT / "data/forecasts/aws-storage.json")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("provision")
    create.add_argument("--stack", default="coppersushi-forecast-storage")
    transfer = sub.add_parser("upload")
    transfer.add_argument("--data-root", type=Path, default=ROOT / "data/forecasts")
    transfer.add_argument("--dataset-root", type=Path, default=ROOT / "data/forecasts/dataset")
    download = sub.add_parser("restore")
    download.add_argument("--bucket", required=True, help="Private bucket name supplied by its owner; never commit account-specific state")
    download.add_argument("--data-root", type=Path, default=ROOT / "data/forecasts")
    args = parser.parse_args()
    # Account identifiers and resource names must stay in the ignored local data tree.
    if not args.state.resolve().is_relative_to((ROOT / "data/forecasts").resolve()):
        parser.error("--state must be inside this checkout's ignored data/forecasts directory")
    {"provision": provision, "upload": upload, "restore": restore}[args.command](args)


if __name__ == "__main__":
    main()
