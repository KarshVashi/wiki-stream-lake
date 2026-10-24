"""Transformation logic for the curate_edits Glue job.

Kept free of Glue imports so it can be unit-tested with plain local PySpark.
Glue 5.1 runs Python 3.11, so nothing here may use newer syntax.
"""

from collections.abc import Iterable
from datetime import date, timedelta

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

# Every column the transform Lambda writes, with the type it should have.
COLUMN_TYPES = {
    "event_id": "string",
    "event_time": "timestamp",
    "domain": "string",
    "wiki": "string",
    "type": "string",
    "namespace": "int",
    "title": "string",
    "user_name": "string",
    "is_anonymous": "boolean",
    "is_bot": "boolean",
    "is_minor": "boolean",
    "comment": "string",
    "length_old": "bigint",
    "length_new": "bigint",
    "revision_old": "bigint",
    "revision_new": "bigint",
}
CURATED_COLUMNS = [*COLUMN_TYPES, "size_delta", "event_date"]


def raw_partition_predicate(event_dates: Iterable[str]) -> str:
    """Glue push-down predicate for the raw partitions that can hold these event dates.

    raw/ is partitioned by arrival time. An edit made on day D arrives on day D, or on
    D+1 if it happened just before midnight, so both days are read.
    """
    days = set()
    for event_date in event_dates:
        day = date.fromisoformat(event_date)
        days.update([day, day + timedelta(days=1)])
    return " OR ".join(f"(year='{d:%Y}' AND month='{d:%m}' AND day='{d:%d}')" for d in sorted(days))


def event_dates_in(raw: DataFrame) -> list[str]:
    """The distinct event dates (UTC, yyyy-MM-dd) present in a raw DataFrame."""
    rows = (
        raw.select(F.date_format(F.col("event_time").cast("timestamp"), "yyyy-MM-dd").alias("d"))
        .distinct()
        .collect()
    )
    return sorted(row.d for row in rows if row.d)


def curate(raw: DataFrame, event_dates: Iterable[str]) -> DataFrame:
    """Typed, deduplicated rows for the given event dates, with size_delta and event_date."""
    typed = raw.select(
        [
            (F.col(name) if name in raw.columns else F.lit(None)).cast(type_).alias(name)
            for name, type_ in COLUMN_TYPES.items()
        ]
    )
    return (
        typed.withColumn("event_date", F.date_format("event_time", "yyyy-MM-dd"))
        .where(F.col("event_date").isin(list(event_dates)))
        .withColumn("size_delta", F.col("length_new") - F.col("length_old"))
        .dropDuplicates(["event_id"])
        .select(CURATED_COLUMNS)
    )
