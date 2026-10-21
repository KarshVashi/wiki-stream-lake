"""Where records come from, and how each one gets its partition key."""

import gzip
import json
import time
import uuid
from collections.abc import Iterable, Iterator


def partition_key(event: dict, key: str) -> str:
    """Pick the Kinesis partition key for an event.

    Live events are nested (meta.domain, meta.id). Replayed events come from raw/,
    where the transform Lambda has already flattened them (domain, event_id).
    """
    meta = event.get("meta", {})
    if key == "domain":
        return meta.get("domain") or event.get("domain") or "unknown"
    return meta.get("id") or event.get("event_id") or str(uuid.uuid4())


def to_records(events: Iterable[dict], key: str) -> Iterator[tuple[bytes, str]]:
    """Turn events into (data, partition_key) pairs ready for Kinesis."""
    for event in events:
        data = json.dumps(event, separators=(",", ":"), ensure_ascii=False).encode()
        yield data, partition_key(event, key)


def split_s3_uri(uri: str) -> tuple[str, str]:
    """Split s3://bucket/some/prefix into ("bucket", "some/prefix")."""
    if not uri.startswith("s3://"):
        raise ValueError(f"expected an s3:// URI, got {uri!r}")
    bucket, _, prefix = uri.removeprefix("s3://").partition("/")
    return bucket, prefix


def read_s3_events(s3, bucket: str, prefix: str) -> Iterator[dict]:
    """Yield events from the gzip JSON-lines files under a prefix, in key order."""
    paginator = s3.get_paginator("list_objects_v2")
    keys = sorted(
        obj["Key"]
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix)
        for obj in page.get("Contents", [])
    )
    for key in keys:
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        for line in gzip.decompress(body).splitlines():
            if line.strip():
                yield json.loads(line)


def rate_limited(items: Iterable, per_second: float, clock=time.monotonic, sleep=time.sleep):
    """Yield items no faster than per_second, sleeping whenever we get ahead."""
    start = clock()
    for count, item in enumerate(items):
        ahead = count / per_second - (clock() - start)
        if ahead > 0:
            sleep(ahead)
        yield item
