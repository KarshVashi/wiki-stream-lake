# Findings

Measured results from four experiments on the pipeline, run between 21 and 27 October 2026 in `eu-west-2`. Every number comes from a run summary in [`runs/`](runs/), a benchmark file in [`benchmarks/`](benchmarks/), Athena, S3 or the Glue job history.

All sizes are in decimal megabytes (1 MB = 1,000,000 bytes).

## The dataset

| | Value |
|---|---|
| Main capture | 12 hours, 2026-10-24 18:24 → 2026-10-25 06:24 UTC |
| Events read from Wikimedia and sent to Kinesis | 1,674,104 (38.8 per second; 0 failed, 0 throttled) |
| Kept by the transform Lambda | 844,371 of the capture's records (50.4%; the rest are mostly `categorize` events), plus 2,936 from a 5-minute test on 21 Oct: 847,307 `raw_edits` rows |
| Rows in `curated_edits` | 847,303 (4 duplicate `event_id`s removed) |
| Event dates | 2026-10-21 (2,936), 2026-10-24 (430,963), 2026-10-25 (413,404) |
| Edit types | 662,999 `edit` · 109,077 `new` · 75,227 `log` |
| Wikis | 417; Commons 25.7%, Wikidata 24.5%, English Wikipedia 11.0% |
| Bot edits | 448,988 (53.0%) |
| Users masked as `anonymous` | 22,786 (2.7%) |
| `raw/edits/` for the 12-hour capture | 751 gzip JSON files, 81.9 MB |
| `curated/edits/` | 3 Snappy Parquet files, 102.0 MB |

The Parquet copy is larger than the gzip JSON on disk. Its advantage is in what a query has to read, which Experiment 2 measures.

---

## Experiment 1: the hot shard

Kinesis sends each record to a shard by hashing its partition key with MD5. A key with a few very common values (the wiki's domain) piles records onto one shard; a unique key (the event ID) spreads them evenly.

### Part A: uneven split on the live stream (2 shards)

| Partition key | Run | Records sent | Shard 0 | Shard 1 | Throttled |
|---|---|---:|---:|---:|---:|
| `domain` | 20 minutes, 26 Oct | 113,076 | 60.2% | 39.8% | 0 |
| `event_id` | 20 minutes, 27 Oct | 37,551 | 50.0% | 50.0% | 0 |
| `event_id` | 12 hours, 24–25 Oct | 1,674,104 | 50.1% | 49.9% | 0 |

At live volume (about 30 to 95 records per second) nothing is throttled: each shard accepts 1,000 records per second. How uneven a `domain` key is depends on which wikis are busiest while it runs: the 26 October run, at an unusually high 94 records per second, put 60% on one shard. Part B shows the same key on 4 shards, under load.

### Part B: throttling on a replay (4 shards)

The same 847,307 captured records were resent from S3 into a separate 4-shard stream at a target of 2,500 records per second, once per key.

| Partition key | Achieved rate (rec/s) | Busiest shard | Quietest shard | Throttled records | Lost records |
|---|---:|---:|---:|---:|---:|
| `domain` | 2,089 | 50.1% | 4.3% | 158,929 | 0 |
| `event_id` | 2,498 | 25.0% | 24.9% | 0 | 0 |

**What it shows:** with `domain` as the key, Commons and English Wikipedia hash to the same shard, so one shard received half of all records while another received 4%. At 2,500 records per second that shard needed about 1,250 per second against a limit of 1,000. Kinesis rejected records 158,929 times with `ProvisionedThroughputExceededException`, a number equal to 19% of the records sent, and the retries cut throughput by 16%. Nothing was lost, because the producer resends only the rejected records. With `event_id`, the four shards were within 0.1% of each other, nothing was throttled and the target rate held. A skewed key wastes capacity at any volume and causes throttling once traffic grows; adding shards would not have helped, because the hot key always maps to one shard.

---

## Experiment 2: JSON versus Parquet

The same aggregation (edits, bot edits and bytes added, per wiki) on the same day, 2026-10-24, once on gzip JSON and once on Snappy Parquet.

| Query | Data scanned | Engine time (median of 3) |
|---|---:|---:|
| `raw_edits`, gzip JSON, one day | 43.1 MB | 1,253 ms |
| `curated_edits`, Parquet, one day | 1.14 MB | 697 ms |
| `curated_edits`, Parquet, all days (no partition filter) | 2.19 MB | 813 ms |

**What it shows:** Parquet cut the data scanned by **38×** for the same answer. Athena read only the 3 columns the query uses (1.14 MB of a 52.7 MB file), while for JSON it had to read and decompress every byte of the day's files. Removing the `event_date` filter roughly doubled the Parquet scan, because Athena then read all three days instead of one: that difference is partition pruning on its own. Run time improved less (1.8×), because at this size every query is dominated by fixed startup cost.

Cost was not compared: Athena bills at least 10 MB per query, so the Parquet queries are billed the same 10 MB whether they scan 1 MB or 2 MB. At scale, Athena's cost is proportional to bytes scanned, so the 38× ratio is the one that matters.

### What the curate job cost

Glue 5.1, 2 G.1X workers, $0.44 per DPU-hour in `eu-west-2`.

| Run | Duration | DPU-seconds | DPU-hours | Cost |
|---|---:|---:|---:|---:|
| Incremental ETL after the 12-hour capture (2 days, 844,367 rows) | 209 s | 419 | 0.116 | $0.051 |
| Backfill of 2026-10-24, #1 | 188 s | 377 | 0.105 | $0.046 |
| Backfill of 2026-10-24, #2 | 243 s | 487 | 0.135 | $0.060 |

---

## Experiment 3: replay with no duplicates

Rebuilding a day from raw must give the same result every time, so the pipeline can recover from a bug by simply running again.

| Step | `curated_edits` rows for 2026-10-24 | Duplicate `event_id`s |
|---|---:|---:|
| Before | 430,963 | 0 |
| After backfill #1 | 430,963 | 0 |
| After backfill #2 | 430,963 | 0 |

**What it shows:** the job overwrites whole `event_date` partitions, so running it again replaced the day with identical content instead of appending a second copy. The same mechanism removed 4 real duplicates that had reached `raw/`.

**A problem this experiment did not catch.** Reconciling row counts afterwards showed that 1,209 edits made on 2026-10-25 between 00:00:00 and 00:01:16 are stored in `raw/` under 2026-10-24, hour 23. Firehose names each file's partition by the time its buffer *started*, and two buffers opened at 23:59 kept filling past midnight. The job assumed an edit on day D can only be filed under D or D+1, so a backfill of 2026-10-25 would have read only the 25th and 26th and silently dropped those 1,209 rows. The incremental run was unaffected, because it rebuilt both days together, and the backfill of the 24th was unaffected, because nothing from the 24th was filed under the 23rd. The job now reads D-1, D and D+1 for every day it rebuilds. After the fix was deployed, a backfill of 2026-10-25 returned 413,404 rows, the same as the incremental run, with 0 duplicates.

---

## Experiment 4: the freshness trade-off

Firehose writes a file when its buffer fills (5 MB) or its time limit passes. A shorter limit means fresher data and more, smaller files.

| Buffer limit | Delay to first file | Files written | Files per hour | Average file size | Records/s during run | Run |
|---:|---:|---:|---:|---:|---:|---|
| 60 s | 67 s | 36 | 144 | 41.9 KB | 31.6 | 15 minutes, 27 Oct |
| 120 s (default) | 120–121 s | 751 | 63 | 106.4 KB | 38.8 | 12 hours, 24–25 Oct |
| 300 s | 301 s | 8 | 32 | 168.7 KB | 31.1 | 15 minutes, 27 Oct |

How: `make apply BUFFER=…`, `make capture MINUTES=15`, `make fetch-runs`, then `make freshness RUN=…`. The 120 s figures come from the 12-hour capture; its 5- and 20-minute runs gave the same 120–121 s delay.

**What it shows:** the delay to the first file equals the buffer limit almost exactly (67, 121 and 301 seconds), because at roughly 10 KB per second of cleaned data even a 300 s buffer holds well under the 5 MB size limit, so the time limit decides every flush. The cost of freshness is file count: going from 300 s to 60 s cut the delay by 4.5× and multiplied the files by 4.5× while making each one a quarter of the size. Firehose keeps one buffer per Kinesis shard, so with 2 shards it writes about two files per interval (63 per hour at 120 s, not 30). The 15-minute runs also include the final partial files written when the run stops, which raises their per-hour rate slightly. The edit rate differed between runs (31 against 39 records per second), so file sizes compare across the 15-minute runs more fairly than against the 12-hour one.

Many small files make every later step slower and costlier: Athena and Glue open each file separately, and S3 charges per request. The curate job compacts them back into one Parquet file per day, which is why the default of 120 s is a reasonable middle point for this pipeline.

---

## Notes

- **Wikimedia outage.** From 23:59 UTC on 26 October, `stream.wikimedia.org` returned 502 and 503 errors for over 20 minutes and was still intermittent at 00:20. The run that was due then (279 records) is kept in `runs/` as a record of the outage and not used in any result; the 20-minute `event_id` run was repeated on 27 October. The producer reconnected with backoff, as designed, but the outage exposed a bug: a run's deadline was only checked when an event arrived, so with no events the task would not stop on time. Reconnects now check the deadline too, and a 1-minute test during the outage stopped after 61 seconds.
- **Glue version.** The job runs on Glue 5.1. The region's price list also shows Glue 6.0 at $0.308 per DPU-hour, 30% less; moving to it would need the job and its tests checked against its Spark and Python versions.
