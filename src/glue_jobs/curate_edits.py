"""Glue job: build curated_edits (Snappy Parquet, partitioned by event_date) from raw_edits.

Incremental (default): job bookmarks find the raw files that arrived since the last
successful run, and every event_date those files touch is rebuilt from raw.

Backfill (--backfill_date YYYY-MM-DD, run with bookmarks disabled): rebuild that one
event_date.

Both modes overwrite whole event_date partitions, so running the job again gives the
same result instead of duplicate rows.
"""

import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from transforms import curate, event_dates_in, raw_partition_predicate

args = getResolvedOptions(sys.argv, ["JOB_NAME", "database", "raw_table", "curated_path"])
backfill_date = (
    getResolvedOptions(sys.argv, ["backfill_date"])["backfill_date"]
    if "--backfill_date" in sys.argv
    else None
)

glue = GlueContext(SparkContext.getOrCreate())
spark = glue.spark_session
spark.conf.set("spark.sql.session.timeZone", "UTC")
# Overwrite only the event_date partitions being written, not the whole table.
spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")
job = Job(glue)
job.init(args["JOB_NAME"], args)
log = glue.get_logger()


def read_raw(**options):
    catalog = {"database": args["database"], "table_name": args["raw_table"]}
    raw = glue.create_dynamic_frame.from_catalog(**catalog, **options)
    # A DynamicFrame keeps a column whose values vary in type (e.g. int in some rows,
    # long in others) as a "choice", which becomes a struct in a DataFrame. Resolve
    # every such column to the type the crawler recorded in the catalog.
    return raw.resolveChoice(choice="match_catalog", **catalog).toDF()


if backfill_date:
    event_dates = [backfill_date]
else:
    # transformation_ctx is what the bookmark tracks: this read returns only new files.
    new_raw = read_raw(transformation_ctx="raw_edits_new")
    event_dates = [] if new_raw.isEmpty() else event_dates_in(new_raw)

if event_dates:
    log.info(f"Rebuilding event_date partitions: {event_dates}")
    raw = read_raw(push_down_predicate=raw_partition_predicate(event_dates))
    (
        curate(raw, event_dates)
        .repartition("event_date")  # one file per partition at this data volume
        .write.mode("overwrite")
        .partitionBy("event_date")
        .option("compression", "snappy")
        .parquet(args["curated_path"])
    )
else:
    log.info("No new raw data since the last run")

job.commit()
