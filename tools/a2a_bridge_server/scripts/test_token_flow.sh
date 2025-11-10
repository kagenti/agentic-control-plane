#!/bin/bash
#
# Test MCP server with JWT token authentication
#
# Usage:
#   ./scripts/test_token_flow.sh <token>
#   ./scripts/test_token_flow.sh $(kubectl create token mfoster --duration=1h)
#
# Options:
#   --namespace <name>    Namespace to query (default: kagenti-system)
#   --all-namespaces      Query all namespaces

set -e

# Parse arguments
TOKEN=""
NAMESPACE="kagenti-system"
ALL_NAMESPACES="false"

while [[ $# -gt 0 ]]; do
    case $1 in
        --namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        --all-namespaces)
            ALL_NAMESPACES="true"
            shift
            ;;
        *)
            TOKEN="$1"
            shift
            ;;
    esac
done

if [ -z "$TOKEN" ]; then
    echo "Error: No token provided"
    echo ""
    echo "Usage: $0 <token> [--namespace <name>] [--all-namespaces]"
    echo ""
    echo "Examples:"
    echo "  $0 \$(kubectl create token mfoster --duration=1h)"
    echo "  $0 \$(kubectl create token mfoster --duration=1h) --namespace default"
    echo "  $0 \$(kubectl create token mfoster --duration=1h) --all-namespaces"
    exit 1
fi

SERVER_URL="${SERVER_URL:-http://localhost:8000/mcp}"

echo "🔑 Testing MCP Token Authentication"
echo "=================================="
echo "Server: $SERVER_URL"
echo "Token length: ${#TOKEN} chars"
echo ""

# Decode token to show identity
echo "📋 Token Identity:"
IDENTITY=$(echo "$TOKEN" | cut -d'.' -f2 | base64 -D 2>/dev/null | tr -d '\0' | grep -o '"sub":"system:[^"]*"' | cut -d'"' -f4 || echo "")
if [ -n "$IDENTITY" ]; then
    echo "  $IDENTITY"
else
    echo "  (decoded from token)"
fi
echo ""

# Initialize session
echo "📡 Initializing MCP session..."
INIT_RESPONSE=$(curl -s -D /tmp/headers_$$.txt -X POST "$SERVER_URL" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-Auth-Token: $TOKEN" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}')

# Extract session ID from headers
SESSION_ID=$(grep -i "mcp-session-id:" /tmp/headers_$$.txt | cut -d' ' -f2 | tr -d '\r')
rm -f /tmp/headers_$$.txt

if [ -z "$SESSION_ID" ]; then
    echo "❌ Failed to initialize session"
    echo "$INIT_RESPONSE"
    exit 1
fi

echo "✅ Session initialized: $SESSION_ID"
echo ""

# Call list_agents tool
if [ "$ALL_NAMESPACES" = "true" ]; then
    echo "🔍 Listing agents across all namespaces..."
    ARGS='{"all_namespaces":true}'
else
    echo "🔍 Listing agents in namespace: $NAMESPACE..."
    ARGS="{\"namespace\":\"$NAMESPACE\",\"all_namespaces\":false}"
fi
echo ""

CALL_RESPONSE=$(curl -s -X POST "$SERVER_URL" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-Auth-Token: $TOKEN" \
  -H "mcp-session-id: $SESSION_ID" \
  -d "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"list_agents\",\"arguments\":$ARGS}}")

# Extract and display result
echo "📊 Results:"
echo "=================================="
echo "$CALL_RESPONSE" | grep 'data:' | sed 's/.*data: //' | jq -r '.result.content[0].text // .error.message // .error // .' 2>/dev/null || echo "$CALL_RESPONSE"
echo ""
echo "✅ Test complete!"
