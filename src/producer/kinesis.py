"""Batch records into PutRecords calls, retrying only the records that failed."""

import logging
import random
import sys
import time

from botocore.exceptions import ClientError

from producer.stats import RunStats

log = logging.getLogger(__name__)

MAX_BATCH_RECORDS = 500  # PutRecords limit
MAX_BATCH_BYTES = 5 * 1024 * 1024  # PutRecords limit, data plus partition keys
THROTTLED = "ProvisionedThroughputExceededException"
# Errors that retrying cannot fix, such as the stream not existing.
FATAL_ERRORS = {"ResourceNotFoundException", "AccessDeniedException", "ValidationException"}


class KinesisWriter:
    def __init__(
        self,
        client,
        stream_name: str,
        stats: RunStats,
        max_attempts: int = 8,
        flush_after_seconds: float = 1.0,
        clock=time.monotonic,
        sleep=time.sleep,
        rand=random.random,
    ):
        self.client = client
        self.stream_name = stream_name
        self.stats = stats
        self.max_attempts = max_attempts
        self.flush_after_seconds = flush_after_seconds
        self.clock = clock
        self.sleep = sleep
        self.rand = rand
        self._buffer: list[dict] = []
        self._buffer_bytes = 0
        self._buffer_started = 0.0

    def add(self, data: bytes, partition_key: str) -> None:
        size = len(data) + len(partition_key.encode())
        if self._buffer and self._buffer_bytes + size > MAX_BATCH_BYTES:
            self.flush()
        if not self._buffer:
            self._buffer_started = self.clock()
        self._buffer.append({"Data": data, "PartitionKey": partition_key})
        self._buffer_bytes += size
        if len(self._buffer) == MAX_BATCH_RECORDS:
            self.flush()

    def flush_if_due(self) -> None:
        """Send a partial batch once it has waited long enough, so quiet periods still flow."""
        if self._buffer and self.clock() - self._buffer_started >= self.flush_after_seconds:
            self.flush()

    def flush(self) -> None:
        pending, self._buffer, self._buffer_bytes = self._buffer, [], 0
        for attempt in range(1, self.max_attempts + 1):
            if not pending:
                return
            pending = self._put(pending)
            if pending and attempt < self.max_attempts:
                self.stats.retries += len(pending)
                self.sleep(self._backoff(attempt))
        if pending:
            self.stats.failed += len(pending)
            log.error("gave up on %d records after %d attempts", len(pending), self.max_attempts)

    def _put(self, records: list[dict]) -> list[dict]:
        """Send one PutRecords call and return the records that failed."""
        try:
            response = self.client.put_records(StreamName=self.stream_name, Records=records)
        except ClientError as exc:
            if exc.response["Error"]["Code"] in FATAL_ERRORS:
                raise
            log.warning("PutRecords call failed (%s), retrying the whole batch", exc)
            return records
        self.stats.mark_first_put()

        failed = []
        for record, result in zip(records, response["Records"], strict=True):
            if "ErrorCode" in result:
                if result["ErrorCode"] == THROTTLED:
                    self.stats.throttled += 1
                failed.append(record)
            else:
                self.stats.sent += 1
                self.stats.per_shard[result["ShardId"]] += 1
        return failed

    def _backoff(self, attempt: int) -> float:
        """Exponential backoff with full jitter: random waits up to 0.2s, 0.4s, 0.8s... max 5s."""
        return self.rand() * min(5.0, 0.1 * 2**attempt)


class PrintSink:
    """Stands in for KinesisWriter in a dry run: prints each record instead of sending it."""

    def __init__(self, out=sys.stdout):
        self.out = out

    def add(self, data: bytes, partition_key: str) -> None:
        print(f"[{partition_key}] {data.decode()}", file=self.out)

    def flush_if_due(self) -> None:
        pass

    def flush(self) -> None:
        self.out.flush()
