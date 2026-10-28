import requests

from producer.sse import parse_sse, stream_events


def test_parse_sse_groups_lines_into_events():
    lines = [
        ": a comment",
        "event: message",
        'id: [{"offset":1}]',
        'data: {"a": 1}',
        "",
        "",  # a second blank line does not produce an empty event
        'id: [{"offset":2}]',
        "data: line one",
        "data: line two",
        "",
    ]
    assert list(parse_sse(lines)) == [
        ('[{"offset":1}]', '{"a": 1}'),
        ('[{"offset":2}]', "line one\nline two"),
    ]


class FakeResponse:
    def __init__(self, lines=(), error=None):
        self.lines, self.error = lines, error

    def __enter__(self):
        if self.error:
            raise self.error
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        pass

    def iter_lines(self, decode_unicode=False):
        yield from self.lines


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.headers_seen = []

    def get(self, url, headers, stream, timeout):
        self.headers_seen.append(headers)
        return self.responses.pop(0)


def test_stream_events_reconnects_and_resumes_from_last_event_id():
    session = FakeSession(
        [
            FakeResponse(["id: first", 'data: {"n": 1}', ""]),
            FakeResponse(error=requests.ConnectionError("dropped")),
            FakeResponse(["id: second", 'data: {"n": 2}', ""]),
        ]
    )
    sleeps = []
    events = stream_events("test-agent", session=session, sleep=sleeps.append)

    assert [next(events), next(events)] == [{"n": 1}, {"n": 2}]
    assert "Last-Event-ID" not in session.headers_seen[0]
    assert session.headers_seen[1]["Last-Event-ID"] == "first"
    assert session.headers_seen[2]["Last-Event-ID"] == "first"
    assert all(h["User-Agent"] == "test-agent" for h in session.headers_seen)
    assert sleeps == [1, 2]  # backoff doubles while reconnects keep failing


def test_stream_events_skips_invalid_json():
    session = FakeSession([FakeResponse(["data: not json", "", 'data: {"ok": true}', ""])])
    assert next(stream_events("ua", session=session, sleep=lambda s: None)) == {"ok": True}


def test_stream_events_stops_when_told_even_if_the_server_is_down():
    session = FakeSession([FakeResponse(error=requests.ConnectionError("503"))] * 10)
    checks = iter([True, True, True, False])  # time runs out on the fourth check
    sleeps = []
    events = stream_events(
        "ua", session=session, sleep=sleeps.append, keep_going=lambda: next(checks)
    )
    assert list(events) == []  # ends instead of retrying forever
    assert len(session.headers_seen) == 2
    assert sleeps == [1]
