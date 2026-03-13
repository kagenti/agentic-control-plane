"""Tests for k8s_debug_agent Settings validation and defaults."""

import json
import os

import pytest

from k8s_debug_agent.config import Settings


def test_default_log_level():
    s = Settings()
    assert s.LOG_LEVEL in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def test_default_service_port():
    s = Settings()
    assert s.SERVICE_PORT == 8000


def test_default_max_plan_steps():
    s = Settings()
    assert s.MAX_PLAN_STEPS == 6


def test_extra_headers_valid_json(monkeypatch):
    """Valid JSON in EXTRA_HEADERS env var is parsed into a dict."""
    headers = {"X-Custom": "value", "X-Other": "123"}
    monkeypatch.setenv("EXTRA_HEADERS", json.dumps(headers))

    s = Settings()
    assert s.EXTRA_HEADERS == headers


def test_extra_headers_invalid_json_raises(monkeypatch):
    """Invalid JSON in EXTRA_HEADERS env var raises an error."""
    monkeypatch.setenv("EXTRA_HEADERS", "not-valid-json")
    with pytest.raises(Exception):
        Settings()


def test_extra_headers_empty_by_default():
    """Without EXTRA_HEADERS env var set, defaults to empty dict."""
    from unittest.mock import patch

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("EXTRA_HEADERS", None)
        s = Settings()
        assert s.EXTRA_HEADERS == {}
