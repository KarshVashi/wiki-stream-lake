"""Run Athena queries in the project workgroup and record what they cost in data scanned.

    benchmark --date D   Experiment 2: the saved benchmark queries on JSON and on Parquet
    count --date D       Experiment 3: rows in curated_edits for one event_date
    dupes                Experiment 3: event_ids stored more than once (should be 0)

Benchmark results are printed as a table and saved to docs/benchmarks/.
"""

import argparse
import json
import statistics
import time
from datetime import UTC, date, datetime
from pathlib import Path

import boto3

from run_task import terraform_outputs

BENCHMARK_DIR = Path("docs/benchmarks")
DATE_FILTER = "WHERE event_date = ?"


def quoted(value: str) -> str:
    """Athena execution parameters are SQL literals, so strings need single quotes."""
    return "'" + value.replace("'", "''") + "'"


def drop_date_filter(sql: str) -> str:
    """benchmark_curated without its event_date filter, to measure partition pruning alone."""
    lines = sql.splitlines()
    kept = [line for line in lines if line.strip() != DATE_FILTER]
    if len(lines) - len(kept) != 1:
        raise ValueError(f"expected exactly one line '{DATE_FILTER}' in the query")
    return "\n".join(kept)


def benchmark_cases(saved: dict[str, str], day: date) -> dict[str, tuple[str, list[str]]]:
    """Name -> (sql, parameters) for the three Experiment 2 measurements."""
    curated = saved["benchmark_curated"]
    return {
        "raw JSON, one day": (
            saved["benchmark_raw"],
            [quoted(f"{day:%Y}"), quoted(f"{day:%m}"), quoted(f"{day:%d}")],
        ),
        "curated Parquet, one day": (curated, [quoted(day.isoformat())]),
        "curated Parquet, all days": (drop_date_filter(curated), []),
    }


class Athena:
    def __init__(self, out: dict):
        self.client = boto3.client("athena", region_name=out["aws_region"])
        self.workgroup = out["athena_workgroup"]
        self.database = out["glue_database"]

    def saved_queries(self) -> dict[str, str]:
        ids = []
        for page in self.client.get_paginator("list_named_queries").paginate(
            WorkGroup=self.workgroup
        ):
            ids += page["NamedQueryIds"]
        queries = self.client.batch_get_named_query(NamedQueryIds=ids)["NamedQueries"]
        return {q["Name"]: q["QueryString"] for q in queries}

    def run(self, sql: str, parameters: list[str] | None = None) -> dict:
        """Run one query to completion and return its statistics."""
        request = {
            "QueryString": sql,
            "WorkGroup": self.workgroup,
            "QueryExecutionContext": {"Database": self.database},
        }
        if parameters:
            request["ExecutionParameters"] = parameters
        query_id = self.client.start_query_execution(**request)["QueryExecutionId"]
        while True:
            execution = self.client.get_query_execution(QueryExecutionId=query_id)
            state = execution["QueryExecution"]["Status"]["State"]
            if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
                break
            time.sleep(1)
        if state != "SUCCEEDED":
            reason = execution["QueryExecution"]["Status"].get("StateChangeReason", "")
            raise RuntimeError(f"query {state}: {reason}")
        stats = execution["QueryExecution"]["Statistics"]
        return {
            "query_id": query_id,
            "bytes_scanned": stats["DataScannedInBytes"],
            "engine_ms": stats["EngineExecutionTimeInMillis"],
            "total_ms": stats["TotalExecutionTimeInMillis"],
        }

    def rows(self, query_id: str) -> list[list[str]]:
        result = self.client.get_query_results(QueryExecutionId=query_id)
        rows = [[col.get("VarCharValue") for col in r["Data"]] for r in result["ResultSet"]["Rows"]]
        return rows[1:]  # first row is the header


def benchmark(args, athena: Athena) -> None:
    day = date.fromisoformat(args.date)
    cases = benchmark_cases(athena.saved_queries(), day)
    results = {}
    for name, (sql, parameters) in cases.items():
        runs = [athena.run(sql, parameters) for _ in range(args.runs)]
        results[name] = {
            "bytes_scanned": runs[0]["bytes_scanned"],  # the same on every run
            "median_engine_ms": statistics.median(r["engine_ms"] for r in runs),
            "runs": runs,
        }

    print(f"\nExperiment 2, event date {day}, median of {args.runs} runs\n")
    print("| Query | Data scanned | Engine time |")
    print("|---|---:|---:|")
    for name, r in results.items():
        print(f"| {name} | {r['bytes_scanned'] / 1024:,.1f} KB | {r['median_engine_ms']:,.0f} ms |")

    BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = BENCHMARK_DIR / f"{stamp}-benchmark-{day}.json"
    path.write_text(json.dumps({"event_date": str(day), "results": results}, indent=2))
    print(f"\nSaved {path}")


def count(args, athena: Athena) -> None:
    run = athena.run("SELECT count(*) FROM curated_edits WHERE event_date = ?", [quoted(args.date)])
    print(f"curated_edits rows for {args.date}: {athena.rows(run['query_id'])[0][0]}")


def dupes(args, athena: Athena) -> None:
    run = athena.run(athena.saved_queries()["duplicate_check"])
    rows = athena.rows(run["query_id"])
    print(f"event_ids stored more than once: {len(rows)}")
    for event_id, copies in rows[:10]:
        print(f"  {event_id}: {copies} copies")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    bench = commands.add_parser("benchmark")
    bench.add_argument("--date", required=True, help="event date, YYYY-MM-DD")
    bench.add_argument("--runs", type=int, default=3)
    bench.set_defaults(handler=benchmark)
    counting = commands.add_parser("count")
    counting.add_argument("--date", required=True, help="event date, YYYY-MM-DD")
    counting.set_defaults(handler=count)
    commands.add_parser("dupes").set_defaults(handler=dupes)

    args = parser.parse_args()
    args.handler(args, Athena(terraform_outputs()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
