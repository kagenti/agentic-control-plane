"""
Authentication utilities Kuberenetes Client creation.

Allowing for either:
  - kubeconfig client creation: local development, or service acount.
    or
  - jwt_token based client creation: useful for delegation of identity.

"""

import os
import contextvars
import logging
from kubernetes import config as k8s_config
from kubernetes.client import ApiClient, Configuration


# Set up logging
logging.basicConfig(level=logging.INFO)

_current_token = contextvars.ContextVar('current_token', default=None)


def set_auth_context(token: str | None) -> None:
    """
    Store authentication info for the current request.

    Args:
        token: JWT from X-Auth-Token header
    """
    _current_token.set(token)


def create_k8s_client_from_token(jwt_token: str) -> ApiClient:
    """
    Create a Kubernetes API client using a user's JWT token.

    Args:
        jwt_token: JWT token issued tby the Kubernetes API.

    Returns:
        Kubernetes API client configured with the user's token
    """
    config = Configuration()

    # Determine API server URL and CA cert
    if os.path.exists('/var/run/secrets/kubernetes.io/serviceaccount/token'):
        # Running in-cluster
        config.host = "https://kubernetes.default.svc"
        ca_cert = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
        if os.path.exists(ca_cert):
            config.ssl_ca_cert = ca_cert
    else:
        # Running locally - get API server URL from kubeconfig
        try:
            k8s_config.load_incluster_config()
        except k8s_config.ConfigException:
            k8s_config.load_kube_config()

        # Get the host and SSL CA cert from the loaded config
        default_config = Configuration.get_default_copy()
        config.host = default_config.host
        config.ssl_ca_cert = default_config.ssl_ca_cert
        config.verify_ssl = default_config.verify_ssl

    # Use the user's JWT as bearer token
    # Let the client library add the "Bearer" prefix via api_key_prefix
    config.api_key = {"authorization": jwt_token}
    config.api_key_prefix = {"authorization": "Bearer"}

    return ApiClient(configuration=config)


def create_k8s_client_from_kubeconfig() -> ApiClient:
    try:
        k8s_config.load_incluster_config()
    except k8s_config.ConfigException:
        k8s_config.load_kube_config()

    return ApiClient()

def create_k8s_client(token_auth_only=False):
    """
    Attempt to create a kubernetes api client from a token if one is available.
    
    if token_auth_only is False it will try to fall back to using a local kubeconfig if a token
    is not available.

    if token_auth_only is True it will instead raise value error.
    """
    jwt_token = _current_token.get()
    if jwt_token:
        logging.info("Using supplied JWT token for client auth.")
        return create_k8s_client_from_token(jwt_token)
    elif not token_auth_only:
        logging.info("Falling back to local kubeconfig for client auth.")
        return create_k8s_client_from_kubeconfig() 
    raise ValueError("Unable to create kubernetes api client: no JWT token supplied.")
