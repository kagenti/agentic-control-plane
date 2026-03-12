"""Tests for authentication context management and K8s client creation."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib import auth


def test_create_k8s_client_no_token_token_auth_only_raises():
    """Without a token, token_auth_only=True must raise ValueError."""
    auth.set_auth_context(None)
    with pytest.raises(ValueError, match="no JWT token supplied"):
        auth.create_k8s_client(token_auth_only=True)


@patch("lib.auth.create_k8s_client_from_token")
def test_create_k8s_client_uses_token_when_set(mock_from_token):
    """When a token is set in context, it is used to build the client."""
    mock_from_token.return_value = MagicMock()
    auth.set_auth_context("my-jwt-token")

    client = auth.create_k8s_client()

    mock_from_token.assert_called_once_with("my-jwt-token")
    auth.set_auth_context(None)  # cleanup


@patch("lib.auth.create_k8s_client_from_kubeconfig")
def test_create_k8s_client_falls_back_to_kubeconfig(mock_from_kube):
    """Without a token and token_auth_only=False, falls back to kubeconfig."""
    mock_from_kube.return_value = MagicMock()
    auth.set_auth_context(None)

    client = auth.create_k8s_client(token_auth_only=False)

    mock_from_kube.assert_called_once()


def test_set_auth_context_is_scoped_per_context():
    """set_auth_context stores the token for the current execution context."""
    auth.set_auth_context("token-abc")
    assert auth._current_token.get() == "token-abc"
    auth.set_auth_context(None)
    assert auth._current_token.get() is None
