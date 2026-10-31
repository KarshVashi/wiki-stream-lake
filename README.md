# wiki-stream-lake

A streaming and batch data lake on AWS, fed by the live stream of Wikipedia edits.

Wikimedia publishes every edit to every Wikipedia, Wikidata and Commons page as a public stream. This project captures it with a Python producer on ECS Fargate, moves it through Kinesis Data Streams and Firehose into S3, curates it into partitioned Parquet with a Glue Spark job, and queries it with Athena. Everything is Terraform, and four experiments measure the trade-offs.

```mermaid
flowchart LR
    W[Wikimedia<br/>EventStreams] --> P[Producer<br/>Fargate task]
    P --> K[Kinesis<br/>2 shards]
    K --> F[Firehose +<br/>Lambda transform]
    F --> R[(S3 raw/<br/>gzip JSON)]
    R --> G[Glue crawler<br/>+ Spark job]
    G --> C[(S3 curated/<br/>Parquet)]
    C --> A[Athena]
    R --> A
```

## Findings

Measured results, with how each was measured, are in [docs/findings.md](docs/findings.md).

| Experiment | Question | Result |
|---|---|---|
| Hot shard | What does a skewed partition key do to Kinesis shards? | Keyed by wiki, one of 4 shards got 50% of records and another 4%. Replayed at 2,500 records/s, Kinesis rejected writes 158,929 times and throughput fell 16%. Keyed by event ID: 25% per shard, no throttling. |
| JSON vs Parquet | How much less does Athena scan on partitioned Parquet? | 38× less for the same query (43.1 MB → 1.14 MB); dropping the date filter doubles the Parquet scan. |
| Replay | Does re-running the curate job create duplicates? | No: 430,963 rows before and after two backfills, 0 duplicates. Reconciling counts also exposed a midnight edge case, now fixed. |
| Freshness | What does the Firehose buffer cost in delay, and in file count? | The first file lands after almost exactly the buffer limit: 67 s at 60 s, 121 s at 120 s, 301 s at 300 s. Going from 300 s to 60 s gave 4.5× more files, each a quarter of the size. |

Data: a 12-hour capture of 1.67 million events on 24–25 October 2026, of which 844,371 were kept after cleaning. With 2,936 rows from a 5-minute test on 21 October and 4 duplicates removed, `curated_edits` holds 847,303 rows.

## How it works

1. **Producer** (`src/producer/`): reads the Server-Sent Events stream, reconnecting and resuming from the last event ID; batches records into `PutRecords` calls, retrying only the records that fail; counts records per shard. It runs as a one-off Fargate task that stops itself when its time is up and writes a run summary to S3.
2. **Stream and delivery**: a 2-shard Kinesis Data Stream feeds Firehose, which writes gzip JSON to `raw/edits/`, partitioned by arrival hour.
3. **Transform Lambda** (`src/transform_lambda/`): drops canary and categorisation events, flattens each event to 16 fields, and replaces IP addresses and temporary-account names with `anonymous`, including inside titles and comments.
4. **Catalog and ETL** (`src/glue_jobs/`): a Glue workflow runs a crawler that registers `raw_edits`, then a Spark job that rebuilds each affected day of `curated_edits` as typed, deduplicated Snappy Parquet, partitioned by the date of the edit. Every run overwrites whole days, so re-running is safe.
5. **Query**: an Athena workgroup with a 1 GB scan limit per query, and saved queries from [`sql/`](sql/).

Design decisions and trade-offs: [docs/architecture.md](docs/architecture.md).

## Running it

Needs an AWS account, Terraform 1.6 or later, AWS CLI v2, Docker, and `uv` (which installs Python 3.12). The Spark tests also need Java.

```sh
make setup && make lint && make test

cp infra/terraform.tfvars.example infra/terraform.tfvars   # add the alert email
make apply        # everything, including the stream
make image        # build and push the producer image
make capture      # 12-hour capture on Fargate
# ...when the task has stopped:
make stream-down  # stop the stream's hourly charge
make run-etl      # crawl, then curate
```

The full routine, the experiments and fixes for common errors are in [docs/runbook.md](docs/runbook.md). `make help` lists every command.

## Cost

A 12-hour capture session, including the ETL, costs about $1. Only the Kinesis streams bill while idle, so they exist only during capture sessions. Everything else bills per use, and a $10 monthly budget sends alerts at 50, 80 and 100%.

## Repo layout

```text
infra/          Terraform: root module and storage, producer_task, streaming,
                replay_stream, catalog_etl, query and guardrails modules
src/producer/   SSE client, Kinesis writer, replay mode, Dockerfile
src/transform_lambda/   Firehose transformation function
src/glue_jobs/  curate_edits.py and its testable transforms
sql/            Athena saved queries
scripts/        helpers behind the make targets (tasks, benchmarks, freshness)
tests/          pytest, including local PySpark tests
docs/           architecture, runbook, findings, run summaries, benchmarks
```
