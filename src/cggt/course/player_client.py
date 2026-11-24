"""HTTP client for the Thinkific course player and Wistia media documents."""

import http.client
import json
import logging
import socket
import time
import urllib.error
import urllib.request


_LOGGER = logging.getLogger(__name__)

_CHUNK_BYTE_COUNT = 65536
_OPEN_TIMEOUT_SECONDS = 300
_TRANSIENT_OPEN_ATTEMPT_COUNT = 4
_TRANSIENT_OPEN_RETRY_SLEEP_SECONDS = 2.0


class PlayerHttpError(Exception):
    """A course-player or Wistia request returned a non-success status."""


class PlayerClient:
    """GET JSON and download files, optionally sending a session cookie."""

    def __init__(self, cookie_header):
        """Store the Cookie header value from a cookietruck session (https://github.com/dsoprea/cookietruck)."""

        self._cookie_header = cookie_header

    def get_json(self, url, send_cookie):
        """GET one JSON document. The cookie is sent only when ``send_cookie`` is true."""

        # Read the whole body, then decode JSON.
        raw_body = self._read_response_body(url, send_cookie)
        decoded_body = raw_body.decode("utf-8")

        return json.loads(decoded_body)

    def get_text(self, url, send_cookie):
        """GET a URL and return the body as text."""

        raw_body = self._read_response_body(url, send_cookie)

        return raw_body.decode("utf-8")

    def download_file(self, url, destination_filepath, on_chunk, send_cookie=False):
        """Stream a URL to ``destination_filepath``. ``on_chunk`` receives each byte count."""

        # Open first so the caller can record Content-Length before the body is copied.
        response = self._open(url, send_cookie)
        with response:
            content_length = response.headers.get("Content-Length")
            if content_length is not None:
                on_chunk(0, int(content_length))
            with open(destination_filepath, "wb") as destination_file:
                while True:
                    chunk = response.read(_CHUNK_BYTE_COUNT)
                    if len(chunk) == 0:
                        break
                    destination_file.write(chunk)
                    on_chunk(len(chunk), None)

    def _read_response_body(self, url, send_cookie):
        """Return the full response body for a JSON GET."""

        response = self._open(url, send_cookie)
        with response:
            body = response.read()

        return body

    def _open(self, url, send_cookie):
        """Open a GET request and raise ``PlayerHttpError`` on HTTP failure."""

        headers = {"Accept": "*/*", "User-Agent": "cggt"}
        if send_cookie:
            headers["Cookie"] = self._cookie_header
        request = urllib.request.Request(url, headers=headers, method="GET")

        return self._open_with_transient_retries(request, url)

    def _open_with_transient_retries(self, request, url):
        """Return a response, retrying when the server closes the connection before headers."""

        for attempt_index in range(_TRANSIENT_OPEN_ATTEMPT_COUNT):
            try:
                return urllib.request.urlopen(
                    request,
                    timeout=_OPEN_TIMEOUT_SECONDS)
            except urllib.error.HTTPError as error:
                error_body = error.read().decode("utf-8")
                message = "HTTP {status} for {url}: {body}".format(
                    status=error.code,
                    url=url,
                    body=error_body)
                _LOGGER.error(message)

                raise PlayerHttpError(message) from error
            except urllib.error.URLError as error:
                if not _is_transient_urlopen_error(error):
                    raise
                transient_error = error
            except (http.client.RemoteDisconnected,
                    ConnectionResetError,
                    BrokenPipeError,
                    TimeoutError,
                    socket.timeout) as error:
                transient_error = error

            if attempt_index + 1 >= _TRANSIENT_OPEN_ATTEMPT_COUNT:
                raise transient_error

            _LOGGER.warning(
                "transient HTTP error for {url} (attempt {attempt} of {attempt_count}): {error}".format(
                    url=url,
                    attempt=attempt_index + 1,
                    attempt_count=_TRANSIENT_OPEN_ATTEMPT_COUNT,
                    error=transient_error))
            time.sleep(_TRANSIENT_OPEN_RETRY_SLEEP_SECONDS)


def _is_transient_urlopen_error(error):
    """Return whether a URLError is a retryable transport failure."""

    reason = error.reason
    if reason is None:
        return False
    if isinstance(reason, (http.client.RemoteDisconnected,
                           ConnectionResetError,
                           BrokenPipeError,
                           TimeoutError,
                           socket.timeout)):

        return True

    return False
