"""Durable cache contracts: complete bundles, misses and visible storage failures."""
import json
from io import BytesIO

import pytest

from coppersushi import REPO
from coppersushi.data_sources import cache

FILES = json.loads((REPO / "tests/fixtures/cache-bundle.json").read_text())
NAMES = tuple(FILES)


def test_bundle_round_trip_keeps_every_table():
    assert cache.decode(cache.encode(FILES), NAMES) == FILES


@pytest.mark.parametrize("files", [{}, {"../escape.csv": "bad"}, {"constraints.csv": 1, "ptdfs.csv": ""}])
def test_a_partial_or_unexpected_bundle_is_rejected(files):
    with pytest.raises(ValueError, match="expected tables"):
        cache.decode(cache.encode(files), NAMES)


def test_durable_round_trip_can_restore_into_a_fresh_instance(tmp_path, monkeypatch):
    boto3 = pytest.importorskip("boto3")
    from botocore.stub import Stubber
    client = boto3.client("s3", region_name="eu-west-1", aws_access_key_id="synthetic", aws_secret_access_key="synthetic")
    monkeypatch.setenv("COPPERSUSHI_CACHE_BUCKET", "test-cache")
    monkeypatch.setattr(cache, "_client", lambda: client)
    with Stubber(client) as stub:
        first = tmp_path / "first"
        for name, text in FILES.items():
            cache.atomic_text(first / name, text)
        stub.add_response("put_object", {}, {"Bucket": "test-cache", "Key": "cache/v1/day.json.gz",
                          "Body": cache.encode(FILES), "ContentType": "application/json", "ContentEncoding": "gzip"})
        cache.publish("day", first, NAMES)
        stub.add_response("get_object", {"Body": BytesIO(cache.encode(FILES))},
                          {"Bucket": "test-cache", "Key": "cache/v1/day.json.gz"})
        fresh = tmp_path / "fresh"
        assert cache.restore("day", fresh, NAMES)
        assert {name: (fresh / name).read_text() for name in NAMES} == FILES
        stub.assert_no_pending_responses()


def test_only_absent_objects_are_cache_misses(tmp_path, monkeypatch):
    boto3 = pytest.importorskip("boto3")
    from botocore.stub import Stubber
    from botocore.exceptions import ClientError
    client = boto3.client("s3", region_name="eu-west-1", aws_access_key_id="synthetic", aws_secret_access_key="synthetic")
    monkeypatch.setenv("COPPERSUSHI_CACHE_BUCKET", "test-cache")
    monkeypatch.setattr(cache, "_client", lambda: client)
    with Stubber(client) as stub:
        stub.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)
        assert not cache.restore("missing", tmp_path, NAMES)
        stub.add_client_error("get_object", service_error_code="AccessDenied", http_status_code=403)
        with pytest.raises(ClientError):
            cache.restore("denied", tmp_path, NAMES)
    assert not list(tmp_path.iterdir())
