# wiki-stream-lake

A streaming and batch data lake on AWS, fed by the live stream of Wikipedia edits.

Wikimedia's public `recentchange` stream is captured by a small Python producer running as a one-off ECS Fargate task, sent through Kinesis Data Streams and Firehose into S3, curated into partitioned Parquet with a Glue Spark job, and queried with Athena. Everything is Terraform.

**Status:** S3 lake buckets, a monthly cost budget, and the producer as a container on ECS Fargate. Streaming, ETL and query layers to follow.

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
