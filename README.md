# wiki-stream-lake

A streaming and batch data lake on AWS, fed by the live stream of Wikipedia edits.

Wikimedia's public `recentchange` stream is captured by a small Python producer running as a one-off ECS Fargate task, sent through Kinesis Data Streams and Firehose into S3, curated into partitioned Parquet with a Glue Spark job, and queried with Athena. Everything is Terraform.

**Status:** producer on ECS Fargate, Kinesis Data Stream, and Firehose with a transform Lambda landing cleaned JSON in S3. ETL and query layers to follow.

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
