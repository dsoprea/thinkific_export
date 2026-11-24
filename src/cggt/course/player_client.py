"""HTTP client for the Thinkific course player and Wistia media documents."""

import json
import logging
import urllib.error
import urllib.request


_LOGGER = logging.getLogger(__name__)

_CHUNK_BYTE_COUNT = 65536
# A stalled connection with no timeout would hold the export open forever, so every request gives up.
_REQUEST_TIMEOUT_SECONDS = 120


class PlayerHttpError(Exception):
    """A course-player or Wistia request failed."""


class IncompleteDownloadError(PlayerHttpError):
    """A download ended before the Content-Length the response declared."""


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
        """Stream a URL to ``destination_filepath``. ``on_chunk`` receives each byte count.

        Raises:
            IncompleteDownloadError: The body ended before the declared Content-Length arrived.
        """

        # Open first so the caller can record Content-Length before the body is copied.
        response = self._open(url, send_cookie)
        with response:
            content_length = response.headers.get("Content-Length")
            declared_byte_count = None
            if content_length is not None:
                declared_byte_count = int(content_length)
                on_chunk(0, declared_byte_count)
            received_byte_count = 0
            with open(destination_filepath, "wb") as destination_file:
                while True:
                    chunk = response.read(_CHUNK_BYTE_COUNT)
                    if len(chunk) == 0:
                        break
                    destination_file.write(chunk)
                    received_byte_count = received_byte_count + len(chunk)
                    on_chunk(len(chunk), None)
            # A body cut short is not something the read loop reports: it ends, and the short file
            # then counts as a finished content directory that every later run skips.
            if declared_byte_count is not None and received_byte_count != declared_byte_count:
                message = "{url} gave {received} of {declared} bytes".format(
                    url=url,
                    received=received_byte_count,
                    declared=declared_byte_count)
                _LOGGER.error(message)

                raise IncompleteDownloadError(message)

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
        try:
            response = urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS)
        except urllib.error.HTTPError as error:
            error_body = error.read().decode("utf-8")
            message = "HTTP {status} for {url}: {body}".format(
                status=error.code,
                url=url,
                body=error_body)
            _LOGGER.error(message)

            raise PlayerHttpError(message) from error
        except urllib.error.URLError as error:
            # A refused connection, a stalled read, or a name that does not resolve: no status code.
            message = "{url}: {reason}".format(url=url, reason=error.reason)
            _LOGGER.error(message)

            raise PlayerHttpError(message) from error

        return response
