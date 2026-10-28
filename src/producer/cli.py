"""Command line entry point: python -m producer {capture,replay} ..."""

import argparse
import json
import logging
import signal
import threading
import time
from collections.abc import Iterable

import boto3
from botocore.config import Config

from producer.kinesis import KinesisWriter, PrintSink
from producer.sources import rate_limited, read_s3_events, split_s3_uri, to_records
from producer.sse import stream_events
from producer.stats import RunStats

log = logging.getLogger("producer")

USER_AGENT = "wiki-stream-lake/0.1 (https://github.com/KarshVashi/wiki-stream-lake)"
MAX_DURATION_MINUTES = 24 * 60
LOG_EVERY_SECONDS = 30


def run(
    records: Iterable[tuple[bytes, str]],
    sink,
    stats: RunStats,
    deadline: float,
    stop: threading.Event,
    clock=time.monotonic,
) -> None:
    """Move records into the sink until the source ends, the deadline passes, or stop is set."""
    last_log = clock()
    try:
        for data, key in records:
            stats.read += 1
            sink.add(data, key)
            sink.flush_if_due()
            now = clock()
            if now - last_log >= LOG_EVERY_SECONDS:
                log.info(stats.log_line())
                last_log = now
            if now >= deadline or stop.is_set():
                break
    finally:
        sink.flush()


def duration_minutes(value: str) -> int:
    minutes = int(value)
    if not 1 <= minutes <= MAX_DURATION_MINUTES:
        raise argparse.ArgumentTypeError(f"must be between 1 and {MAX_DURATION_MINUTES}")
    return minutes


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="producer", description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)

    capture = modes.add_parser("capture", help="read the live Wikimedia stream")
    capture.add_argument("--contact", help="extra contact detail for the User-Agent header")

    replay = modes.add_parser("replay", help="resend events from raw/ in S3 at a fixed rate")
    replay.add_argument("--source", required=True, help="s3://bucket/raw/edits/... prefix")
    replay.add_argument("--rate", type=float, required=True, help="records per second")

    for mode in (capture, replay):
        mode.add_argument("--stream-name", help="Kinesis stream (not needed with --dry-run)")
        mode.add_argument("--partition-key", choices=["domain", "event_id"], default="event_id")
        mode.add_argument("--duration-minutes", type=duration_minutes, required=True)
        mode.add_argument("--dry-run", action="store_true", help="print records, send nothing")
        mode.add_argument("--summary-bucket", help="write the run summary to s3://BUCKET/runs/")

    args = parser.parse_args(argv)
    if not args.dry_run and not args.stream_name:
        parser.error("--stream-name is required unless --dry-run is set")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # ECS stops a task with SIGTERM; finish the current batch and write the summary.
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    stats = RunStats(args.mode, args.partition_key, args.stream_name, args.dry_run)
    deadline = time.monotonic() + args.duration_minutes * 60

    def keep_going() -> bool:
        return time.monotonic() < deadline and not stop.is_set()

    if args.mode == "capture":
        user_agent = f"{USER_AGENT} {args.contact}" if args.contact else USER_AGENT
        events = stream_events(user_agent, keep_going=keep_going)
        records = to_records(events, args.partition_key)
    else:
        bucket, prefix = split_s3_uri(args.source)
        events = read_s3_events(boto3.client("s3"), bucket, prefix)
        records = rate_limited(to_records(events, args.partition_key), args.rate)

    if args.dry_run:
        sink = PrintSink()
    else:
        kinesis = boto3.client("kinesis", config=Config(retries={"mode": "standard"}))
        sink = KinesisWriter(kinesis, args.stream_name, stats)

    log.info(
        "starting %s for %d minutes, partition key %s%s",
        args.mode,
        args.duration_minutes,
        args.partition_key,
        " (dry run)" if args.dry_run else "",
    )
    try:
        run(records, sink, stats, deadline, stop)
    finally:
        stats.finish()
        summary = stats.summary()
        log.info("finished: %s", stats.log_line())
        log.info("summary: %s", json.dumps(summary))
        if args.summary_bucket:
            key = stats.summary_key()
            boto3.client("s3").put_object(
                Bucket=args.summary_bucket,
                Key=key,
                Body=json.dumps(summary, indent=2).encode(),
                ContentType="application/json",
            )
            log.info("wrote s3://%s/%s", args.summary_bucket, key)
    return 0
