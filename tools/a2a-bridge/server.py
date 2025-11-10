#!/usr/bin/env python3
"""
MCP Server for A2A Agent Discovery using Kagenti's AgentCard CRD.

This server provides tools to discover and interact with A2A-compliant agents
in Kubernetes clusters running Kagenti. It uses the AgentCard CRD which caches
agent card data, eliminating the need for direct HTTP calls to agent endpoints.

Authentication:
This server is intended to recieve a jwt token for authorization to the kubernetes api. 
- X-Auth-Token: JWT token

The server uses the JWT to call Kubernetes API, enforcing user-level RBAC.
"""

from typing import Optional
from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from lib import discovery, a2a, auth


# Create the MCP server
mcp = FastMCP("A2A Bridge")


class AuthHeaderMiddleware(BaseHTTPMiddleware):
    """
    Middleware to extract authentication injected auth headers.

    We extract these and store in context for use in tool handlers.
    """

    async def dispatch(self, request: Request, call_next):
        # Extract auth headers (case-insensitive)
        token = request.headers.get("x-auth-token") or request.headers.get("X-Auth-Token")

        # Store in context for this request
        auth.set_auth_context(token=token)

        try:
            response = await call_next(request)
        finally:
            # Clear context after request
            auth.set_auth_context(None)

        return response


# Prepare middleware to pass to mcp.run()
AUTH_MIDDLEWARE = [Middleware(AuthHeaderMiddleware)]


@mcp.tool()
def discover_agents(
    namespace: Optional[str] = None,
    all_namespaces: bool = False,
) -> str:
    """
    Discover agents in the Kubernetes cluster using AgentCard resources.

    AgentCards cache agent card data, so this tool returns immediately without
    making HTTP calls to agent endpoints. The Kagenti operator keeps this data
    up-to-date automatically.

    Args:
        namespace: Specific namespace to search (optional)
        all_namespaces: Search across all namespaces (default: False)

    Returns:
        JSON array of discovered agents with their cached metadata
    """
    return discovery.discover_agents(namespace, all_namespaces)


@mcp.tool()
def list_agents(
    namespace: Optional[str] = None,
    all_namespaces: bool = False,
    filter: Optional[str] = None,
) -> str:
    """
    Get a summary table of all discovered agents.

    Returns a formatted table showing key information about each agent,
    including name, version, protocol, sync status, and URL.

    Args:
        namespace: Specific namespace to search (optional)
        all_namespaces: Search across all namespaces (default: False)
        filter: Case-insensitive substring to filter agents by skill, name, or description.
               Example: filter="weather" finds agents with "weather" in their skills.

    Returns:
        Formatted table of agent information
    """
    return discovery.list_agents(namespace, all_namespaces, filter=filter)


@mcp.tool()
def get_agent_details(
    agentcard_name: str,
    namespace: str,
) -> str:
    """
    Get detailed information about a specific agent including all skills.

    Args:
        agentcard_name: Name of the AgentCard resource
        namespace: Namespace where the AgentCard exists

    Returns:
        Detailed JSON information about the agent and its capabilities
    """
    return discovery.get_agent_details(agentcard_name, namespace)


@mcp.tool()
async def send_message_to_agent(
    agent_url: str,
    message: str,
    use_extended_card: bool = False,
) -> str:
    """
    Send a message to an A2A agent and get the response.

    Args:
        agent_url: The base URL of the agent (from AgentCard status.card.url)
        message: The message text to send
        use_extended_card: Whether to attempt fetching the extended agent card

    Returns:
        JSON response from the agent
    """
    return await a2a.send_message_to_agent(agent_url, message, use_extended_card)


@mcp.tool()
async def send_streaming_message_to_agent(
    agent_url: str,
    message: str,
    use_extended_card: bool = False,
) -> str:
    """
    Send a streaming message to an A2A agent and get the streaming response.

    Args:
        agent_url: The base URL of the agent (from AgentCard status.card.url)
        message: The message text to send
        use_extended_card: Whether to attempt fetching the extended agent card

    Returns:
        All streaming response chunks from the agent as JSON
    """
    return await a2a.send_streaming_message_to_agent(
        agent_url, message, use_extended_card
    )


def main():
    """Run the MCP server with uvicorn."""
    import uvicorn
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    # Health check handler for Kubernetes probes
    async def health(_):
        return PlainTextResponse("OK")

    # Create HTTP app with custom middleware
    app = mcp.http_app(middleware=AUTH_MIDDLEWARE)

    # Add health check routes
    app.routes.append(Route("/health", health))
    app.routes.append(Route("/healthz", health))

    # Run with uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
