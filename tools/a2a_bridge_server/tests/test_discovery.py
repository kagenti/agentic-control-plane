"""Tests for agent discovery logic (namespace scope and data parsing)."""

from unittest.mock import patch

from lib import discovery

# ---------------------------------------------------------------------------
# get_namespace_scope
# ---------------------------------------------------------------------------


def test_namespace_scope_defaults_to_default():
    ns, msg = discovery.get_namespace_scope()
    assert ns == "default"
    assert msg == "namespace: default"


def test_namespace_scope_specific_namespace():
    ns, msg = discovery.get_namespace_scope(namespace="kagenti-system")
    assert ns == "kagenti-system"
    assert msg == "namespace: kagenti-system"


def test_namespace_scope_all_namespaces():
    ns, msg = discovery.get_namespace_scope(all_namespaces=True)
    assert ns is None
    assert msg == "all namespaces"


def test_namespace_scope_all_namespaces_overrides_explicit():
    # all_namespaces takes precedence when both are provided
    ns, msg = discovery.get_namespace_scope(namespace="kagenti-system", all_namespaces=True)
    assert ns is None
    assert msg == "all namespaces"


# ---------------------------------------------------------------------------
# get_agents_data — AgentCard CR parsing
# ---------------------------------------------------------------------------

SAMPLE_CARD_CR = {
    "metadata": {"name": "k8s-debug-card", "namespace": "kagenti-system"},
    "status": {
        "card": {
            "name": "K8s Debug Agent",
            "description": "Kubernetes debugging agent",
            "version": "1.0.0",
            "url": "http://k8s-debug.kagenti-system.svc",
            "capabilities": {"streaming": True},
            "skills": [
                {"name": "get_pod_logs", "description": "Fetch pod logs"},
            ],
            "supportsAuthenticatedExtendedCard": True,
        },
        "conditions": [
            {"type": "Synced", "status": "True", "message": "OK"},
        ],
        "lastSyncTime": "2025-10-29T10:00:00Z",
        "protocol": "a2a",
    },
}


@patch("lib.discovery.discover_agent_cards")
def test_get_agents_data_parses_card_fields(mock_discover):
    mock_discover.return_value = [SAMPLE_CARD_CR]

    agents, _ = discovery.get_agents_data(namespace="kagenti-system")

    assert len(agents) == 1
    agent = agents[0]
    assert agent["agentcard_name"] == "k8s-debug-card"
    assert agent["namespace"] == "kagenti-system"
    assert agent["agent_name"] == "K8s Debug Agent"
    assert agent["description"] == "Kubernetes debugging agent"
    assert agent["version"] == "1.0.0"
    assert agent["url"] == "http://k8s-debug.kagenti-system.svc"
    assert agent["protocol"] == "a2a"
    assert agent["sync_status"] == "True"
    assert agent["sync_message"] == "OK"
    assert agent["last_sync_time"] == "2025-10-29T10:00:00Z"
    assert agent["supports_authenticated_extended_card"] is True
    assert len(agent["skills"]) == 1


@patch("lib.discovery.discover_agent_cards")
def test_get_agents_data_empty_returns_empty_list(mock_discover):
    mock_discover.return_value = []

    agents, scope_msg = discovery.get_agents_data(namespace="kagenti-system")

    assert agents == []
    assert scope_msg == "namespace: kagenti-system"


@patch("lib.discovery.discover_agent_cards")
def test_get_agents_data_missing_sync_condition(mock_discover):
    """Cards without a Synced condition should not crash."""
    cr = {
        "metadata": {"name": "partial-card", "namespace": "default"},
        "status": {
            "card": {"name": "Partial Agent"},
            "conditions": [],
            "protocol": "a2a",
        },
    }
    mock_discover.return_value = [cr]

    agents, _ = discovery.get_agents_data()

    assert len(agents) == 1
    assert agents[0]["sync_status"] == "Unknown"
    assert agents[0]["sync_message"] == ""


# ---------------------------------------------------------------------------
# discover_agents — formatted output
# ---------------------------------------------------------------------------


@patch("lib.discovery.get_agents_data")
def test_discover_agents_empty(mock_get_data):
    mock_get_data.return_value = ([], "namespace: default")

    result = discovery.discover_agents()

    assert "No agents found" in result
    assert "Kagenti operator" in result


@patch("lib.discovery.get_agents_data")
def test_discover_agents_returns_json(mock_get_data):
    mock_get_data.return_value = (
        [{"agent_name": "Test Agent", "url": "http://test"}],
        "namespace: default",
    )

    result = discovery.discover_agents()

    assert "Found 1 agent(s)" in result
    assert "Test Agent" in result
