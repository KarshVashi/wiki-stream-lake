"""Experiment 4: how long data took to reach S3, and how many files Firehose wrote.

Reads a run summary (from make fetch-runs) and the raw/edits/ objects written while
that run was sending, then reports the delay from the first record sent to the first
file in S3, plus the number and average size of the files.
"""

import argparse
import json
from datetime import datetime, timedelta

import boto3

from run_task import terraform_outputs

# Firehose flushes at most 900 s after a record arrives; allow a little more.
FLUSH_ALLOWANCE = timedelta(seconds=960)


def freshness(first_put_at: datetime, objects: list[dict]) -> dict:
    """objects: [{"LastModified": datetime, "Size": int}, ...] written by this run."""
    if not objects:
        return {"files": 0}
    first_file = min(obj["LastModified"] for obj in objects)
    sizes = [obj["Size"] for obj in objects]
    return {
        "first_put_at": first_put_at.isoformat(),
        "first_file_at": first_file.isoformat(),
        "delay_seconds": round((first_file - first_put_at).total_seconds()),
        "files": len(objects),
        "avg_file_kb": round(sum(sizes) / len(sizes) / 1024, 1),
        "total_mb": round(sum(sizes) / 1024 / 1024, 2),
    }


def day_prefixes(start: datetime, end: datetime) -> list[str]:
    """raw/edits/ day prefixes covering start..end (arrival time, UTC)."""
    prefixes, day = [], start.date()
    while day <= end.date():
        prefixes.append(f"raw/edits/year={day:%Y}/month={day:%m}/day={day:%d}/")
        day += timedelta(days=1)
    return prefixes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", help="a run summary JSON file, e.g. docs/runs/....json")
    args = parser.parse_args()

    summary = json.loads(open(args.summary).read())
    if not summary.get("first_put_at"):
        raise SystemExit("This run sent nothing (a dry run?), so there is nothing to measure.")
    first_put = datetime.fromisoformat(summary["first_put_at"])
    window_end = datetime.fromisoformat(summary["ended_at"]) + FLUSH_ALLOWANCE

    out = terraform_outputs()
    s3 = boto3.client("s3", region_name=out["aws_region"])
    objects = []
    for prefix in day_prefixes(first_put, window_end):
        for page in s3.get_paginator("list_objects_v2").paginate(
            Bucket=out["lake_bucket"], Prefix=prefix
        ):
            objects += [
                o for o in page.get("Contents", []) if first_put <= o["LastModified"] <= window_end
            ]

    print(json.dumps(freshness(first_put, objects), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
