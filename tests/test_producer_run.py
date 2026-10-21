import gzip
import io
import json
import threading

import pytest

from producer.cli import parse_args, run
from producer.sources import partition_key, rate_limited, read_s3_events, split_s3_uri
from producer.stats import RunStats


class ListSink:
    def __init__(self):
        self.added, self.flushed = [], 0

    def add(self, data, key):
        self.added.append(key)

    def flush_if_due(self):
        pass

    def flush(self):
        self.flushed += 1


def test_run_stops_at_deadline_and_flushes():
    now = [0.0]

    def records():
        for i in range(100):
            now[0] = float(i)
            yield b"x", str(i)

    sink, stats = ListSink(), RunStats("capture", "event_id", None, dry_run=True)
    run(records(), sink, stats, deadline=10.0, stop=threading.Event(), clock=lambda: now[0])
    assert sink.added == [str(i) for i in range(11)]
    assert stats.read == 11
    assert sink.flushed == 1


def test_run_stops_when_asked():
    stop = threading.Event()

    def records():
        yield b"x", "a"
        stop.set()
        yield b"x", "b"
        yield b"x", "c"

    sink = ListSink()
    run(records(), sink, RunStats("capture", "event_id", None, True), 1e9, stop)
    assert sink.added == ["a", "b"]


def test_partition_key_handles_live_and_flattened_events():
    live = {"meta": {"domain": "en.wikipedia.org", "id": "abc"}}
    flat = {"domain": "www.wikidata.org", "event_id": "def"}
    assert partition_key(live, "domain") == "en.wikipedia.org"
    assert partition_key(live, "event_id") == "abc"
    assert partition_key(flat, "domain") == "www.wikidata.org"
    assert partition_key(flat, "event_id") == "def"


def test_rate_limited_sleeps_to_hold_the_rate():
    now = [0.0]
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    out = list(rate_limited(range(5), per_second=10, clock=lambda: now[0], sleep=sleep))
    assert out == [0, 1, 2, 3, 4]
    assert now[0] == pytest.approx(0.4)


def test_read_s3_events_reads_gzip_lines_in_key_order():
    def gz(*events):
        return gzip.compress(b"".join(json.dumps(e).encode() + b"\n" for e in events))

    objects = {"raw/b.gz": gz({"n": 3}), "raw/a.gz": gz({"n": 1}, {"n": 2})}

    class FakeS3:
        def get_paginator(self, name):
            class Paginator:
                def paginate(self, Bucket, Prefix):
                    return [{"Contents": [{"Key": k} for k in objects]}]

            return Paginator()

        def get_object(self, Bucket, Key):
            return {"Body": io.BytesIO(objects[Key])}

    assert [e["n"] for e in read_s3_events(FakeS3(), "b", "raw/")] == [1, 2, 3]


def test_split_s3_uri():
    assert split_s3_uri("s3://lake/raw/edits/day=01/") == ("lake", "raw/edits/day=01/")
    with pytest.raises(ValueError):
        split_s3_uri("lake/raw")


def test_args_require_stream_unless_dry_run():
    with pytest.raises(SystemExit):
        parse_args(["capture", "--duration-minutes", "5"])
    assert parse_args(["capture", "--duration-minutes", "5", "--dry-run"]).dry_run


def test_args_cap_duration_at_24_hours():
    with pytest.raises(SystemExit):
        parse_args(["capture", "--duration-minutes", "1441", "--dry-run"])


def test_summary_key_and_shares():
    stats = RunStats("replay", "domain", "s", dry_run=False)
    stats.sent = 4
    stats.per_shard.update({"shard-0": 3, "shard-1": 1})
    summary = stats.summary()
    assert summary["percent_per_shard"] == {"shard-0": 75.0, "shard-1": 25.0}
    assert stats.summary_key().startswith("runs/")
    assert stats.summary_key().endswith("-replay-domain.json")
