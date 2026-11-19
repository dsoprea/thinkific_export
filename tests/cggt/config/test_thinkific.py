"""Thinkific credential loading."""

import pytest

import cggt.config.thinkific


def test_load_thinkific_credentials_returns_both_values(monkeypatch):
    """Non-empty environment values are returned in token, secret order."""

    monkeypatch.setenv("THINKIFIC_API_ACCESS_TOKEN", "token-value")
    monkeypatch.setenv("THINKIFIC_SSO_SIGNING_SECRET", "secret-value")
    access_token, signing_secret = cggt.config.thinkific.load_thinkific_credentials()

    assert access_token == "token-value"
    assert signing_secret == "secret-value"


def test_load_thinkific_credentials_rejects_empty_token(monkeypatch):
    """An empty access token is a configuration error."""

    monkeypatch.setenv("THINKIFIC_API_ACCESS_TOKEN", "")
    monkeypatch.setenv("THINKIFIC_SSO_SIGNING_SECRET", "secret-value")

    with pytest.raises(ValueError):
        cggt.config.thinkific.load_thinkific_credentials()


def test_load_thinkific_credentials_requires_environment(monkeypatch):
    """Missing variables surface as KeyError from the environment lookup."""

    monkeypatch.delenv("THINKIFIC_API_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("THINKIFIC_SSO_SIGNING_SECRET", raising=False)

    with pytest.raises(KeyError):
        cggt.config.thinkific.load_thinkific_credentials()
