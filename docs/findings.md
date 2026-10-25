# Findings

Measured results from four experiments on the pipeline. Every number here comes from a run summary in [`runs/`](runs/), a benchmark file in [`benchmarks/`](benchmarks/), or the AWS console. Cells stay blank until they have been measured.

## The dataset

| | Value |
|---|---|
| Capture window (UTC) | |
| Events read from Wikimedia | |
| Records kept by the transform Lambda (`raw_edits` rows) | |
| Rows in `curated_edits` | |
| Event dates covered | |
| Size of `raw/edits/` (gzip JSON) | |
| Size of `curated/edits/` (Snappy Parquet) | |

How: `make fetch-runs` for the capture summary; `SELECT count(*)` on each table; S3 console **Calculate total size** on each prefix.

---

## Experiment 1: the hot shard

Kinesis sends each record to a shard by hashing its partition key. A key with a few very common values (the wiki's domain) piles records onto one shard; a unique key (the event ID) spreads them evenly.

### Part A: uneven split on the live stream (2 shards)

| Partition key | Minutes | Records sent | Shard 0 | Shard 1 | Throttled |
|---|---:|---:|---:|---:|---:|
| `domain` | 20 | | | | |
| `event_id` | 20 | | | | |

How: `make capture MINUTES=20 KEY=domain`, then the same with `KEY=event_id`, then `make fetch-runs`. Screenshot the stream's **Incoming data (count)** graph for both runs.

At live volume (about 40 records per second) no throttling is expected: each shard accepts 1,000 records per second.

### Part B: throttling on a replay (4 shards)

| Partition key | Target rate (rec/s) | Achieved rate (rec/s) | Busiest shard | Quietest shard | Throttled records |
|---|---:|---:|---:|---:|---:|
| `domain` | | | | | |
| `event_id` | | | | | |

How: `make apply REPLAY=true`, then `make replay SOURCE=raw/edits/year=…/month=…/day=…/ KEY=domain`, then the same with `KEY=event_id`, then `make fetch-runs` and `make apply REPLAY=false`. Screenshot the replay stream's **Write throughput exceeded** graph.

**What it shows:**

---

## Experiment 2: JSON versus Parquet

The same aggregation (edits, bot edits and bytes added, per wiki) on the same day, once on gzip JSON and once on Snappy Parquet.

| Query | Data scanned | Engine time (median of 3) |
|---|---:|---:|
| `raw_edits`, gzip JSON, one day | | |
| `curated_edits`, Parquet, one day | | |
| `curated_edits`, Parquet, all days (no partition filter) | | |

How: `make benchmark DATE=YYYY-MM-DD`. The results are saved in `docs/benchmarks/`.

Comparing the first two rows shows the effect of the columnar format; comparing the last two shows the effect of partition pruning. Cost is not compared: Athena bills at least 10 MB per query, and at this data volume every query falls under that minimum.

**What it shows:**

### What the curate job cost

| Run | Duration | DPU-seconds | DPU-hours | Cost at the region's price per DPU-hour |
|---|---:|---:|---:|---:|
| ETL after the long capture | | | | |

How: `make job-status`. DPU-hours = DPU-seconds / 3600.

---

## Experiment 3: replay with no duplicates

Rebuilding a day from raw must give the same result every time, so the pipeline can recover from a bug by simply running again.

| Step | `curated_edits` rows for the day | Duplicate `event_id`s |
|---|---:|---:|
| Before | | |
| After backfill #1 | | |
| After backfill #2 | | |

How: `make count DATE=…`, `make backfill DATE=…` (wait for `make job-status` to show SUCCEEDED), `make count DATE=…`, again, then `make dupes`.

**What it shows:**

---

## Experiment 4: the freshness trade-off

Firehose writes a file when its buffer fills (5 MB) or its time limit passes. A shorter limit means fresher data and more, smaller files.

| Buffer limit | Delay to first file | Files in 15 minutes | Average file size |
|---:|---:|---:|---:|
| 60 s | | | |
| 120 s (default) | | | |
| 300 s | | | |

How: for each limit, `make apply BUFFER=60`, `make capture MINUTES=15`, `make fetch-runs`, then `make freshness RUN=docs/runs/<that run>.json`. Return to the default with `make apply`.

At roughly 10 KB per second of cleaned data, even a 300-second buffer holds only about 3 MB, so the 5 MB size limit is never reached and the time limit decides every flush.

**What it shows:**
