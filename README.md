# wiki-stream-lake

A streaming and batch data lake on AWS, fed by the live stream of Wikipedia edits.

Wikimedia's public `recentchange` stream is captured by a small Python producer running as a one-off ECS Fargate task, sent through Kinesis Data Streams and Firehose into S3, curated into partitioned Parquet with a Glue Spark job, and queried with Athena. Everything is Terraform.

**Status:** the full pipeline is in place, from the live stream to SQL in Athena. Experiments and findings to follow.

## Quick start

Needs Terraform 1.6 or later, AWS CLI v2, and `uv` (which installs Python 3.12 for you).

```sh
make setup   # install Python and dev dependencies
make lint    # ruff, terraform fmt, terraform validate
make test    # pytest
```

To deploy, copy `infra/terraform.tfvars.example` to `infra/terraform.tfvars`, fill in the alert email, and use an AWS CLI profile named `wiki-lake` (or set `AWS_PROFILE`):

```sh
make plan    # review the changes
make apply   # asks for confirmation
```

Run `make help` to list every target.

## The producer

`src/producer/` reads the live stream (Server-Sent Events), batches events into Kinesis `PutRecords` calls, retries only the records that fail, and counts records per shard. It runs as a Fargate task that stops itself when its duration ends and writes a run summary to `s3://<lake bucket>/runs/`.

```sh
make dry-run MINUTES=1                    # locally: print live events, send nothing
make image                                # build the container and push it to ECR
make capture MINUTES=2 ARGS="--dry-run"   # same dry run, on Fargate
make logs                                 # follow the task's logs
```

## Streaming into the lake

The producer writes to a 2-shard Kinesis Data Stream. Firehose reads the stream, passes each batch through a Lambda (`src/transform_lambda/`), and writes gzip JSON lines to `raw/edits/year=/month=/day=/hour=/`, partitioned by the hour each record **arrived**. The Lambda:

- drops canary events and every type except `edit`, `new` and `log`;
- flattens each event to 16 fixed fields;
- replaces temporary-account names and IP addresses with `anonymous`, in the user field and inside titles and comments.

The stream bills per shard-hour even when idle, so remove it between sessions; the lake and everything else stay in place:

```sh
make stream-down              # same as: make apply STREAMING=false
make apply                    # brings it back
```

## Curating with Glue

`make run-etl` starts a Glue workflow:

1. A **crawler** reads `raw/edits/` and registers the table `raw_edits` (partitions `year/month/day/hour`, by arrival time) in the Glue Data Catalog.
2. When the crawl succeeds, a **Spark job** (`src/glue_jobs/curate_edits.py`, 2 G.1X workers) finds the raw files that are new since its last run, using job bookmarks, works out which event dates they contain, and rebuilds each of those `event_date` partitions from raw: typed columns, `size_delta`, duplicates removed, written as Snappy Parquet.

The result is `curated_edits`, a table defined in Terraform with partition projection, so Athena knows its partitions without a crawler. Because each run overwrites whole partitions, re-running it is safe:

```sh
make backfill DATE=2026-10-21   # rebuild one day from raw, same result every time
```

The transform logic lives in `src/glue_jobs/transforms.py` with no Glue imports, so it is tested with local PySpark (needs Java).

## Querying with Athena

Queries run in the `wiki-lake-dev` Athena workgroup. Its settings are enforced, so clients cannot override them:

- results go to the Athena results bucket and expire after 7 days;
- any query that would scan more than 1 GB is cancelled;
- bytes scanned per query are published to CloudWatch.

Every file in `sql/` is registered as a saved query of the same name. A `?` in a query is a parameter that the Athena console asks for when you run it.

| Query | What it answers |
|---|---|
| `top_wikis` | Which wikis get the most edits |
| `bots_vs_humans` | Share of edits made by bots, per wiki |
| `edits_per_minute` | Edit rate through one day |
| `largest_changes` | Biggest additions and removals of text on one day |
| `duplicate_check` | Any `event_id` stored twice (must return nothing) |
| `benchmark_raw` / `benchmark_curated` | The same aggregation on gzip JSON and on Parquet, to compare data scanned |
