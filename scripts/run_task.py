"""Start or stop the producer's Fargate task. Called by make capture and make capture-stop.

Cluster, subnets, security group and bucket names come from `terraform output`,
so nothing here is hard-coded to one account.
"""

import argparse
import json
import os
import subprocess
import sys

import boto3


def terraform_outputs() -> dict:
    result = subprocess.run(
        [os.environ.get("TF", "terraform"), "-chdir=infra", "output", "-json"],
        check=True,
        capture_output=True,
        text=True,
    )
    return {name: output["value"] for name, output in json.loads(result.stdout).items()}


def producer_command(
    mode: str, minutes: int, key: str, stream: str | None, bucket: str, extra: list[str]
) -> list[str]:
    """Arguments passed to `python -m producer` inside the container."""
    command = [mode, "--partition-key", key, "--duration-minutes", str(minutes)]
    command += ["--summary-bucket", bucket]
    if stream:
        command += ["--stream-name", stream]
    return command + extra


def capture(args: argparse.Namespace, out: dict) -> int:
    minutes = args.minutes or args.hours * 60
    dry_run = "--dry-run" in args.extra
    stream = out.get("edits_stream_name")
    if not stream and not dry_run:
        sys.exit("No edits stream exists (streaming is off). Run make apply first.")

    command = producer_command("capture", minutes, args.key, stream, out["lake_bucket"], args.extra)
    ecs = boto3.client("ecs", region_name=out["aws_region"])
    response = ecs.run_task(
        cluster=out["ecs_cluster"],
        taskDefinition=out["producer_task_family"],
        launchType="FARGATE",
        count=1,
        startedBy="make-capture",
        networkConfiguration={
            "awsvpcConfiguration": {
                "subnets": out["producer_subnets"],
                "securityGroups": [out["producer_security_group"]],
                "assignPublicIp": "ENABLED",
            }
        },
        overrides={"containerOverrides": [{"name": out["producer_container"], "command": command}]},
    )
    if response["failures"]:
        sys.exit(f"run-task failed: {response['failures']}")
    print(f"Started {response['tasks'][0]['taskArn']}")
    print(f"Runs for {minutes} minutes: {' '.join(command)}")
    print("Follow it with: make logs")
    return 0


def stop(args: argparse.Namespace, out: dict) -> int:
    ecs = boto3.client("ecs", region_name=out["aws_region"])
    task_arns = ecs.list_tasks(
        cluster=out["ecs_cluster"], family=out["producer_task_family"], desiredStatus="RUNNING"
    )["taskArns"]
    if not task_arns:
        print("No producer task is running.")
    for arn in task_arns:
        ecs.stop_task(cluster=out["ecs_cluster"], task=arn, reason="make capture-stop")
        print(f"Stopping {arn} (it writes its summary before exiting)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    start = commands.add_parser("capture", help="start a capture task")
    start.add_argument("--hours", type=int, default=12)
    start.add_argument("--minutes", type=int, help="overrides --hours")
    start.add_argument("--key", choices=["event_id", "domain"], default="event_id")
    start.add_argument("extra", nargs="*", help="extra producer flags, after --")
    start.set_defaults(handler=capture)

    commands.add_parser("stop", help="stop running producer tasks").set_defaults(handler=stop)

    args = parser.parse_args()
    return args.handler(args, terraform_outputs())


if __name__ == "__main__":
    raise SystemExit(main())
