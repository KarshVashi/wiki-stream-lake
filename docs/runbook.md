# Runbook

Every command runs from the repo root. They use the AWS CLI profile `wiki-lake` unless `AWS_PROFILE` is set. If a command says the SSO token has expired, run `aws sso login --profile wiki-lake`.

## Switches on every apply

`make plan` and `make apply` always pass three settings, so the state of anything billable is stated in the command rather than remembered in a file:

| Variable | Default | Controls |
|---|---|---|
| `STREAMING` | `true` | the Kinesis stream, Firehose and transform Lambda |
| `REPLAY` | `false` | the 4-shard replay stream for Experiment 1 |
| `BUFFER` | `120` | Firehose's buffer time limit in seconds |

A plain `make apply` therefore brings the stream back, removes the replay stream and resets the buffer.

## A capture session

```sh
make apply                  # stream on: expect "10 to add" if it was down
make image                  # only if src/producer/ changed since the last push
make capture                # 12 hours; or HOURS=3, MINUTES=20, KEY=domain
make logs                   # optional: progress every 30 seconds
```

`make capture` returns once the task has started. The task stops itself at the end of its duration and writes a summary to `runs/`. To stop early: `make capture-stop`, which still writes the summary.

When the task has stopped:

```sh
make fetch-runs             # summaries to docs/runs/, printed as a table
# wait about 5 minutes for Firehose to write its last buffer
make stream-down            # remove the stream; the lake stays
make run-etl                # crawler, then the curate job
make job-status             # wait for SUCCEEDED
```

## Rebuild a day (backfill)

```sh
make backfill DATE=2026-10-24
make job-status             # wait for SUCCEEDED
make count DATE=2026-10-24
```

Backfill ignores job bookmarks and overwrites only that day's partition, so it is safe to repeat.

## Replay (Experiment 1, part B)

```sh
make apply REPLAY=true                      # adds the 4-shard replay stream
make replay SOURCE=raw/edits/year=2026/month=10/day=24/ KEY=domain RATE=2500
make replay SOURCE=raw/edits/year=2026/month=10/day=24/ KEY=event_id RATE=2500
make fetch-runs
make apply REPLAY=false STREAMING=false     # remove it straight away
```

Each replay runs for 10 minutes by default (`MINUTES=`). Run them one after the other, not at the same time. If the summary shows an achieved rate well under `RATE`, give the task more CPU for that run only: `CPU=512` or `CPU=1024`.

## Benchmarks and checks

```sh
make benchmark DATE=2026-10-24   # Experiment 2, saved to docs/benchmarks/
make dupes                       # duplicate event_ids in curated_edits: should be 0
make freshness RUN=docs/runs/<summary>.json   # Experiment 4
```

## Tear down

```sh
make stream-down            # between sessions: only the streams cost money while idle
make destroy                # everything, including the data
```

Check the Billing console the next day.

## When something fails

| Symptom | Cause and fix |
|---|---|
| `Token has expired and refresh failed` | `aws sso login --profile wiki-lake` |
| `No edits stream exists` from `make capture` | The stream is down: `make apply`. |
| Task stops with `CannotPullContainerError` | No image in ECR: `make image`. |
| `run-task` mentions a service-linked role | First ECS use in the account: `aws iam create-service-linked-role --aws-service-name ecs.amazonaws.com`, then retry. |
| Curate job: `cannot cast "STRUCT<int, long>"` | A column with mixed number types. The job resolves these against the catalog (`resolveChoice`); if a new column does this, check its type in `raw_edits`. |
| Athena: `Column '2026' cannot be resolved` or `varchar = integer` | Parameter typed without single quotes. Enter `'2026'`, not `2026` or `"2026"`. |
