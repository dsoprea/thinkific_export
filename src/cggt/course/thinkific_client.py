"""HTTP client for the Thinkific Admin API."""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

import cggt.config.thinkific


_LOGGER = logging.getLogger(__name__)


class ThinkificApiError(Exception):
    """Thinkific returned a non-success HTTP status."""


class ThinkificClient:
    """Authenticated GET client for ``/api/public/v1``."""

    def __init__(self, access_token):
        """Store the bearer token used on every request."""

        self._access_token = access_token

    def get_json(self, resource_path, query_items):
        """GET one JSON object. ``query_items`` is a list of ``(name, value)`` pairs."""

        # Build the URL, then read the body or raise with the error payload.
        query_string = urllib.parse.urlencode(query_items)
        url = cggt.config.thinkific.THINKIFIC_API_BASE_URL + resource_path
        if query_string != "":
            url = url + "?" + query_string
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": "Bearer " + self._access_token,
                "Accept": "application/json",
                "User-Agent": "cggt",
            },
            method="GET")
        try:
            response = urllib.request.urlopen(request)
        except urllib.error.HTTPError as error:
            error_body = error.read().decode("utf-8")
            message = "Thinkific API HTTP {status} for {url}: {body}".format(
                status=error.code,
                url=url,
                body=error_body)
            _LOGGER.error(message)

            raise ThinkificApiError(message) from error

        with response:
            raw_body = response.read()
        decoded_body = raw_body.decode("utf-8")

        return json.loads(decoded_body)

    def list_collection(self, resource_path, query_items):
        """Follow ``meta.pagination.next_page`` until the collection is exhausted."""

        # Page through the collection. Thinkific defaults to 25 rows and caps a page at 250.
        items = []
        page_number = 1
        while True:
            page_query_items = list(query_items)
            page_query_items.append(("page", page_number))
            page_query_items.append(("limit", cggt.config.thinkific.THINKIFIC_PAGE_LIMIT))
            payload = self.get_json(resource_path, page_query_items)
            page_items = payload["items"]
            items.extend(page_items)
            next_page = payload["meta"]["pagination"]["next_page"]
            if next_page is None:
                break
            page_number = next_page

        return items
