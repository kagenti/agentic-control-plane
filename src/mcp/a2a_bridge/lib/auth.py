"""
Authentication utilities for MCP server.

Authorino injects these headers after validating the JWT:
- X-Auth-User: Username from JWT (e.g., "mofoster")
- X-Auth-Email: Email from JWT
- X-Auth-Groups: Groups from JWT (JSON array)
- X-Auth-Token: Original JWT token

The MCP server reads these headers and uses them to:
1. Identify the user
2. Create Kubernetes API clients with the user's JWT
3. Enforce RBAC (Kubernetes validates the JWT)
"""

import os
import contextvars
from typing import Optional
from kubernetes import client
from kubernetes.client import ApiClient, Configuration


# Context variables to store auth info for current request
_current_user = contextvars.ContextVar('current_user', default=None)
_current_token = contextvars.ContextVar('current_token', default=None)
_current_email = contextvars.ContextVar('current_email', default=None)
_current_groups = contextvars.ContextVar('current_groups', default=None)


def set_auth_context(user: Optional[str], token: Optional[str],
                     email: Optional[str] = None, groups: Optional[str] = None) -> None:
    """
    Store authentication info for the current request.

    Args:
        user: Username from X-Auth-User header
        token: JWT from X-Auth-Token header
        email: Email from X-Auth-Email header
        groups: Groups JSON from X-Auth-Groups header
    """
    _current_user.set(user)
    _current_token.set(token)
    _current_email.set(email)
    _current_groups.set(groups)


def get_current_user() -> Optional[str]:
    """Get the authenticated user for the current request."""
    return _current_user.get()


def get_current_token() -> Optional[str]:
    """Get the JWT token for the current request."""
    return _current_token.get()


def create_k8s_client_from_token(jwt_token: str) -> ApiClient:
    """
    Create a Kubernetes API client using a user's JWT token.

    The JWT has been validated by Authorino/OpenShift OAuth. We pass it
    directly to the Kubernetes API server which will:
    1. Validate it again (defense in depth)
    2. Extract the user identity
    3. Enforce RBAC for that user

    Args:
        jwt_token: JWT token from X-Auth-Token header

    Returns:
        Kubernetes API client configured with the user's token
    """
    config = Configuration()

    # Determine API server URL
    if os.path.exists('/var/run/secrets/kubernetes.io/serviceaccount/token'):
        # Running in-cluster
        config.host = "https://kubernetes.default.svc"
        ca_cert = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
        if os.path.exists(ca_cert):
            config.ssl_ca_cert = ca_cert
    else:
        # Local development - get from kubeconfig
        from kubernetes import config as k8s_config
        try:
            k8s_config.load_kube_config()
            config.host = k8s_config.Configuration().host
            config.ssl_ca_cert = k8s_config.Configuration().ssl_ca_cert
        except Exception as e:
            raise Exception(f"Failed to load kubeconfig: {e}")

    # Use the user's JWT as bearer token
    config.api_key = {"authorization": f"Bearer {jwt_token}"}
    config.api_key_prefix = {"authorization": "Bearer"}

    return ApiClient(configuration=config)


def create_k8s_client() -> ApiClient:
    """
    Create a Kubernetes API client for the current request.

    If auth headers are present (from Authorino), uses the user's JWT.
    Otherwise falls back to default configuration (ServiceAccount or kubeconfig).

    Returns:
        Kubernetes API client
    """
    token = get_current_token()

    if token:
        # Use user's JWT token (passed through from Authorino)
        return create_k8s_client_from_token(token)
    else:
        # Fall back to default (for development or unauthenticated endpoints)
        from kubernetes import config as k8s_config
        try:
            k8s_config.load_incluster_config()
        except k8s_config.ConfigException:
            k8s_config.load_kube_config()

        return ApiClient()
