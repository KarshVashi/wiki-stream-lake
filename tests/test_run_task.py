from run_task import producer_command


def test_producer_command_for_a_capture():
    assert producer_command("capture", 180, "domain", "edits", "lake", []) == [
        "capture", "--partition-key", "domain", "--duration-minutes", "180",
        "--summary-bucket", "lake", "--stream-name", "edits",
    ]  # fmt: skip


def test_producer_command_dry_run_without_stream():
    command = producer_command("capture", 2, "event_id", None, "lake", ["--dry-run"])
    assert "--stream-name" not in command
    assert command[-1] == "--dry-run"
