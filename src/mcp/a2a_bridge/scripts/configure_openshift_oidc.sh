#!/bin/bash
#
# Configure OpenShift OAuth to trust Keycloak as an OIDC provider
#
# This enables direct authentication delegation - no impersonation needed.
#

set -e

KEYCLOAK_URL="${KEYCLOAK_URL:-}"
KEYCLOAK_REALM="${KEYCLOAK_REALM:-master}"

echo "======================================================================="
echo "OpenShift OAuth + Keycloak OIDC Integration"
echo "======================================================================="
echo ""

# Auto-discover Keycloak URL if not set
if [ -z "$KEYCLOAK_URL" ]; then
    echo "[1/5] Auto-discovering Keycloak URL..."
    KEYCLOAK_HOST=$(oc get route -n keycloak -o jsonpath='{.items[0].spec.host}' 2>/dev/null || true)

    if [ -n "$KEYCLOAK_HOST" ]; then
        KEYCLOAK_URL="https://$KEYCLOAK_HOST"
        echo "  [+] Found Keycloak at: $KEYCLOAK_URL"
    else
        echo "  [!] Could not auto-discover Keycloak URL"
        echo "      Please set KEYCLOAK_URL environment variable"
        echo "      Example: export KEYCLOAK_URL=https://keycloak.example.com"
        exit 1
    fi
else
    echo "[1/5] Using provided Keycloak URL: $KEYCLOAK_URL"
fi

ISSUER_URL="$KEYCLOAK_URL/realms/$KEYCLOAK_REALM"
echo "  Issuer URL: $ISSUER_URL"
echo ""

# Get Keycloak CA certificate
echo "[2/5] Fetching Keycloak CA certificate..."

# Try to get from Keycloak pod
CA_CERT=$(oc get secret -n keycloak keycloak-tls -o jsonpath='{.data.ca\.crt}' 2>/dev/null || true)

if [ -z "$CA_CERT" ]; then
    echo "  [!] Could not find Keycloak CA cert in secret"
    echo "      Attempting to fetch from Keycloak endpoint..."

    # Fetch CA cert from the server
    CA_CERT=$(echo | openssl s_client -showcerts -connect "${KEYCLOAK_HOST}:443" 2>/dev/null | \
              awk '/BEGIN CERTIFICATE/,/END CERTIFICATE/' | \
              base64 | tr -d '\n')
fi

if [ -z "$CA_CERT" ]; then
    echo "  [!] Warning: Could not fetch CA certificate"
    echo "      You may need to add it manually if using self-signed certs"
else
    echo "  [+] CA certificate retrieved"
fi
echo ""

# Create ConfigMap with CA certificate
echo "[3/5] Creating ConfigMap for Keycloak CA certificate..."
if [ -n "$CA_CERT" ]; then
    cat <<EOF | oc apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: keycloak-ca-bundle
  namespace: openshift-config
data:
  ca.crt: |
$(echo "$CA_CERT" | base64 -d | sed 's/^/    /')
EOF
    echo "  [+] ConfigMap created"
else
    echo "  [!] Skipping CA ConfigMap creation"
fi
echo ""

# Configure OAuth
echo "[4/5] Configuring OpenShift OAuth..."

# Build the JSON config based on whether we have a CA cert
if [ -n "$CA_CERT" ]; then
    # With CA configuration
    oc patch oauth cluster --type merge -p "$(cat <<EOF
{
  "spec": {
    "identityProviders": [
      {
        "name": "keycloak",
        "type": "OpenID",
        "mappingMethod": "claim",
        "openID": {
          "issuer": "$ISSUER_URL",
          "clientID": "a2a-mcp-bridge",
          "clientSecret": {
            "name": "keycloak-client-secret"
          },
          "claims": {
            "preferredUsername": ["preferred_username"],
            "name": ["name"],
            "email": ["email"],
            "groups": ["groups"]
          },
          "ca": {
            "name": "keycloak-ca-bundle"
          }
        }
      }
    ]
  }
}
EOF
)"
else
    # Without CA configuration
    oc patch oauth cluster --type merge -p "$(cat <<EOF
{
  "spec": {
    "identityProviders": [
      {
        "name": "keycloak",
        "type": "OpenID",
        "mappingMethod": "claim",
        "openID": {
          "issuer": "$ISSUER_URL",
          "clientID": "a2a-mcp-bridge",
          "clientSecret": {
            "name": "keycloak-client-secret"
          },
          "claims": {
            "preferredUsername": ["preferred_username"],
            "name": ["name"],
            "email": ["email"],
            "groups": ["groups"]
          }
        }
      }
    ]
  }
}
EOF
)"
fi

echo "  [+] OAuth configuration updated"
echo ""

# Note about client secret
echo "[5/5] Client Secret Configuration"
echo ""
echo "  The OAuth configuration references a secret 'keycloak-client-secret'"
echo "  that doesn't exist yet. You have two options:"
echo ""
echo "  Option A: Use a public client (recommended for MCP use case)"
echo "    - Update your Keycloak client 'a2a-mcp-bridge' to be confidential"
echo "    - Generate a client secret in Keycloak"
echo "    - Create the secret:"
echo ""
echo "      oc create secret generic keycloak-client-secret \\"
echo "        --from-literal=clientSecret=<your-client-secret> \\"
echo "        -n openshift-config"
echo ""
echo "  Option B: Use implicit flow (less secure, for testing only)"
echo "    - Remove the clientSecret reference from OAuth config"
echo "    - Keep 'a2a-mcp-bridge' as a public client"
echo ""

echo "======================================================================="
echo "Configuration Complete!"
echo "======================================================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Restart OAuth pods to pick up the new configuration:"
echo "   oc delete pod -n openshift-authentication -l app=oauth-openshift"
echo ""
echo "2. Wait for OAuth pods to be ready:"
echo "   oc wait --for=condition=ready pod -n openshift-authentication -l app=oauth-openshift --timeout=120s"
echo ""
echo "3. Test login:"
echo "   oc login --web"
echo "   (You should see 'keycloak' as a login option)"
echo ""
echo "4. Get a token for your MCP server:"
echo "   TOKEN=\$(curl -k '$ISSUER_URL/protocol/openid-connect/token' \\"
echo "     -d 'grant_type=password' \\"
echo "     -d 'client_id=a2a-mcp-bridge' \\"
echo "     -d 'username=mofoster' \\"
echo "     -d 'password=YOUR_PASSWORD' | jq -r .access_token)"
echo ""
echo "5. Verify the token works with Kubernetes:"
echo "   kubectl --token=\"\$TOKEN\" get agentcards -A"
echo ""
echo "Users authenticated via Keycloak will have the prefix: keycloak:"
echo "Example: User 'mofoster' → Kubernetes user 'keycloak:mofoster'"
echo ""
