"""Versioned S3 artifacts and immutable authority for forecast operations."""
import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path, PurePosixPath
from typing import Annotated, Any

from botocore.exceptions import ClientError
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

type Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
type Nonempty = Annotated[str, StringConstraints(min_length=1)]
type RunId = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{24}$")]


class ObjectPin(BaseModel):
    """The immutable S3 version and content digest of a retained artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    bucket: Nonempty
    key: Nonempty
    version_id: Nonempty
    sha256: Sha256

    @field_validator("version_id")
    @classmethod
    def require_version(cls, value: str) -> str:
        if value == "null":
            raise ValueError("An S3 object version is required")
        return value


@dataclass(frozen=True)
class StoredObject:
    """Bytes delivered by S3, alongside their version and server write time."""

    pin: ObjectPin
    data: bytes
    published_at: datetime


class MissingArtifact(FileNotFoundError):
    """A required S3 object or exact version is absent."""

    def __init__(self, bucket: str, key: str, version_id: str | None) -> None:
        super().__init__(f"Missing S3 artifact s3://{bucket}/{key}" + (f" version {version_id}" if version_id else ""))
        self.key = key


class Artifacts:
    """Resolve complete objects and reserve an immutable key with a conditional PUT."""

    def __init__(self, s3: Any, bucket: str, replay: str | None) -> None:
        self.s3 = s3
        self.bucket = bucket
        self.prefix = "" if replay is None else f"replays/{replay}/"

    def key(self, path: str) -> str:
        """Put an output path in the current authority namespace."""
        return self.prefix + path

    def get(self, path: str) -> StoredObject:
        """Read the complete current version of an authority object."""
        return self._get(self.bucket, self.key(path))

    def pinned(self, pin: ObjectPin) -> StoredObject:
        """Read the complete object and verify its exact version and SHA-256."""
        result = self._get(pin.bucket, pin.key, pin.version_id)
        if result.pin != pin:
            raise ValueError(f"Pinned artifact changed: s3://{pin.bucket}/{pin.key} ({pin.version_id})")
        return result

    def create(self, path: str, data: bytes) -> str | None:
        """Return the new version, or None when another writer already reserved the key."""
        key = self.key(path)
        checksum = base64.b64encode(hashlib.sha256(data).digest()).decode("ascii")
        for _ in range(3):
            try:
                result = self.s3.put_object(Bucket=self.bucket, Key=key, Body=data, IfNoneMatch="*",
                                            ChecksumSHA256=checksum)
                return _version(result, key)
            except ClientError as error:
                code = error.response["Error"]["Code"]
                if code in {"PreconditionFailed", "412"}:
                    return None
                if code not in {"ConditionalRequestConflict", "409"}:
                    raise
        raise RuntimeError(f"Concurrent conditional S3 write did not settle: {key}")

    def retain(self, path: str, data: bytes) -> ObjectPin:
        """Keep an immutable artifact and verify identical content on retries."""
        version_id = self.create(path, data)
        pin = ObjectPin(bucket=self.bucket, key=self.key(path), version_id=version_id or self.get(path).pin.version_id,
                        sha256=sha256(data))
        self.pinned(pin)
        return pin

    def _get(self, bucket: str, key: str, version_id: str | None = None) -> StoredObject:
        request = {"Bucket": bucket, "Key": key}
        if version_id is not None:
            request["VersionId"] = version_id
        try:
            response = self.s3.get_object(**request)
        except ClientError as error:
            if error.response["Error"]["Code"] in {"404", "NoSuchKey", "NoSuchVersion", "NotFound"}:
                raise MissingArtifact(bucket, key, version_id) from error
            raise
        body = response["Body"]
        try:
            data = body.read()
        finally:
            body.close()
        published_at = response["LastModified"]
        if published_at.utcoffset() is None:
            raise ValueError(f"S3 omitted the publication timezone: {key}")
        pin = ObjectPin(bucket=bucket, key=key, version_id=_version(response, key), sha256=sha256(data))
        return StoredObject(pin, data, published_at.astimezone(timezone.utc))


def under(directory: Path, name: str) -> Path:
    """Resolve a canonical relative artifact name within a local bundle."""
    candidate = PurePosixPath(name)
    if not candidate.parts or candidate.is_absolute() or ".." in candidate.parts or candidate.as_posix() != name:
        raise ValueError(f"Invalid artifact name: {name}")
    return directory.joinpath(*candidate.parts)


def sha256(data: bytes) -> str:
    """Return the lowercase hexadecimal SHA-256 checksum."""
    return hashlib.sha256(data).hexdigest()


def _version(response: dict[str, Any], key: str) -> str:
    version_id = response.get("VersionId")
    if not version_id or version_id == "null":
        raise ValueError(f"S3 did not return an immutable version: {key}")
    return version_id
