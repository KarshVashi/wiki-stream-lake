import base64
import json

import pytest

from transform_lambda.handler import handler, is_anonymous, mask_text


def edit_event(**overrides):
    event = {
        "meta": {"id": "e1", "dt": "2026-10-21T10:00:00Z", "domain": "en.wikipedia.org"},
        "type": "edit",
        "wiki": "enwiki",
        "namespace": 0,
        "title": "Data engineering",
        "user": "ExampleUser",
        "bot": False,
        "minor": True,
        "comment": "fix typo",
        "length": {"old": 100, "new": 120},
        "revision": {"old": 1, "new": 2},
        "parsedcomment": "<b>dropped</b>",
    }
    event.update(overrides)
    return event


def run(*payloads):
    records = [
        {"recordId": str(i), "data": base64.b64encode(p).decode()} for i, p in enumerate(payloads)
    ]
    return handler({"records": records}, None)["records"]


def run_event(event):
    return run(json.dumps(event).encode())[0]


def decode(result):
    raw = base64.b64decode(result["data"]).decode()
    assert raw.endswith("\n")
    return json.loads(raw)


def test_normal_edit_is_flattened():
    result = run_event(edit_event())
    assert result["result"] == "Ok"
    assert decode(result) == {
        "event_id": "e1",
        "event_time": "2026-10-21T10:00:00Z",
        "domain": "en.wikipedia.org",
        "wiki": "enwiki",
        "type": "edit",
        "namespace": 0,
        "title": "Data engineering",
        "user_name": "ExampleUser",
        "is_anonymous": False,
        "is_bot": False,
        "is_minor": True,
        "comment": "fix typo",
        "length_old": 100,
        "length_new": 120,
        "revision_old": 1,
        "revision_new": 2,
    }


def test_canary_is_dropped():
    event = edit_event(meta={"id": "c", "dt": "2026-10-21T10:00:00Z", "domain": "canary"})
    assert run_event(event)["result"] == "Dropped"


@pytest.mark.parametrize("event_type", ["categorize", "142", None])
def test_other_types_are_dropped(event_type):
    assert run_event(edit_event(type=event_type))["result"] == "Dropped"


@pytest.mark.parametrize("user", ["~2026-54871-77", "203.0.113.7", "2001:db8::1"])
def test_anonymous_users_are_masked(user):
    flat = decode(run_event(edit_event(user=user)))
    assert flat["user_name"] == "anonymous"
    assert flat["is_anonymous"] is True


def test_named_user_with_a_tilde_is_not_masked():
    assert not is_anonymous("~Tilde fan")
    assert not is_anonymous(None)


def test_ips_and_temporary_accounts_are_masked_in_titles_and_comments():
    flat = decode(
        run_event(
            edit_event(
                type="log",
                title="User:203.0.113.7",
                comment="Reverted edits by ~2026-54871-77 and 2001:db8:0:0:0:0:0:1",
            )
        )
    )
    assert flat["title"] == "User:anonymous"
    assert flat["comment"] == "Reverted edits by anonymous and anonymous"


def test_mask_text_leaves_ordinary_text_alone():
    text = "Version 3.12 released at 12:30:45, see page 10:30"
    assert mask_text(text) == text
    assert mask_text("blocked 2001:db8::1 today") == "blocked anonymous today"
    assert mask_text(None) is None


def test_missing_optional_fields_become_null():
    event = {
        "meta": {"id": "e2", "dt": "2026-10-21T10:00:00Z", "domain": "commons.wikimedia.org"},
        "type": "log",
        "title": "File:Example.jpg",
        "user": "Uploader",
    }
    flat = decode(run_event(event))
    assert flat["is_minor"] is None
    assert flat["length_old"] is None
    assert flat["revision_new"] is None


@pytest.mark.parametrize(
    "payload",
    [b"not json", b"[1, 2, 3]", b'{"type": "edit"}', b'{"meta": "x", "type": "edit"}', b"\xff"],
)
def test_malformed_input_fails_without_raising(payload):
    assert run(payload)[0]["result"] == "ProcessingFailed"


def test_every_record_comes_back_with_its_id():
    results = run(json.dumps(edit_event()).encode(), b"bad")
    assert [r["recordId"] for r in results] == ["0", "1"]
    assert [r["result"] for r in results] == ["Ok", "ProcessingFailed"]
