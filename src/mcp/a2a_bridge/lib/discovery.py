"""Agent discovery functionality using Kubernetes AgentCard CRDs."""

import json
from typing import Optional, Dict, Any, List
from kubernetes import client
from kubernetes.client.exceptions import ApiException
from . import auth


def _get_k8s_client() -> client.CustomObjectsApi:
    """
    Get a Kubernetes API client for the current request.

    Uses the authenticated user's JWT if available (from Authorino headers),
    otherwise falls back to default configuration.

    Returns:
        Kubernetes CustomObjectsApi client
    """
    api_client = auth.create_k8s_client()
    return client.CustomObjectsApi(api_client)


def get_namespace_scope(
    namespace: Optional[str] = None,
    all_namespaces: bool = False
) -> tuple[Optional[str], str]:
    """
    Determine namespace scope for Kubernetes API calls.

    Args:
        namespace: Specific namespace to search (optional)
        all_namespaces: Search across all namespaces (default: False)

    Returns:
        Tuple of (namespace_value, scope_message)
        - namespace_value: None for all namespaces, or specific namespace string
        - scope_message: Human-readable description of the scope
    """
    if all_namespaces:
        return None, "all namespaces"
    elif namespace:
        return namespace, f"namespace: {namespace}"
    else:
        # When authenticated via Authorino, we don't have a "current namespace"
        # Default to 'default' namespace
        # Users should specify the namespace explicitly for better clarity
        return "default", "namespace: default"


def discover_agent_cards(
    namespace: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Discover AgentCard resources using Kubernetes API.

    Args:
        namespace: Specific namespace to search, or None for all namespaces

    Returns:
        List of AgentCard CRD objects as dictionaries
    """
    try:
        custom_api = _get_k8s_client()

        # Call the appropriate API method based on namespace scope
        if namespace is None:
            # List across all namespaces
            result = custom_api.list_cluster_custom_object(
                group="agent.kagenti.dev",
                version="v1alpha1",
                plural="agentcards"
            )
        else:
            # List in specific namespace
            result = custom_api.list_namespaced_custom_object(
                group="agent.kagenti.dev",
                version="v1alpha1",
                namespace=namespace,
                plural="agentcards"
            )

        return result.get("items", [])

    except ApiException as e:
        if e.status == 404:
            raise Exception(
                "AgentCard CRD not found. Ensure Kagenti operator is installed."
            )
        elif e.status == 403:
            raise Exception(
                "Permission denied to access AgentCard resources. "
                "Check RBAC permissions."
            )
        else:
            raise Exception(f"Kubernetes API error: {e}")
    except Exception as e:
        raise Exception(f"Failed to discover agent cards: {e}")


def get_agents_data(
    namespace: Optional[str] = None,
    all_namespaces: bool = False,
) -> tuple[List[Dict[str, Any]], str]:
    """
    Get agent data without formatting.

    Args:
        namespace: Specific namespace to search (optional)
        all_namespaces: Search across all namespaces (default: False)

    Returns:
        Tuple of (agents list, scope message)
    """
    # Get namespace scope
    namespace_value, scope_msg = get_namespace_scope(namespace, all_namespaces)

    # Discover AgentCard CRs
    agent_card_crs = discover_agent_cards(namespace_value)

    if not agent_card_crs:
        return [], scope_msg

    # Process discovered AgentCard CRs
    agents = []
    for card_cr in agent_card_crs:
        metadata = card_cr.get("metadata", {})
        status = card_cr.get("status", {})

        # Extract basic metadata
        card_name = metadata.get("name", "unknown")
        card_namespace = metadata.get("namespace", "")

        # Get cached agent card data from status
        card_data = status.get("card", {})

        # Get sync status
        conditions = status.get("conditions", [])
        synced_condition = next(
            (c for c in conditions if c.get("type") == "Synced"), {}
        )
        sync_status = synced_condition.get("status", "Unknown")
        sync_message = synced_condition.get("message", "")

        last_sync_time = status.get("lastSyncTime", "")
        protocol = status.get("protocol", "unknown")

        agent_info = {
            "agentcard_name": card_name,
            "namespace": card_namespace,
            "agent_name": card_data.get("name", ""),
            "description": card_data.get("description", ""),
            "version": card_data.get("version", ""),
            "url": card_data.get("url", ""),
            "protocol": protocol,
            "capabilities": card_data.get("capabilities", {}),
            "skills": card_data.get("skills", []),
            "supports_authenticated_extended_card": card_data.get(
                "supportsAuthenticatedExtendedCard", False
            ),
            "sync_status": sync_status,
            "sync_message": sync_message,
            "last_sync_time": last_sync_time,
        }

        agents.append(agent_info)

    return agents, scope_msg


def discover_agents(
    namespace: Optional[str] = None,
    all_namespaces: bool = False,
) -> str:
    """
    Discover agents in the Kubernetes cluster using AgentCard resources.

    AgentCards cache agent card data, so this function returns immediately without
    making HTTP calls to agent endpoints. The Kagenti operator keeps this data
    up-to-date automatically.

    Args:
        namespace: Specific namespace to search (optional)
        all_namespaces: Search across all namespaces (default: False)

    Returns:
        JSON array of discovered agents with their cached metadata
    """
    agents, scope_msg = get_agents_data(namespace, all_namespaces)

    if not agents:
        return (
            f"No agents found in {scope_msg}.\n\n"
            "AgentCards are automatically created by the Kagenti operator when "
            "Agents are deployed with the kagenti.io/type=agent label."
        )

    result_text = f"Found {len(agents)} agent(s) in {scope_msg}:\n\n"
    result_text += json.dumps(agents, indent=2)

    return result_text


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
        filter: Optional case-insensitive substring to filter agents by.
               Searches across agent name, description, and skill names/descriptions.

    Returns:
        Formatted table of agent information
    """
    try:
        agents, scope_msg = get_agents_data(namespace, all_namespaces)

        if not agents:
            return (
                f"No agents found in {scope_msg}.\n\n"
                "AgentCards are automatically created by the Kagenti operator when "
                "Agents are deployed with the kagenti.io/type=agent label."
            )

        # Apply filter if provided
        if filter:
            filter_lower = filter.lower()
            filtered_agents = []

            for agent in agents:
                # Search in agent name
                if filter_lower in (agent["agent_name"] or "").lower():
                    filtered_agents.append(agent)
                    continue

                # Search in description
                if filter_lower in (agent["description"] or "").lower():
                    filtered_agents.append(agent)
                    continue

                # Search in skills
                for skill in agent.get("skills", []):
                    skill_name = skill.get("name", "").lower()
                    skill_desc = skill.get("description", "").lower()
                    if filter_lower in skill_name or filter_lower in skill_desc:
                        filtered_agents.append(agent)
                        break

            agents = filtered_agents

            if not agents:
                return f"No agents matching filter '{filter}' found in {scope_msg}."

        # Create summary table
        summary = "Agent Summary:\n\n"
        if filter:
            summary += f"Filter: '{filter}'\n\n"

        summary += f"{'AGENT NAME':<25} {'VERSION':<12} {'PROTOCOL':<10} {'SYNCED':<8} {'NAMESPACE':<20} {'URL':<50}\n"
        summary += f"{'-'*25} {'-'*12} {'-'*10} {'-'*8} {'-'*20} {'-'*50}\n"

        for agent in agents:
            agent_name = agent["agent_name"] or agent["agentcard_name"]
            version = agent["version"] or "N/A"
            protocol = agent["protocol"]
            synced = "Yes" if agent["sync_status"] == "True" else "No"
            agent_namespace = agent["namespace"]
            url = agent["url"] or "N/A"

            summary += f"{agent_name:<25} {version:<12} {protocol:<10} {synced:<8} {agent_namespace:<20} {url:<50}\n"

        summary += f"\nTotal: {len(agents)} agent(s)"

        return summary

    except Exception as e:
        raise Exception(f"Error creating agent summary: {e}")


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
    try:
        custom_api = _get_k8s_client()

        # Get the specific AgentCard
        card_cr = custom_api.get_namespaced_custom_object(
            group="agent.kagenti.dev",
            version="v1alpha1",
            namespace=namespace,
            plural="agentcards",
            name=agentcard_name
        )

        card_data = card_cr.get("status", {}).get("card", {})

        if not card_data:
            raise Exception(
                f"AgentCard '{agentcard_name}' has no cached card data. "
                "The agent may not be ready or the sync may have failed."
            )

        result_text = f"Agent details for {agentcard_name}:\n\n"
        result_text += json.dumps(card_data, indent=2)

        return result_text

    except ApiException as e:
        if e.status == 404:
            raise Exception(
                f"AgentCard '{agentcard_name}' not found in namespace '{namespace}'"
            )
        elif e.status == 403:
            raise Exception(
                f"Permission denied to access AgentCard '{agentcard_name}'"
            )
        else:
            raise Exception(f"Kubernetes API error: {e}")
    except Exception as e:
        raise Exception(f"Failed to get AgentCard details: {e}")
