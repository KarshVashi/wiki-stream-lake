from datetime import UTC, date, datetime, timedelta

import pytest

from athena import benchmark_cases, drop_date_filter, quoted
from freshness import day_prefixes, freshness
from run_task import producer_command, replay_source
from runs_table import row

CURATED = """SELECT domain, count(*) AS edits
FROM curated_edits
WHERE event_date = ?
GROUP BY domain"""


def test_drop_date_filter_removes_only_that_line():
    assert (
        drop_date_filter(CURATED)
        == "SELECT domain, count(*) AS edits\nFROM curated_edits\nGROUP BY domain"
    )


def test_drop_date_filter_refuses_an_unexpected_query():
    with pytest.raises(ValueError):
        drop_date_filter("SELECT 1")


def test_benchmark_cases_quote_their_parameters():
    cases = benchmark_cases(
        {"benchmark_raw": "raw sql", "benchmark_curated": CURATED}, date(2026, 10, 24)
    )
    assert cases["raw JSON, one day"] == ("raw sql", ["'2026'", "'10'", "'24'"])
    assert cases["curated Parquet, one day"][1] == ["'2026-10-24'"]
    assert cases["curated Parquet, all days"][1] == []
    assert quoted("it's") == "'it''s'"


def test_freshness_measures_delay_files_and_size():
    start = datetime(2026, 10, 24, 18, 0, tzinfo=UTC)
    objects = [
        {"LastModified": start + timedelta(seconds=125), "Size": 100 * 1024},
        {"LastModified": start + timedelta(seconds=245), "Size": 300 * 1024},
    ]
    result = freshness(start, objects)
    assert (result["delay_seconds"], result["files"], result["avg_file_kb"]) == (125, 2, 200.0)
    assert freshness(start, []) == {"files": 0}


def test_day_prefixes_span_midnight():
    start = datetime(2026, 10, 24, 23, 50, tzinfo=UTC)
    assert day_prefixes(start, start + timedelta(minutes=30)) == [
        "raw/edits/year=2026/month=10/day=24/",
        "raw/edits/year=2026/month=10/day=25/",
    ]


def test_replay_source_must_be_under_raw_edits():
    assert replay_source("lake", "raw/edits/year=2026/") == "s3://lake/raw/edits/year=2026/"
    with pytest.raises(SystemExit):
        replay_source("lake", "curated/edits/")


def test_replay_command():
    extra = ["--source", "s3://lake/raw/edits/", "--rate", "2500"]
    command = producer_command("replay", 10, "domain", "replay", "lake", extra)
    assert command[:5] == ["replay", "--partition-key", "domain", "--duration-minutes", "10"]
    assert command[-4:] == extra


def test_runs_table_row():
    summary = {
        "mode": "capture", "dry_run": False, "partition_key": "domain", "duration_seconds": 1200,
        "records_sent": 50000, "records_failed": 0, "throttled": 0, "sent_per_second": 41.7,
        "percent_per_shard": {"shardId-0": 71.2, "shardId-1": 28.8},
    }  # fmt: skip
    assert row(summary, "run1") == (
        "| run1 | capture | domain | 20 | 50,000 | 0 | 0 | 41.7 | 71.2% / 28.8% |"
    )
