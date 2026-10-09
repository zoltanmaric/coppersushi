"""Provision private S3 storage and transfer verified, content-addressed snapshots.

AWS profiles belong to the user, never the repository. Account-specific state stays
under ignored data/forecasts; this module does not read or export credentials.
"""
import base64
import json
import os
from pathlib import Path
import subprocess

from forecasts.dataset import digest


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


def put_verified(profile, region, bucket, key, path):
    """Conditional creation makes retries safe; verify any existing object's bytes."""
    sha = digest(path)
    listing = aws(profile, region, "s3api", "list-objects-v2", "--bucket", bucket, "--prefix", key)
    if not any(item["Key"] == key for item in listing.get("Contents", [])):
        aws(profile, region, "s3api", "put-object", "--bucket", bucket, "--key", key,
            "--body", str(path), "--server-side-encryption", "AES256", "--if-none-match", "*",
            "--checksum-sha256", base64.b64encode(bytes.fromhex(sha)).decode(), "--metadata", f"sha256={sha}")
    head = aws(profile, region, "s3api", "head-object", "--bucket", bucket, "--key", key, "--checksum-mode", "ENABLED")
    if head["ContentLength"] != path.stat().st_size or head.get("ChecksumSHA256") != base64.b64encode(bytes.fromhex(sha)).decode():
        raise ValueError(f"Remote checksum/size mismatch: {key}")
    return {"key": key, "sha256": sha, "bytes": head["ContentLength"], "version_id": head["VersionId"]}


def get_verified(profile, region, bucket, key, path, sha=None):
    aws(profile, region, "s3api", "get-object", "--bucket", bucket,
        "--key", key, "--checksum-mode", "ENABLED", str(path))
    if sha is not None and digest(path) != sha:
        path.unlink(missing_ok=True)
        raise ValueError(f"Downloaded checksum mismatch: {key}")
