# wiki-stream-lake

A streaming and batch data lake on AWS, fed by the live stream of Wikipedia edits.

Wikimedia's public `recentchange` stream is captured by a small Python producer, sent through Kinesis Data Streams and Firehose into S3, curated into partitioned Parquet with a Glue Spark job, and queried with Athena. Everything is Terraform.

**Status:** S3 lake buckets and a monthly cost budget. Streaming, ETL and query layers to follow.

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
