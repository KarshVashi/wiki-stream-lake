import pytest
from botocore.exceptions import ClientError

from producer.kinesis import THROTTLED, KinesisWriter
from producer.stats import RunStats


class FakeKinesis:
    """Records each PutRecords call. fail_first[n] = how many records to fail on call n."""

    def __init__(self, fail_first=(), error_code=THROTTLED):
        self.calls = []
        self.fail_first = list(fail_first)
        self.error_code = error_code

    def put_records(self, StreamName, Records):
        self.calls.append([r["PartitionKey"] for r in Records])
        n_fail = self.fail_first.pop(0) if self.fail_first else 0
        results = []
        for i, _ in enumerate(Records):
            if i < n_fail:
                results.append({"ErrorCode": self.error_code, "ErrorMessage": "slow down"})
            else:
                results.append({"ShardId": f"shard-{i % 2}", "SequenceNumber": "1"})
        return {"FailedRecordCount": n_fail, "Records": results}


def make_writer(client, **kwargs):
    stats = RunStats("capture", "event_id", "s", dry_run=False)
    writer = KinesisWriter(client, "s", stats, sleep=lambda s: None, rand=lambda: 1.0, **kwargs)
    return writer, stats


def test_batches_at_500_records():
    client = FakeKinesis()
    writer, stats = make_writer(client)
    for i in range(1200):
        writer.add(b"x", f"k{i}")
    writer.flush()
    assert [len(call) for call in client.calls] == [500, 500, 200]
    assert stats.sent == 1200


def test_batches_split_before_5_mb():
    client = FakeKinesis()
    writer, _ = make_writer(client)
    for i in range(6):
        writer.add(b"x" * 1_000_000, f"k{i}")
    writer.flush()
    assert [len(call) for call in client.calls] == [5, 1]


def test_retries_only_the_failed_records():
    client = FakeKinesis(fail_first=[2, 1])
    writer, stats = make_writer(client)
    for key in ["a", "b", "c"]:
        writer.add(b"x", key)
    writer.flush()
    assert client.calls == [["a", "b", "c"], ["a", "b"], ["a"]]
    assert (stats.sent, stats.throttled, stats.retries, stats.failed) == (3, 3, 3, 0)


def test_gives_up_after_max_attempts():
    client = FakeKinesis(fail_first=[1, 1, 1])
    writer, stats = make_writer(client, max_attempts=3)
    writer.add(b"x", "a")
    writer.flush()
    assert len(client.calls) == 3
    assert (stats.sent, stats.failed, stats.retries) == (0, 1, 2)


def test_only_throughput_errors_count_as_throttles():
    client = FakeKinesis(fail_first=[1], error_code="InternalFailure")
    writer, stats = make_writer(client)
    writer.add(b"x", "a")
    writer.flush()
    assert (stats.sent, stats.throttled, stats.retries) == (1, 0, 1)


def test_counts_records_per_shard():
    client = FakeKinesis()
    writer, stats = make_writer(client)
    for key in "abcde":
        writer.add(b"x", key)
    writer.flush()
    assert stats.per_shard == {"shard-0": 3, "shard-1": 2}
    assert stats.first_put_at is not None


def test_partial_batch_flushes_after_waiting():
    now = [0.0]
    client = FakeKinesis()
    writer, _ = make_writer(client, clock=lambda: now[0], flush_after_seconds=1.0)
    writer.add(b"x", "a")
    writer.flush_if_due()
    assert client.calls == []
    now[0] = 1.5
    writer.flush_if_due()
    assert client.calls == [["a"]]


def test_missing_stream_is_fatal():
    class MissingStream:
        def put_records(self, **kwargs):
            raise ClientError({"Error": {"Code": "ResourceNotFoundException"}}, "PutRecords")

    writer, _ = make_writer(MissingStream())
    writer.add(b"x", "a")
    with pytest.raises(ClientError):
        writer.flush()
