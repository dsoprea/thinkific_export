"""Thinkific credential environment variables."""

import os


THINKIFIC_API_ACCESS_TOKEN_ENVIRONMENT_NAME = "THINKIFIC_API_ACCESS_TOKEN"
THINKIFIC_SSO_SIGNING_SECRET_ENVIRONMENT_NAME = "THINKIFIC_SSO_SIGNING_SECRET"
THINKIFIC_API_BASE_URL = "https://api.thinkific.com/api/public/v1"
THINKIFIC_PAGE_LIMIT = 250


def load_thinkific_credentials():
    """Return the API access token and SSO signing secret from the process environment."""

    # Both credentials must be present even when a command only calls the Admin API.
    access_token = os.environ[THINKIFIC_API_ACCESS_TOKEN_ENVIRONMENT_NAME]
    signing_secret = os.environ[THINKIFIC_SSO_SIGNING_SECRET_ENVIRONMENT_NAME]
    if access_token == "" or signing_secret == "":
        message = "THINKIFIC_API_ACCESS_TOKEN and THINKIFIC_SSO_SIGNING_SECRET must be non-empty"

        raise ValueError(message)

    return access_token, signing_secret
