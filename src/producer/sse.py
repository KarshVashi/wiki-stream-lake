"""A small Server-Sent Events client for Wikimedia EventStreams."""

import json
import logging
import time
from collections.abc import Iterable, Iterator

import requests

log = logging.getLogger(__name__)

STREAM_URL = "https://stream.wikimedia.org/v2/stream/recentchange"
MAX_BACKOFF_SECONDS = 60


def parse_sse(lines: Iterable[str]) -> Iterator[tuple[str | None, str]]:
    """Turn raw SSE lines into (event_id, data) pairs.

    An event is a group of lines ended by a blank line. "data:" lines are joined,
    "id:" sets the event ID, and lines starting with ":" are comments.
    """
    event_id, data = None, []
    for line in lines:
        if line == "":
            if data:
                yield event_id, "\n".join(data)
            data = []
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        value = value.removeprefix(" ")
        if field == "data":
            data.append(value)
        elif field == "id":
            event_id = value


def stream_events(
    user_agent: str,
    url: str = STREAM_URL,
    session=None,
    sleep=time.sleep,
    keep_going=lambda: True,
):
    """Yield events from the stream until keep_going() returns False.

    On any connection problem, wait and reconnect, sending the last event ID seen so
    the server resumes where it left off instead of skipping or repeating events.
    keep_going is checked before every reconnect, so a run still ends on time when
    the server is down and no events arrive.
    """
    session = session or requests.Session()
    last_event_id = None
    backoff = 1
    while keep_going():
        headers = {"User-Agent": user_agent, "Accept": "text/event-stream"}
        if last_event_id:
            headers["Last-Event-ID"] = last_event_id
        try:
            with session.get(url, headers=headers, stream=True, timeout=(10, 30)) as response:
                response.raise_for_status()
                response.encoding = "utf-8"
                for event_id, data in parse_sse(response.iter_lines(decode_unicode=True)):
                    if event_id:
                        last_event_id = event_id
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        log.warning("skipping event that is not valid JSON")
                        continue
                    backoff = 1
                    yield event
            log.warning("stream closed by server, reconnecting in %ss", backoff)
        except requests.RequestException as exc:
            log.warning("stream error (%s), reconnecting in %ss", exc, backoff)
        if not keep_going():
            break
        sleep(backoff)
        backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
