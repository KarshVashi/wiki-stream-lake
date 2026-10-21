"""Counters for one producer run, and the summary written at the end."""

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class RunStats:
    mode: str
    partition_key: str
    stream_name: str | None
    dry_run: bool
    started_at: datetime = field(default_factory=_now)
    ended_at: datetime | None = None
    first_put_at: datetime | None = None
    read: int = 0  # events taken from the source
    sent: int = 0  # records Kinesis accepted
    failed: int = 0  # records given up on after all retries
    throttled: int = 0  # per-record ProvisionedThroughputExceeded responses
    retries: int = 0  # records sent again after a failure
    per_shard: Counter = field(default_factory=Counter)

    def mark_first_put(self) -> None:
        if self.first_put_at is None:
            self.first_put_at = _now()

    def finish(self) -> None:
        self.ended_at = _now()

    def log_line(self) -> str:
        shards = ", ".join(f"{shard}={n}" for shard, n in sorted(self.per_shard.items()))
        return (
            f"read={self.read} sent={self.sent} failed={self.failed} "
            f"throttled={self.throttled} retries={self.retries} shards: {shards or '-'}"
        )

    def summary(self) -> dict:
        ended_at = self.ended_at or _now()
        seconds = (ended_at - self.started_at).total_seconds()
        return {
            "mode": self.mode,
            "partition_key": self.partition_key,
            "stream_name": self.stream_name,
            "dry_run": self.dry_run,
            "started_at": self.started_at.isoformat(),
            "ended_at": ended_at.isoformat(),
            "first_put_at": self.first_put_at.isoformat() if self.first_put_at else None,
            "duration_seconds": round(seconds, 1),
            "records_read": self.read,
            "records_sent": self.sent,
            "records_failed": self.failed,
            "throttled": self.throttled,
            "retries": self.retries,
            "sent_per_second": round(self.sent / seconds, 1) if seconds else 0.0,
            "records_per_shard": dict(sorted(self.per_shard.items())),
            "percent_per_shard": {
                shard: round(100 * n / self.sent, 1) for shard, n in sorted(self.per_shard.items())
            },
        }

    def summary_key(self) -> str:
        """S3 key for the summary, e.g. runs/20261020T140501Z-capture-domain.json."""
        stamp = self.started_at.strftime("%Y%m%dT%H%M%SZ")
        suffix = "-dryrun" if self.dry_run else ""
        return f"runs/{stamp}-{self.mode}-{self.partition_key}{suffix}.json"
