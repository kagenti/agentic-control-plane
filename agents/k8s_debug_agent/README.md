Kubernetes Debug Agent
=======================

Overview
--------

This package implements an autonomous “Kubernetes Debug Agent” that speaks the
Autonomous Agent (A2A) protocol. It orchestrates several Autogen agents to plan,
execute, and summarize Kubernetes diagnostic tasks by calling MCP tools exposed
by the `k8s-readonly-server`.

Key Features
------------

- Plan/Act/Reflect loop for gathering Kubernetes state and logs.
- Multiple specialized Autogen agents (planner, step critic, goal judge,
  report writer) coordinated through a shared user proxy.
- Optional MCP toolkit integration for executing real cluster queries.
- Streaming event bridge into the A2A control plane with a logging fallback.

Project Layout
--------------

```
agents/k8s_debug_agent/
├── a2a_agent.py        # A2A server entrypoint and HTTP runtime wiring
├── k8s_debug_agent/
│   ├── main.py         # Core orchestration logic and workflow control
│   ├── agents.py       # Autogen agent definitions and MCP registration
│   ├── config.py       # Pydantic settings model and defaults
│   ├── data_types.py   # Pydantic schemas for structured LLM responses
│   ├── event.py        # Event abstraction plus logging implementation
│   ├── llm.py          # Common LLM configuration helpers
│   ├── prompts.py      # Prompt templates shared across Autogen agents
│   └── …
└── pyproject.toml      # Packaging, dependencies, lint/format configuration
```

Getting Started
---------------

1. **Install dependencies**

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e agents/k8s_debug_agent[dev]
   ```

2. **Configure environment**

   Copy `.env.template` to `.env` and fill in the required values. Important
   variables:

   - `LLM_API_BASE` / `LLM_API_KEY` – endpoint and key for the target OpenAI-compatible API.
   - `TASK_MODEL_ID` – default model used for tool-execution steps (defaults to `granite3.3:8b`).
   - `MCP_URL` – URL to the MCP Kubernetes tool server (e.g. `http://kubernetes-tool:8000`).
   - `SERVICE_PORT` – port the A2A HTTP server listens on (default `8000`).

3. **Run the agent service**

   ```bash
   cd agents/k8s_debug_agent
   python -m a2a_agent
   ```

   The server exposes the A2A HTTP routes and publishes its public agent card
   under `/.well-known/agent.json`.

4. **Exercise the agent**

   ```bash
   cd agents/k8s_debug_agent
   python -m a2a_client
   ```

   The sample client resolves the agent card, sends a Kubernetes diagnostic
   question, and prints the structured response.

Pre-commit Hooks
----------------

The repository ships with Ruff and Black hooks. After installing dependencies,
run `pre-commit install` inside `agents/k8s_debug_agent/` to enforce formatting
on every commit.

Testing & Verification
----------------------

- `python -m compileall k8s_debug_agent` ensures the package is syntax clean.
- Integrate with your preferred test runner once custom tooling or mocks are in
  place for the MCP server.

Operational Notes
-----------------

- The MCP URL must point to a server exposing Kubernetes tooling; see
  `tools/k8s-readonly-server/` for a reference implementation.
