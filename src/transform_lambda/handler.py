"""Firehose transformation Lambda: flatten Wikimedia recentchange events, drop noise,
and mask personal data before anything is written to S3.

Firehose calls handler() with a batch of base64-encoded records. For every record it
expects back the same recordId, a result (Ok, Dropped or ProcessingFailed) and
base64-encoded data. Ok records are written to raw/edits/, ProcessingFailed records
to errors/, and Dropped records are discarded.
"""

import base64
import ipaddress
import json
import re

KEEP_TYPES = {"edit", "new", "log"}
ANONYMOUS = "anonymous"

# Logged-out editors get temporary accounts named like ~2026-54871-77.
TEMP_ACCOUNT = re.compile(r"^~\d{4}-\d+(-\d+)?$")

# Free text (titles, comments) can also mention IPs or temporary accounts, for
# example block logs on pages such as "User:203.0.113.7".
PERSONAL_IN_TEXT = re.compile(
    r"~\d{4}-\d+(?:-\d+)?"  # temporary account
    r"|\b(?:\d{1,3}\.){3}\d{1,3}\b"  # IPv4
    r"|\b(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}\b"  # IPv6, all 8 groups
    r"|\b(?:[0-9A-Fa-f]{1,4}:)+:(?:[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4})*)?"  # IPv6 with ::
)


def is_anonymous(user: str | None) -> bool:
    if not user:
        return False
    if TEMP_ACCOUNT.match(user):
        return True
    try:
        ipaddress.ip_address(user)
        return True
    except ValueError:
        return False


def mask_text(text: str | None) -> str | None:
    return PERSONAL_IN_TEXT.sub(ANONYMOUS, text) if text else text


def flatten(event: dict) -> dict | None:
    """Return the flat event, or None if it should be dropped."""
    meta = event["meta"]
    if meta.get("domain") == "canary" or event.get("type") not in KEEP_TYPES:
        return None

    user = event.get("user")
    anonymous = is_anonymous(user)
    length = event.get("length") or {}
    revision = event.get("revision") or {}
    return {
        "event_id": meta["id"],
        "event_time": meta["dt"],
        "domain": meta["domain"],
        "wiki": event.get("wiki"),
        "type": event["type"],
        "namespace": event.get("namespace"),
        "title": mask_text(event.get("title")),
        "user_name": ANONYMOUS if anonymous else user,
        "is_anonymous": anonymous,
        "is_bot": event.get("bot"),
        "is_minor": event.get("minor"),  # absent on log events, stays null
        "comment": mask_text(event.get("comment")),
        "length_old": length.get("old"),
        "length_new": length.get("new"),
        "revision_old": revision.get("old"),
        "revision_new": revision.get("new"),
    }


def transform(record: dict) -> dict:
    try:
        event = json.loads(base64.b64decode(record["data"]))
        flat = flatten(event)
    except (ValueError, KeyError, TypeError, AttributeError):
        return {
            "recordId": record["recordId"],
            "result": "ProcessingFailed",
            "data": record["data"],
        }

    if flat is None:
        return {"recordId": record["recordId"], "result": "Dropped", "data": record["data"]}

    line = json.dumps(flat, ensure_ascii=False, separators=(",", ":")) + "\n"
    return {
        "recordId": record["recordId"],
        "result": "Ok",
        "data": base64.b64encode(line.encode()).decode(),
    }


def handler(event, context):
    return {"records": [transform(record) for record in event["records"]]}
