#!/usr/bin/env python3
"""
MCP Server for A2A Agent Discovery using Kagenti's AgentCard CRD.

This server provides tools to discover and interact with A2A-compliant agents
in Kubernetes clusters running Kagenti. It uses the AgentCard CRD which caches
agent card data, eliminating the need for direct HTTP calls to agent endpoints.
"""

from typing import Optional
from fastmcp import FastMCP

from lib import discovery, a2a


# Create the MCP server
mcp = FastMCP("A2A Bridge")


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
    auth_token: Optional[str] = None,
    use_extended_card: bool = False,
) -> str:
    """
    Send a message to an A2A agent and get the response.

    Args:
        agent_url: The base URL of the agent (from AgentCard status.card.url)
        message: The message text to send
        auth_token: Optional OAuth token for authenticated requests
        use_extended_card: Whether to attempt fetching the extended agent card

    Returns:
        JSON response from the agent
    """
    return await a2a.send_message_to_agent(agent_url, message, auth_token, use_extended_card)


@mcp.tool()
async def send_streaming_message_to_agent(
    agent_url: str,
    message: str,
    auth_token: Optional[str] = None,
    use_extended_card: bool = False,
) -> str:
    """
    Send a streaming message to an A2A agent and get the streaming response.

    Args:
        agent_url: The base URL of the agent (from AgentCard status.card.url)
        message: The message text to send
        auth_token: Optional OAuth token for authenticated requests
        use_extended_card: Whether to attempt fetching the extended agent card

    Returns:
        All streaming response chunks from the agent as JSON
    """
    return await a2a.send_streaming_message_to_agent(
        agent_url, message, auth_token, use_extended_card
    )


def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
