#!/bin/bash
#
# Deploy A2A MCP Bridge with Authorino authentication
#
# This script:
# 1. Discovers Keycloak URL from cluster
# 2. Discovers Keycloak realm
# 3. Generates kustomize overlay with environment-specific values
# 4. Deploys using kubectl + kustomize
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
A2A_BRIDGE_ROOT="$(dirname "$SCRIPT_DIR")"
DEPLOY_DIR="$A2A_BRIDGE_ROOT/deploy"

echo "======================================================================="
echo "A2A MCP Bridge - Authorino Deployment"
echo "======================================================================="
echo ""

# Auto-discover Keycloak URL
echo "[1/4] Auto-discovering Keycloak URL..."
KEYCLOAK_HOST=$(oc get route -n keycloak -o jsonpath='{.items[0].spec.host}' 2>/dev/null || true)

if [ -n "$KEYCLOAK_HOST" ]; then
    KEYCLOAK_URL="https://$KEYCLOAK_HOST"
    echo "  [+] Found Keycloak at: $KEYCLOAK_URL"
else
    echo "  [!] Could not auto-discover Keycloak URL"
    echo "      Please set KEYCLOAK_URL environment variable"
    exit 1
fi

# Auto-discover Keycloak realm
echo ""
echo "[2/4] Auto-discovering Keycloak realm..."
KEYCLOAK_REALM=$(kubectl get configmap -n kagenti-system global-environments \
    -o jsonpath='{.data.KEYCLOAK_REALM}' 2>/dev/null || echo "master")

echo "  [+] Using realm: $KEYCLOAK_REALM"

# Build issuer URL
KEYCLOAK_ISSUER_URL="$KEYCLOAK_URL/realms/$KEYCLOAK_REALM"
echo "  [+] Issuer URL: $KEYCLOAK_ISSUER_URL"

# Create overlay directory
echo ""
echo "[3/4] Generating kustomize overlay..."
OVERLAY_DIR="$DEPLOY_DIR/overlays/discovered"
mkdir -p "$OVERLAY_DIR"

# Create kustomization.yaml for overlay
cat > "$OVERLAY_DIR/kustomization.yaml" <<EOF
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - ../../base

# Replace placeholder in AuthConfig with discovered Keycloak URL
patches:
  - target:
      kind: AuthConfig
      name: a2a-mcp-bridge-auth
    patch: |-
      - op: replace
        path: /spec/authentication/keycloak-jwt/jwt/issuerUrl
        value: $KEYCLOAK_ISSUER_URL
EOF

echo "  [+] Overlay created at: $OVERLAY_DIR"

# Deploy in phases to handle CRD creation
echo ""
echo "[4/7] Deploying Authorino operator..."
kubectl apply -f "$DEPLOY_DIR/base/authorino-operator.yaml"

echo ""
echo "[5/7] Waiting for operator to be ready..."
echo "  OLM is installing the operator (this may take 1-2 minutes)..."

# Wait for the deployment to be created by OLM
echo "  Waiting for operator deployment to be created..."
TIMEOUT=180
ELAPSED=0
while ! kubectl get deployment -n authorino-operator authorino-operator &>/dev/null; do
  if [ $ELAPSED -ge $TIMEOUT ]; then
    echo "  [!] Timeout waiting for operator deployment"
    echo "      Check: kubectl get csv -n authorino-operator"
    exit 1
  fi
  sleep 5
  ELAPSED=$((ELAPSED + 5))
  echo "  Still waiting... (${ELAPSED}s)"
done

echo "  [+] Operator deployment created"
echo "  Waiting for operator to become available..."
kubectl wait --for=condition=available --timeout=120s \
  deployment/authorino-operator -n authorino-operator

echo "  [+] Operator is ready"

echo ""
echo "[6/7] Deploying namespace and Authorino instance..."
kubectl apply -f "$DEPLOY_DIR/base/namespace.yaml"
kubectl apply -f "$DEPLOY_DIR/base/authorino-instance.yaml"

echo ""
echo "  Waiting for Authorino instance to appear..."
TIMEOUT=60
ELAPSED=0
while ! kubectl get authorino authorino -n a2a-mcp-bridge &>/dev/null; do
  if [ $ELAPSED -ge $TIMEOUT ]; then
    echo "  [!] Timeout waiting for Authorino instance"
    exit 1
  fi
  sleep 2
  ELAPSED=$((ELAPSED + 2))
done

echo "  [+] Authorino instance created"
echo "  Waiting for Authorino to become ready..."
kubectl wait --for=condition=ready --timeout=120s \
  authorino/authorino -n a2a-mcp-bridge

echo ""
echo "[7/9] Deploying MCP server resources..."
kubectl apply -f "$DEPLOY_DIR/base/mcp-server-serviceaccount.yaml"
kubectl apply -f "$DEPLOY_DIR/base/mcp-server-buildconfig.yaml"
kubectl apply -f "$DEPLOY_DIR/base/mcp-server-service.yaml"

echo ""
echo "[8/9] Triggering image build..."
oc start-build a2a-mcp-bridge -n a2a-mcp-bridge --follow

echo ""
echo "[9/9] Deploying MCP server and AuthConfig..."
kubectl apply -f "$DEPLOY_DIR/base/mcp-server-deployment.yaml"
kubectl apply -f "$DEPLOY_DIR/base/mcp-server-httproute.yaml"
kubectl apply -k "$OVERLAY_DIR"

echo ""
echo "  Waiting for MCP server to be ready..."
kubectl wait --for=condition=available --timeout=120s \
  deployment/a2a-mcp-bridge -n a2a-mcp-bridge || true

echo ""
echo "======================================================================="
echo "Deployment Complete!"
echo "======================================================================="
echo ""
echo "Authorino and MCP server are now running."
echo ""
echo "Configuration:"
echo "  Namespace: a2a-mcp-bridge"
echo "  Keycloak: $KEYCLOAK_URL"
echo "  Realm: $KEYCLOAK_REALM"
echo "  Issuer: $KEYCLOAK_ISSUER_URL"
echo "  MCP Server: a2a-bridge.mcp.test.com"
echo ""
echo "Next steps:"
echo "  1. Configure Gateway to use Authorino for ext_authz"
echo "  2. Test with Claude Code"
echo ""
