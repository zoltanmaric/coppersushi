"""API credentials from explicit local configuration or the trial's private AWS secret."""
from functools import lru_cache
import json
import os
from pathlib import Path


@lru_cache(maxsize=1)
def _secret() -> dict[str, str]:
    name = os.environ.get("COPPERSUSHI_SECRET_ID")
    if not name:
        return {}
    import boto3
    result = boto3.client("secretsmanager").get_secret_value(SecretId=name)
    return json.loads(result["SecretString"])


def token(name: str, path: Path) -> str:
    value = os.environ.get(name) or _secret().get(name)
    if value:
        return value
    try:
        return path.read_text().strip()
    except FileNotFoundError as error:
        raise RuntimeError(f"set {name} or create {path}") from error
