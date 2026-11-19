"""Thinkific HTTP client pagination and errors."""

import io
import json
import urllib.error

import pytest

import cggt.course.thinkific_client


class _FakeResponse:
    """Context manager that returns a fixed body."""

    def __init__(self, body):
        """Store the response bytes."""

        self._body = body

    def read(self):
        """Return the body bytes."""

        return self._body

    def __enter__(self):
        """Enter the context as this response."""

        return self

    def __exit__(self, exc_type, exc, traceback):
        """Do not suppress exceptions."""

        return False


def test_list_collection_follows_next_page(monkeypatch):
    """Pages are concatenated until next_page is null."""

    pages = {
        1: {
            "items": [{"id": 1}],
            "meta": {"pagination": {"next_page": 2}},
        },
        2: {
            "items": [{"id": 2}],
            "meta": {"pagination": {"next_page": None}},
        },
    }
    requested_pages = []

    def fake_urlopen(request):
        query = request.full_url.split("page=", 1)[1]
        page_number = int(query.split("&", 1)[0])
        requested_pages.append(page_number)
        encoded = json.dumps(pages[page_number]).encode("utf-8")

        return _FakeResponse(encoded)

    monkeypatch.setattr(cggt.course.thinkific_client.urllib.request, "urlopen", fake_urlopen)
    client = cggt.course.thinkific_client.ThinkificClient("token-value")
    items = client.list_collection("/courses", [])

    assert requested_pages == [1, 2]
    assert items == [{"id": 1}, {"id": 2}]


def test_get_json_raises_on_http_error(monkeypatch):
    """HTTP failures become ThinkificApiError and include the status."""

    def fake_urlopen(request):
        raise urllib.error.HTTPError(
            request.full_url,
            401,
            "Unauthorized",
            hdrs=None,
            fp=io.BytesIO(b'{"error":"Authentication Error"}'))

    monkeypatch.setattr(cggt.course.thinkific_client.urllib.request, "urlopen", fake_urlopen)
    client = cggt.course.thinkific_client.ThinkificClient("token-value")

    with pytest.raises(cggt.course.thinkific_client.ThinkificApiError, match="401"):
        client.get_json("/courses/1", [])
