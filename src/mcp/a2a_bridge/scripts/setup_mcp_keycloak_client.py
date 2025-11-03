#!/usr/bin/env python3
"""
Setup Keycloak client for A2A Bridge MCP Server.

This script creates a public client in Keycloak that allows users to obtain
JWTs which the MCP server will validate and use for Kubernetes impersonation.

Prerequisites:
- Keycloak running and accessible
- Admin credentials
- A realm created (default: 'kagenti' or 'Demo')

Features:
- Auto-discovers Keycloak URL from OpenShift routes or Kubernetes ingress
- Falls back to manual configuration via environment variables
"""

import os
import sys
import subprocess
import requests
import argparse
from typing import Optional, Tuple


def run_command(cmd: list) -> Tuple[bool, str]:
    """Run a shell command and return success status and output."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0, result.stdout.strip()
    except Exception as e:
        return False, str(e)


def discover_keycloak_url(verbose: bool = True) -> Optional[str]:
    """
    Auto-discover Keycloak URL from cluster resources.

    Tries in order:
    1. OpenShift route in keycloak namespace
    2. Kubernetes ingress in keycloak namespace

    Args:
        verbose: Print discovery progress
    """
    if verbose:
        print("Auto-discovering Keycloak URL from cluster...")

    # Try OpenShift route first
    success, output = run_command([
        "oc", "get", "route", "-n", "keycloak",
        "-o", "jsonpath={.items[0].spec.host}", "--ignore-not-found"
    ])

    if success and output:
        url = f"https://{output}" if not output.startswith("http") else output
        if verbose:
            print(f"  [+] Found OpenShift route: {url}")
        return url

    # Try kubectl with route (OpenShift CRD via kubectl)
    success, output = run_command([
        "kubectl", "get", "route", "-n", "keycloak",
        "-o", "jsonpath={.items[0].spec.host}", "--ignore-not-found"
    ])

    if success and output:
        url = f"https://{output}" if not output.startswith("http") else output
        if verbose:
            print(f"  [+] Found route: {url}")
        return url

    # Try Kubernetes ingress
    success, output = run_command([
        "kubectl", "get", "ingress", "-n", "keycloak",
        "-o", "jsonpath={.items[0].spec.rules[0].host}", "--ignore-not-found"
    ])

    if success and output:
        url = f"https://{output}" if not output.startswith("http") else output
        if verbose:
            print(f"  [+] Found Kubernetes ingress: {url}")
        return url

    if verbose:
        print("  [!] Could not auto-discover Keycloak URL")
    return None


def discover_keycloak_realm() -> str:
    """
    Discover Keycloak realm from cluster ConfigMaps or environment.
    Falls back to 'master' (Kagenti default).
    """
    # Check environment first
    env_realm = os.getenv("KEYCLOAK_REALM")
    if env_realm:
        return env_realm

    # Try to get from Kagenti global-environments ConfigMap
    success, output = run_command([
        "kubectl", "get", "configmap", "-n", "kagenti-system", "global-environments",
        "-o", "jsonpath={.data.KEYCLOAK_REALM}", "--ignore-not-found"
    ])

    if success and output:
        print(f"  [+] Found realm in ConfigMap: {output}")
        return output

    # Default to 'master' (Kagenti's default realm)
    return "master"


def get_admin_token(base_url: str, username: str, password: str, realm: str = "master") -> str:
    """Get admin access token from Keycloak."""
    url = f"{base_url}/realms/{realm}/protocol/openid-connect/token"
    data = {
        "client_id": "admin-cli",
        "username": username,
        "password": password,
        "grant_type": "password",
    }

    response = requests.post(url, data=data, verify=False)  # Note: verify=False for self-signed certs
    response.raise_for_status()
    return response.json()["access_token"]


def create_client(base_url: str, realm: str, access_token: str, client_config: dict) -> None:
    """Create a client in Keycloak."""
    url = f"{base_url}/admin/realms/{realm}/clients"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
    }

    response = requests.post(url, headers=headers, json=client_config, verify=False)
    if response.status_code == 201:
        print(f"[+] Created client: {client_config['clientId']}")
    elif response.status_code == 409:
        print(f"[!] Client already exists: {client_config['clientId']}")
    else:
        response.raise_for_status()


def create_client_scope(base_url: str, realm: str, access_token: str, scope_config: dict) -> None:
    """Create a client scope in Keycloak."""
    url = f"{base_url}/admin/realms/{realm}/client-scopes"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
    }

    response = requests.post(url, headers=headers, json=scope_config, verify=False)
    if response.status_code == 201:
        print(f"[+] Created client scope: {scope_config['name']}")
    elif response.status_code == 409:
        print(f"[!] Client scope already exists: {scope_config['name']}")
    else:
        response.raise_for_status()


def main():
    parser = argparse.ArgumentParser(
        description="Setup Keycloak client for A2A MCP Bridge",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Auto-discover from cluster
  python setup_mcp_keycloak_client.py --auto-discover

  # Manually specify URL
  python setup_mcp_keycloak_client.py --url https://keycloak.example.com

  # Use environment variables
  export KEYCLOAK_URL=https://keycloak.example.com
  python setup_mcp_keycloak_client.py
        """
    )
    parser.add_argument(
        "--auto-discover",
        action="store_true",
        help="Auto-discover Keycloak URL from cluster (OpenShift route or K8s ingress)"
    )
    parser.add_argument(
        "--url",
        help="Keycloak base URL (e.g., https://keycloak.example.com)"
    )
    parser.add_argument(
        "--realm",
        help="Keycloak realm (default: kagenti or auto-discovered)"
    )
    parser.add_argument(
        "--admin-user",
        default="admin",
        help="Keycloak admin username (default: admin)"
    )
    parser.add_argument(
        "--admin-password",
        help="Keycloak admin password (or use KEYCLOAK_ADMIN_PASSWORD env var)"
    )

    args = parser.parse_args()

    print("=" * 70)
    print("A2A MCP Bridge - Keycloak Client Setup")
    print("=" * 70)
    print()

    # Determine Keycloak URL
    base_url = None
    if args.url:
        base_url = args.url
        print(f"Using provided URL: {base_url}")
    elif args.auto_discover:
        base_url = discover_keycloak_url()
    else:
        # Check environment variable
        base_url = os.getenv("KEYCLOAK_URL")
        if base_url:
            print(f"Using KEYCLOAK_URL from environment: {base_url}")

    if not base_url:
        print("[!] Could not find Keycloak URL.")
        print("    Please use one of:")
        print("    - --auto-discover flag to discover from cluster")
        print("    - --url <keycloak-url> to specify manually")
        print("    - KEYCLOAK_URL environment variable")
        sys.exit(1)

    # Determine realm
    if args.realm:
        realm = args.realm
        print(f"Using provided realm: {realm}")
    else:
        realm = discover_keycloak_realm()
        print(f"Using realm: {realm}")

    # Determine admin credentials
    admin_user = args.admin_user
    admin_pass = args.admin_password or os.getenv("KEYCLOAK_ADMIN_PASSWORD")

    if not admin_pass:
        print("[!] KEYCLOAK_ADMIN_PASSWORD environment variable is required.")
        print("    Set it before running this script:")
        print("    export KEYCLOAK_ADMIN_PASSWORD='your-admin-password'")
        sys.exit(1)

    print(f"\nConfiguration:")
    print(f"  Keycloak URL: {base_url}")
    print(f"  Realm: {realm}")
    print(f"  Admin User: {admin_user}")
    print()

    # Get admin token
    print("Authenticating as admin...")
    try:
        # Disable SSL warnings for self-signed certs
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        token = get_admin_token(base_url, admin_user, admin_pass)
        print("[+] Authenticated\n")
    except Exception as e:
        print(f"[!] Failed to authenticate: {e}")
        print(f"    Please verify credentials and URL are correct.")
        sys.exit(1)

    # Create client scope for Kubernetes groups
    print("Creating client scope for Kubernetes groups...")
    k8s_groups_scope = {
        "name": "kubernetes-groups",
        "protocol": "openid-connect",
        "attributes": {
            "include.in.token.scope": "true",
            "display.on.consent.screen": "false"
        },
        "protocolMappers": [
            {
                "name": "kubernetes-groups",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-group-membership-mapper",
                "config": {
                    "claim.name": "groups",
                    "full.path": "false",
                    "id.token.claim": "true",
                    "access.token.claim": "true",
                    "userinfo.token.claim": "true"
                }
            },
            {
                "name": "kubernetes-username",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-usermodel-property-mapper",
                "config": {
                    "user.attribute": "username",
                    "claim.name": "preferred_username",
                    "id.token.claim": "true",
                    "access.token.claim": "true",
                    "userinfo.token.claim": "true"
                }
            },
            {
                "name": "email",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-usermodel-property-mapper",
                "config": {
                    "user.attribute": "email",
                    "claim.name": "email",
                    "id.token.claim": "true",
                    "access.token.claim": "true",
                    "userinfo.token.claim": "true"
                }
            }
        ]
    }

    try:
        create_client_scope(base_url, realm, token, k8s_groups_scope)
    except Exception as e:
        print(f"[!] Failed to create client scope: {e}\n")

    # Auto-discover OpenShift OAuth callback URL
    print("Discovering OpenShift OAuth callback URL...")
    oauth_callback_url = None
    success, output = run_command([
        "oc", "get", "route", "-n", "openshift-authentication",
        "-o", "jsonpath={.items[0].spec.host}", "--ignore-not-found"
    ])

    if success and output:
        oauth_callback_url = f"https://{output}/oauth2callback/keycloak"
        print(f"  [+] Found OAuth callback: {oauth_callback_url}")
    else:
        print("  [!] Could not auto-discover OAuth callback URL")
        print("      You may need to add it manually after setup")

    # Build redirect URIs list
    redirect_uris = [
        "http://localhost:*",
        "http://127.0.0.1:*",
    ]

    if oauth_callback_url:
        redirect_uris.append(oauth_callback_url)

    print()

    # Create confidential client for MCP server and CLI login
    print("Creating confidential client for MCP server...")
    mcp_client = {
        "clientId": "a2a-mcp-bridge",
        "name": "A2A MCP Bridge",
        "description": "Confidential client for A2A Bridge MCP Server and CLI authentication",
        "enabled": True,
        "publicClient": False,  # Confidential client with secret
        "standardFlowEnabled": True,  # Authorization code flow
        "directAccessGrantsEnabled": True,  # Direct grant (for testing)
        "serviceAccountsEnabled": False,
        "protocol": "openid-connect",
        "fullScopeAllowed": False,
        "attributes": {
            "pkce.code.challenge.method": "",  # PKCE optional (OpenShift OAuth doesn't use it)
            "access.token.lifespan": "300",  # 5 minutes
        },
        "redirectUris": redirect_uris,
        "webOrigins": ["+"],  # Allow CORS for redirectUris
        "defaultClientScopes": [
            "email",
            "profile",
            "roles",
            "web-origins"
        ],
        "optionalClientScopes": [
            "address",
            "phone",
            "offline_access",
            "kubernetes-groups"
        ]
    }

    try:
        create_client(base_url, realm, token, mcp_client)
    except Exception as e:
        print(f"[!] Failed to create client: {e}\n")
        sys.exit(1)

    print("\n" + "="*70)
    print("Setup complete!")
    print("="*70)
    print("\nNext steps:")
    print()
    print("1. Get the client secret from Keycloak:")
    print(f"   - Go to {base_url}/admin/master/console")
    print(f"   - Navigate to Clients -> a2a-mcp-bridge -> Credentials")
    print(f"   - Copy the Client Secret")
    print()
    print("2. Create Kubernetes secret for OpenShift OAuth (if using configure_openshift_oidc.sh):")
    print("   oc create secret generic keycloak-client-secret \\")
    print("     --from-literal=clientSecret=<CLIENT_SECRET> \\")
    print("     -n openshift-config")
    print()
    print("3. Configure your MCP server with these environment variables:")
    print(f"   export KEYCLOAK_ISSUER={base_url}/realms/{realm}")
    print(f"   export KEYCLOAK_AUDIENCE=a2a-mcp-bridge")
    print(f"   export KEYCLOAK_USER_CLAIM=preferred_username")
    print(f"   export KEYCLOAK_GROUPS_CLAIM=groups")
    print(f"   export REQUIRE_AUTH=true")
    print()
    print("2. Test getting a token (Direct Grant - for testing only!):")
    print(f"   curl -k -X POST '{base_url}/realms/{realm}/protocol/openid-connect/token' \\")
    print(f"     -H 'Content-Type: application/x-www-form-urlencoded' \\")
    print(f"     -d 'grant_type=password' \\")
    print(f"     -d 'client_id=a2a-mcp-bridge' \\")
    print(f"     -d 'username=USERNAME' \\")
    print(f"     -d 'password=YOUR_PASSWORD' \\")
    print(f"     -d 'scope=openid profile email kubernetes-groups'")
    print()
    print("3. Use that token with your MCP server:")
    print("   Authorization: Bearer <access_token>")
    print()
    print("4. Grant Kubernetes RBAC to user 'USERNAME':")
    print("   kubectl create rolebinding USERNAME-agentcards \\")
    print("     --role=agentcards-reader \\")
    print("     --user=USERNAME \\")
    print("     --namespace=<namespace>")
    print()


if __name__ == "__main__":
    main()
