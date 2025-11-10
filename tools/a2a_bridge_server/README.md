# A2A Bridge MCP Server

An MCP (Model Context Protocol) server that bridges MCP clients (like Claude, coding assistants, and other agents) to [A2A-compliant agents](https://github.com/a2a-protocol/a2a-protocol) running in Kubernetes clusters managed by Kagenti.

## What is this?

This MCP server allows agents and coding assistants to discover and interact with A2A agents deployed in your Kubernetes cluster. Once connected, they can:

- Discover available agents in your cluster
- Get details about agent capabilities and skills
- Send messages to agents using the A2A protocol
- Orchestrate multi-agent workflows

The bridge handles all the Kubernetes and A2A protocol complexity, providing simple MCP tools to work with your agent ecosystem.

## Quick Start

### 1. Install and Run

```bash
# Install dependencies
uv sync

# Run the server
uv run server.py
```

The server will start on `http://localhost:8000` and use your local kubeconfig to access the cluster.

### 2. Connect to an MCP Client

For example, with Claude Desktop:

```bash
claude mcp add a2a-mcp --protocol http http://localhost:8000/mcp
```

### 3. Try it out!

You can now ask your agent to:
- "What agents are available in my cluster?"
- "Show me agents that can help with weather"
- "Get details about the my-agent in the kagenti-system namespace"

## Authentication Modes

The A2A Bridge supports two authentication modes:

### Local Mode (Development)

When running locally without authentication headers, the server uses your local kubeconfig. Perfect for:
- Development and testing
- Connecting coding assistants to your cluster
- Quick prototyping

**No additional configuration needed** - just make sure your kubeconfig has access to the cluster.

### Token Mode (Production)

When deployed in a Kubernetes cluster, the server accepts JWT tokens via the `X-Auth-Token` header. This enables:
- **Identity propagation**: Agents pass their service account tokens when calling other agents
- **RBAC enforcement**: Each request uses the caller's Kubernetes identity
- **Multi-tenant security**: Callers only see agents they have permission to access

This mode is designed for agent-to-agent communication where each agent maintains its own identity.

## Testing Token Flow

Use the included test script to verify JWT token authentication:

```bash
# Create a service account token and test
./scripts/test_token_flow.sh $(kubectl create token <service-account> --duration=1h)

# Test with specific namespace
./scripts/test_token_flow.sh $(kubectl create token <service-account>) --namespace default

# Test across all namespaces
./scripts/test_token_flow.sh $(kubectl create token <service-account>) --all-namespaces
```

This demonstrates how agents in the cluster can use their own tokens to discover and interact with other agents while maintaining their identity.

## Available MCP Tools

Once connected, these tools become available to your MCP client:

- **`discover_agents`** - Find agents in the cluster (returns full JSON metadata)
- **`list_agents`** - Get a formatted table of agents (supports filtering by skill/name)
- **`get_agent_details`** - Get detailed info about a specific agent
- **`send_message_to_agent`** - Send a message to an agent
- **`send_streaming_message_to_agent`** - Send a streaming message to an agent

## How It Works

The A2A Bridge leverages Kagenti's **AgentCard CRD**, which caches agent card data from A2A-compliant agents:

- Agent discovery is fast (no HTTP calls needed, just Kubernetes API queries)
- Agent metadata is automatically kept up-to-date by the Kagenti operator
- When sending messages, the bridge communicates directly with agent endpoints using the A2A protocol

## Requirements

- Python 3.12+
- Kubernetes cluster with Kagenti installed
- kubectl configured (for local mode) or valid service account tokens (for production mode)

## Deployment

When deployed in a Kubernetes cluster, agents can call this MCP server by passing their service account tokens in the `X-Auth-Token` header. The server will use that token to authenticate with the Kubernetes API, ensuring RBAC policies are enforced based on the calling agent's identity.

This maintains security boundaries in multi-tenant environments where different agents should have different levels of access.
