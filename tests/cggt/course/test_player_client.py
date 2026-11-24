"""Course player client downloads, timeouts, and transport errors."""

import io
import urllib.error

import pytest

import cggt.course.player_client


class _FakeResponse:
    """Context manager that yields a fixed body and an optional Content-Length."""

    def __init__(self, body, declared_byte_count=None):
        """Store the body and the length the server declares in its header."""

        self._body = io.BytesIO(body)
        self.headers = {}
        if declared_byte_count is not None:
            self.headers["Content-Length"] = str(declared_byte_count)

    def read(self, amount=None):
        """Return up to ``amount`` bytes of the body."""

        return self._body.read(amount)

    def __enter__(self):
        """Enter the context as this response."""

        return self

    def __exit__(self, exc_type, exc, traceback):
        """Do not suppress exceptions."""

        return False


class _Progress:
    """Records every progress report the client makes."""

    def __init__(self):
        """Start with no reports."""

        self.reports = []

    def __call__(self, chunk_byte_count, content_length):
        """Record one report."""

        self.reports.append((chunk_byte_count, content_length))


def _patch_open(monkeypatch, response):
    """Make every open return ``response``."""

    monkeypatch.setattr(
        cggt.course.player_client.PlayerClient,
        "_open",
        lambda self, url, send_cookie: response)


def test_download_file_writes_the_body_and_reports_its_length(tmp_path, monkeypatch):
    """A whole body lands on disk, and the declared length opens the progress total."""

    _patch_open(monkeypatch, _FakeResponse(b"0123456789", 10))
    destination_filepath = str(tmp_path / "video.mp4")
    progress = _Progress()
    client = cggt.course.player_client.PlayerClient("cookie")
    client.download_file("https://cdn.example/video.mp4", destination_filepath, progress, False)

    assert (tmp_path / "video.mp4").read_bytes() == b"0123456789"
    assert progress.reports == [(0, 10), (10, None)]


def test_download_file_refuses_a_body_short_of_its_content_length(tmp_path, monkeypatch):
    """A body cut short is an error, so a truncated file is never taken for a finished one."""

    _patch_open(monkeypatch, _FakeResponse(b"0123456789", 4096))
    destination_filepath = str(tmp_path / "video.mp4")
    client = cggt.course.player_client.PlayerClient("cookie")

    with pytest.raises(cggt.course.player_client.IncompleteDownloadError, match="10 of 4096 bytes"):
        client.download_file("https://cdn.example/video.mp4", destination_filepath, _Progress(), False)


def test_incomplete_download_error_is_a_player_http_error():
    """A caller that already handles a failed request handles a short body too."""

    assert issubclass(
        cggt.course.player_client.IncompleteDownloadError,
        cggt.course.player_client.PlayerHttpError)


def test_download_file_accepts_a_body_with_no_content_length(tmp_path, monkeypatch):
    """Without a declared length there is nothing to compare, so the body is taken as it comes."""

    _patch_open(monkeypatch, _FakeResponse(b"0123456789"))
    destination_filepath = str(tmp_path / "playlist.m3u8")
    progress = _Progress()
    client = cggt.course.player_client.PlayerClient("cookie")
    client.download_file("https://cdn.example/playlist.m3u8", destination_filepath, progress, False)

    assert (tmp_path / "playlist.m3u8").read_bytes() == b"0123456789"
    assert progress.reports == [(10, None)]


def test_get_json_sends_a_timeout(monkeypatch):
    """Every request gives up, so a stalled connection cannot hold the export open."""

    opened_urls = []

    def fake_urlopen(request, timeout=None):
        opened_urls.append((request.full_url, timeout))

        return _FakeResponse(b'{"id": 1}', 8)

    monkeypatch.setattr(cggt.course.player_client.urllib.request, "urlopen", fake_urlopen)
    client = cggt.course.player_client.PlayerClient("cookie")
    document = client.get_json("https://example.thinkific.com/api/x", False)

    assert document == {"id": 1}
    assert opened_urls == [
        ("https://example.thinkific.com/api/x", cggt.course.player_client._REQUEST_TIMEOUT_SECONDS),
    ]


def test_get_json_wraps_a_transport_error(monkeypatch):
    """A name that does not resolve becomes PlayerHttpError rather than a traceback."""

    def fake_urlopen(request, timeout=None):
        raise urllib.error.URLError("Name or service not known")

    monkeypatch.setattr(cggt.course.player_client.urllib.request, "urlopen", fake_urlopen)
    client = cggt.course.player_client.PlayerClient("cookie")

    with pytest.raises(cggt.course.player_client.PlayerHttpError, match="Name or service not known"):
        client.get_json("https://example.thinkific.com/api/x", False)


def test_open_sends_the_cookie_only_when_asked(monkeypatch):
    """The Cookie header is on a player request and off a Wistia request."""

    sent_headers = []

    def fake_urlopen(request, timeout=None):
        sent_headers.append(dict(request.headers))

        return _FakeResponse(b"body", 4)

    monkeypatch.setattr(cggt.course.player_client.urllib.request, "urlopen", fake_urlopen)
    client = cggt.course.player_client.PlayerClient("session=abc")
    client.get_text("https://example.thinkific.com/play", True)
    client.get_text("https://fast.wistia.com/embed/medias/abc.json", False)

    assert sent_headers[0]["Cookie"] == "session=abc"
    assert "Cookie" not in sent_headers[1]
