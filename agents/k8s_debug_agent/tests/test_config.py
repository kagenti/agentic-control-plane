"""Tests for k8s_debug_agent Settings validation and defaults."""

import json
import sys
from pathlib import Path

import pytest

# Add the agent root to path so we can import the package
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_default_log_level():
    from k8s_debug_agent.config import Settings

    s = Settings()
    assert s.LOG_LEVEL in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def test_default_service_port():
    from k8s_debug_agent.config import Settings

    s = Settings()
    assert s.SERVICE_PORT == 8000


def test_default_max_plan_steps():
    from k8s_debug_agent.config import Settings

    s = Settings()
    assert s.MAX_PLAN_STEPS == 6


def test_extra_headers_valid_json(monkeypatch):
    """Valid JSON in EXTRA_HEADERS env var is parsed into a dict."""
    headers = {"X-Custom": "value", "X-Other": "123"}
    monkeypatch.setenv("EXTRA_HEADERS", json.dumps(headers))

    from k8s_debug_agent.config import Settings

    s = Settings()
    assert s.EXTRA_HEADERS == headers


def test_extra_headers_invalid_json_raises(monkeypatch):
    """Invalid JSON in EXTRA_HEADERS env var raises ValueError.

    The import is placed inside pytest.raises to handle both the case where
    the module is not yet cached (import triggers module-level Settings() and
    raises) and when it is cached (reload re-runs module-level Settings()).
    """
    monkeypatch.setenv("EXTRA_HEADERS", "not-valid-json")
    with pytest.raises(ValueError, match="EXTRA_HEADERS must be a valid JSON string"):
        from importlib import reload

        import k8s_debug_agent.config as cfg_module

        reload(cfg_module)
        cfg_module.Settings()


def test_extra_headers_empty_by_default():
    """Without EXTRA_HEADERS env var set, defaults to empty dict."""
    import os
    from unittest.mock import patch

    from k8s_debug_agent.config import Settings

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("EXTRA_HEADERS", None)
        s = Settings()
        assert s.EXTRA_HEADERS == {}
