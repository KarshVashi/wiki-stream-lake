import os
import subprocess

import pytest
from transforms import CURATED_COLUMNS, curate, event_dates_in, raw_partition_predicate


def test_predicate_reads_the_day_before_the_day_and_the_day_after():
    # The day before matters: a Firehose buffer opened just before midnight is filed
    # under that day but holds edits from after midnight (seen on 24-25 Oct 2026).
    assert raw_partition_predicate(["2026-10-31"]) == (
        "(year='2026' AND month='10' AND day='30') OR "
        "(year='2026' AND month='10' AND day='31') OR "
        "(year='2026' AND month='11' AND day='01')"
    )


def test_predicate_merges_overlapping_days():
    predicate = raw_partition_predicate(["2026-10-21", "2026-10-20"])
    assert predicate.count("day=") == 4  # 19, 20, 21, 22


def test_predicate_rejects_a_bad_date():
    with pytest.raises(ValueError):
        raw_partition_predicate(["21-10-2026"])


# ---------------------------------------------------------------- Spark tests


# Types as the crawler infers them from the raw JSON: event_time is still a string.
RAW_SCHEMA = (
    "event_id string, event_time string, domain string, wiki string, type string, "
    "namespace int, title string, user_name string, is_anonymous boolean, is_bot boolean, "
    "is_minor boolean, comment string, length_old int, length_new int, "
    "revision_old bigint, revision_new bigint"
)


def java_available() -> bool:
    """True if a real JDK runs. macOS has a /usr/bin/java stub that only prints an error."""
    try:
        return subprocess.run(["java", "-version"], capture_output=True).returncode == 0
    except FileNotFoundError:
        return False


@pytest.fixture(scope="module")
def spark():
    if not java_available():
        if os.environ.get("CI"):
            pytest.fail("Spark tests need Java in CI")
        pytest.skip("no JDK found; Spark tests run in CI")
    from pyspark.sql import SparkSession

    session = (
        SparkSession.builder.master("local[1]")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "1")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    yield session
    session.stop()


def raw_df(spark, *rows):
    return spark.createDataFrame(rows, RAW_SCHEMA)


def raw_row(event_id, event_time, **overrides):
    row = {
        "event_id": event_id,
        "event_time": event_time,
        "domain": "en.wikipedia.org",
        "wiki": "enwiki",
        "type": "edit",
        "namespace": 0,
        "title": "Page",
        "user_name": "Someone",
        "is_anonymous": False,
        "is_bot": False,
        "is_minor": None,
        "comment": "c",
        "length_old": 100,
        "length_new": 150,
        "revision_old": 1,
        "revision_new": 2,
    }
    row.update(overrides)
    return tuple(row.values())


def test_curate_types_filters_dedupes_and_adds_size_delta(spark):
    raw = raw_df(
        spark,
        raw_row("a", "2026-10-21T10:00:00.123Z"),
        raw_row("a", "2026-10-21T10:00:00.123Z"),  # duplicate delivery
        raw_row("b", "2026-10-21T23:59:59Z", length_old=None),
        raw_row("c", "2026-10-22T00:00:01Z"),  # next day, filtered out
    )
    rows = {r.event_id: r for r in curate(raw, ["2026-10-21"]).collect()}

    assert sorted(rows) == ["a", "b"]
    assert rows["a"].size_delta == 50
    assert rows["a"].event_date == "2026-10-21"
    assert rows["a"].event_time.year == 2026
    assert rows["b"].size_delta is None  # new pages have no old length


def test_curate_output_columns_and_types(spark):
    raw = raw_df(spark, raw_row("a", "2026-10-21T10:00:00Z"))
    curated = curate(raw, ["2026-10-21"])
    types = dict(curated.dtypes)
    assert curated.columns == CURATED_COLUMNS
    assert types["event_time"] == "timestamp"
    assert types["namespace"] == "int"
    assert types["is_minor"] == "boolean"
    assert types["size_delta"] == "bigint"


def test_curate_fills_columns_the_crawler_did_not_see(spark):
    raw = spark.createDataFrame(
        [("a", "2026-10-21T10:00:00Z")], "event_id string, event_time string"
    )
    row = curate(raw, ["2026-10-21"]).collect()[0]
    assert row.title is None
    assert row.is_minor is None


def test_event_dates_in_uses_utc(spark):
    raw = raw_df(spark, raw_row("a", "2026-10-21T23:30:00Z"), raw_row("b", "2026-10-22T00:30:00Z"))
    assert event_dates_in(raw) == ["2026-10-21", "2026-10-22"]
