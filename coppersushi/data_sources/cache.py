"""Optional durable cache: one validated input bundle per atomic private S3 object."""

from functools import lru_cache
import gzip
import json
import logging
import os
from pathlib import Path
import tempfile

from coppersushi import REPO

logger = logging.getLogger(__name__)
DATA_DIR = Path(os.environ.get("COPPERSUSHI_DATA_DIR", REPO / "data"))


@lru_cache(maxsize=1)
def _client():
    import boto3
    from botocore.config import Config
    return boto3.client("s3", config=Config(connect_timeout=5, read_timeout=10,
                                           retries={"max_attempts": 2}))


def encode(files: dict[str, str]) -> bytes:
    return gzip.compress(json.dumps(files).encode("utf-8"))


def decode(payload: bytes, names: tuple[str, ...]) -> dict[str, str]:
    files = json.loads(gzip.decompress(payload))
    if not isinstance(files, dict) or set(files) != set(names) or any(not isinstance(v, str) for v in files.values()):
        raise ValueError("cache bundle does not contain exactly the expected tables")
    return files


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, mode="w", encoding="utf-8", delete=False) as file:
        temporary = Path(file.name)
        file.write(text)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def restore(key: str, directory: Path, names: tuple[str, ...]) -> bool:
    bucket = os.environ.get("COPPERSUSHI_CACHE_BUCKET")
    if not bucket:
        return False
    from botocore.exceptions import ClientError
    try:
        response = _client().get_object(Bucket=bucket, Key=f"cache/v1/{key}.json.gz")
    except ClientError as error:
        if error.response["Error"]["Code"] in {"NoSuchKey", "404"}:
            return False
        raise
    with response["Body"] as stream:
        payload = stream.read()
    try:
        files = decode(payload, names)
    except (ValueError, OSError, EOFError):
        logger.exception("Ignoring corrupt durable cache entry %s", key)
        return False
    # Decode and check every table before creating any local file.
    for name, text in files.items():
        atomic_text(directory / name, text)
    logger.info("Durable cache hit: %s", key)
    return True


def publish(key: str, directory: Path, names: tuple[str, ...]) -> None:
    bucket = os.environ.get("COPPERSUSHI_CACHE_BUCKET")
    if not bucket:
        return
    files = {name: (directory / name).read_text(encoding="utf-8") for name in names}
    _client().put_object(Bucket=bucket, Key=f"cache/v1/{key}.json.gz", Body=encode(files),
                         ContentType="application/json", ContentEncoding="gzip")
    logger.info("Durable cache published: %s", key)
