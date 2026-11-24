"""Unit tests for the Thinkific course player HTTP client."""

import http.client
import io
import urllib.error

import pytest

import cggt.course.player_client


class _RecordingOpener:
    """Records urlopen calls and returns a canned response or raises."""

    def __init__(self, outcomes):
        """``outcomes`` is a list of return values or exceptions for each call."""

        self._outcomes = list(outcomes)
        self.call_count = 0

    def urlopen(self, request, timeout):
        """Return the next outcome."""

        index = self.call_count
        self.call_count = self.call_count + 1
        if index >= len(self._outcomes):
            message = "no more outcomes"

            raise RuntimeError(message)

        outcome = self._outcomes[index]
        if isinstance(outcome, BaseException):
            raise outcome

        return outcome


def _build_response(body_text, status=200):
    """Return a minimal addinfourl response wrapping ``body_text``."""

    payload = body_text.encode("utf-8")
    response = io.BytesIO(payload)

    return urllib.response.addinfourl(
        response,
        {"Content-Length": str(len(payload))},
        "https://example.test/resource",
        status)


def test_open_retries_remote_disconnected(monkeypatch):
    """Transient disconnect while opening the response is retried."""

    opener = _RecordingOpener([
        http.client.RemoteDisconnected("Remote end closed connection without response"),
        _build_response("ok"),
    ])
    monkeypatch.setattr(urllib.request, "urlopen", opener.urlopen)
    monkeypatch.setattr(cggt.course.player_client.time, "sleep", lambda _seconds: None)
    client = cggt.course.player_client.PlayerClient("session=abc")

    body = client._read_response_body("https://example.test/resource", False)

    assert body == b"ok"
    assert opener.call_count == 2


def test_open_maps_http_error_to_player_http_error(monkeypatch):
    """HTTP failure responses become ``PlayerHttpError`` without retry."""

    error_body = b"denied"
    http_error = urllib.error.HTTPError(
        "https://example.test/resource",
        403,
        "Forbidden",
        {},
        io.BytesIO(error_body))
    opener = _RecordingOpener([http_error])
    monkeypatch.setattr(urllib.request, "urlopen", opener.urlopen)
    client = cggt.course.player_client.PlayerClient("session=abc")

    with pytest.raises(cggt.course.player_client.PlayerHttpError) as error_info:
        client._read_response_body("https://example.test/resource", False)

    assert "HTTP 403" in str(error_info.value)
    assert opener.call_count == 1