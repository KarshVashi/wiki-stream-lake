"""Print every run summary in docs/runs/ as one Markdown table, for docs/findings.md."""

import json
from pathlib import Path

RUNS_DIR = Path("docs/runs")


def row(summary: dict, name: str) -> str:
    shares = " / ".join(f"{p:.1f}%" for p in summary["percent_per_shard"].values()) or "-"
    minutes = summary["duration_seconds"] / 60
    mode = summary["mode"] + (" (dry run)" if summary["dry_run"] else "")
    return (
        f"| {name} | {mode} | {summary['partition_key']} | {minutes:.0f} | "
        f"{summary['records_sent']:,} | {summary['records_failed']:,} | "
        f"{summary['throttled']:,} | {summary['sent_per_second']:,.1f} | {shares} |"
    )


def main() -> int:
    paths = sorted(RUNS_DIR.glob("*.json"))
    if not paths:
        print("No run summaries in docs/runs/ yet.")
        return 0
    print("| Run | Mode | Key | Minutes | Sent | Failed | Throttled | Sent/s | Split per shard |")
    print("|---|---|---|---:|---:|---:|---:|---:|---|")
    for path in paths:
        print(row(json.loads(path.read_text()), path.stem))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
