"""Tests for k8s_debug_agent Settings validation and defaults."""

import json
import sys
from pathlib import Path

import pytest

# Add the agent root to path so we can import the package
sys.path.insert(0, str(Path(__file__).parent.parent))


def _make_settings(env: dict):
    """Create a fresh Settings instance with specific env vars patched."""
    import os
    from unittest.mock import patch

    # Patch os.getenv so Field defaults pick up our values,
    # and also patch env vars so pydantic-settings reads them.
    with patch.dict(os.environ, env, clear=False):
        # Re-import to get a fresh Settings instance with patched env
        from importlib import import_module, reload
        import k8s_debug_agent.config as cfg_module
        reload(cfg_module)
        return cfg_module.Settings()


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
    import os
    headers = {"X-Custom": "value", "X-Other": "123"}
    monkeypatch.setenv("EXTRA_HEADERS", json.dumps(headers))

    from k8s_debug_agent.config import Settings
    s = Settings()
    assert s.EXTRA_HEADERS == headers


def test_extra_headers_invalid_json_raises(monkeypatch):
    """Invalid JSON in EXTRA_HEADERS env var raises ValueError."""
    monkeypatch.setenv("EXTRA_HEADERS", "not-valid-json")

    from k8s_debug_agent.config import Settings
    with pytest.raises(ValueError, match="EXTRA_HEADERS must be a valid JSON string"):
        Settings()


def test_extra_headers_empty_by_default():
    """Without EXTRA_HEADERS env var set, defaults to empty dict."""
    import os
    from unittest.mock import patch
    from k8s_debug_agent.config import Settings

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("EXTRA_HEADERS", None)
        s = Settings()
        assert s.EXTRA_HEADERS == {}
