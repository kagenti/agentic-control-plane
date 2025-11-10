"""Test agent filtering logic."""

import pytest
from unittest.mock import patch

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib import discovery


# Sample agent data for testing
SAMPLE_AGENTS = [
    {
        "agentcard_name": "weather-agent-card",
        "namespace": "kagenti",
        "agent_name": "Weather Assistant",
        "description": "Provides weather information",
        "version": "1.0.0",
        "url": "http://weather.example.com",
        "protocol": "a2a",
        "capabilities": {},
        "skills": [
            {"name": "Weather Lookup", "description": "Get weather forecasts"}
        ],
        "supports_authenticated_extended_card": False,
        "sync_status": "True",
        "sync_message": "OK",
        "last_sync_time": "2025-10-29T10:00:00Z"
    },
    {
        "agentcard_name": "database-agent-card",
        "namespace": "kagenti",
        "agent_name": "Database Assistant",
        "description": "Helps with database queries",
        "version": "2.0.0",
        "url": "http://database.example.com",
        "protocol": "a2a",
        "capabilities": {},
        "skills": [
            {"name": "SQL Query", "description": "Execute SQL queries"},
            {"name": "Schema Explorer", "description": "Browse database schema"}
        ],
        "supports_authenticated_extended_card": False,
        "sync_status": "True",
        "sync_message": "OK",
        "last_sync_time": "2025-10-29T10:00:00Z"
    },
    {
        "agentcard_name": "chat-agent-card",
        "namespace": "kagenti",
        "agent_name": "Chat Bot",
        "description": "General conversation agent",
        "version": "1.5.0",
        "url": "http://chat.example.com",
        "protocol": "a2a",
        "capabilities": {},
        "skills": [
            {"name": "Conversation", "description": "Natural language chat"}
        ],
        "supports_authenticated_extended_card": False,
        "sync_status": "True",
        "sync_message": "OK",
        "last_sync_time": "2025-10-29T10:00:00Z"
    }
]


@patch('lib.discovery.get_agents_data')
def test_no_filter_returns_all_agents(mock_get_agents_data):
    """Test that without a filter, all agents are returned."""
    mock_get_agents_data.return_value = (SAMPLE_AGENTS, "namespace: kagenti")

    result = discovery.list_agents(namespace="kagenti")

    # All three agents should appear in the output
    assert "Weather Assistant" in result
    assert "Database Assistant" in result
    assert "Chat Bot" in result
    assert "Total: 3 agent(s)" in result


@patch('lib.discovery.get_agents_data')
def test_filter_returns_only_matches(mock_get_agents_data):
    """Test that filter returns only matching agents."""
    mock_get_agents_data.return_value = (SAMPLE_AGENTS, "namespace: kagenti")

    # Filter for "weather"
    result = discovery.list_agents(namespace="kagenti", filter="weather")

    # Only weather agent should appear
    assert "Weather Assistant" in result
    assert "Database Assistant" not in result
    assert "Chat Bot" not in result
    assert "Total: 1 agent(s)" in result
    assert "Filter: 'weather'" in result


@patch('lib.discovery.get_agents_data')
def test_filter_is_case_insensitive(mock_get_agents_data):
    """Test that filter is case-insensitive."""
    mock_get_agents_data.return_value = (SAMPLE_AGENTS, "namespace: kagenti")

    # Filter with different cases
    result1 = discovery.list_agents(namespace="kagenti", filter="WEATHER")
    result2 = discovery.list_agents(namespace="kagenti", filter="Weather")
    result3 = discovery.list_agents(namespace="kagenti", filter="weather")

    # All should match the weather agent
    assert "Weather Assistant" in result1
    assert "Weather Assistant" in result2
    assert "Weather Assistant" in result3


@patch('lib.discovery.get_agents_data')
def test_filter_searches_agent_name(mock_get_agents_data):
    """Test that filter searches in agent name."""
    mock_get_agents_data.return_value = (SAMPLE_AGENTS, "namespace: kagenti")

    result = discovery.list_agents(namespace="kagenti", filter="database")

    assert "Database Assistant" in result
    assert "Total: 1 agent(s)" in result


@patch('lib.discovery.get_agents_data')
def test_filter_searches_description(mock_get_agents_data):
    """Test that filter searches in description."""
    mock_get_agents_data.return_value = (SAMPLE_AGENTS, "namespace: kagenti")

    result = discovery.list_agents(namespace="kagenti", filter="conversation")

    assert "Chat Bot" in result
    assert "Total: 1 agent(s)" in result


@patch('lib.discovery.get_agents_data')
def test_filter_searches_skill_names(mock_get_agents_data):
    """Test that filter searches in skill names."""
    mock_get_agents_data.return_value = (SAMPLE_AGENTS, "namespace: kagenti")

    result = discovery.list_agents(namespace="kagenti", filter="SQL")

    assert "Database Assistant" in result
    assert "Total: 1 agent(s)" in result


@patch('lib.discovery.get_agents_data')
def test_filter_searches_skill_descriptions(mock_get_agents_data):
    """Test that filter searches in skill descriptions."""
    mock_get_agents_data.return_value = (SAMPLE_AGENTS, "namespace: kagenti")

    result = discovery.list_agents(namespace="kagenti", filter="forecasts")

    assert "Weather Assistant" in result
    assert "Total: 1 agent(s)" in result


@patch('lib.discovery.get_agents_data')
def test_filter_with_no_matches_returns_nothing(mock_get_agents_data):
    """Test that filter with no matches returns appropriate message."""
    mock_get_agents_data.return_value = (SAMPLE_AGENTS, "namespace: kagenti")

    result = discovery.list_agents(namespace="kagenti", filter="nonexistent")

    # Should indicate no matches
    assert "No agents matching filter 'nonexistent'" in result
    assert "Weather Assistant" not in result
    assert "Database Assistant" not in result
    assert "Chat Bot" not in result


@patch('lib.discovery.get_agents_data')
def test_filter_matches_multiple_agents(mock_get_agents_data):
    """Test that filter can match multiple agents."""
    mock_get_agents_data.return_value = (SAMPLE_AGENTS, "namespace: kagenti")

    # "assistant" appears in both Weather Assistant and Database Assistant
    result = discovery.list_agents(namespace="kagenti", filter="assistant")

    assert "Weather Assistant" in result
    assert "Database Assistant" in result
    assert "Chat Bot" not in result
    assert "Total: 2 agent(s)" in result
