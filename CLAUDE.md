# agentic-control-plane

## Overview

A multi-agent demo showcasing AI agents as first-class Kubernetes citizens that collaborate to manage, monitor, and troubleshoot cluster workloads. Agents communicate via the A2A protocol, are discovered through AgentCard CRDs, and are bridged to supervisors via MCP.

## Repository Structure

```
agentic-control-plane/
├── agents/
│   ├── k8s_debug_agent/        # AG2-based K8s debugging agent (A2A)
│   └── source_code_analyzer/   # AG2-based source code analysis agent (A2A)
├── tools/
│   ├── a2a_bridge_server/      # MCP-to-A2A bridge (agent discovery + invocation)
│   └── k8s_readonly_server/    # K8s read-only MCP tool server
└── deploy/                     # Kubernetes manifests (kustomize)
```

## Key Commands

| Task | Command |
|------|---------|
| Lint | `make lint` |
| Format | `make fmt` |
| Install pre-commit | `pre-commit install` |
| Run agent (k8s-debug) | `cd agents/k8s_debug_agent && uv run python a2a_agent.py` |
| Run agent (src-analyzer) | `cd agents/source_code_analyzer && uv run python a2a_agent.py` |
| Run bridge | `cd tools/a2a_bridge_server && uv run python server.py` |
| Deploy to K8s | `kubectl apply -k deploy/<component>/` |

## Code Style

- Python 3.10+, `uv` package manager
- `ruff` for linting and formatting (line-length: 100)
- Pre-commit hooks: `pre-commit install`
- DCO sign-off required: `git commit -s`

## Protocols

- **A2A**: Agent-to-Agent (Google) — agents expose `/.well-known/agent.json`
- **MCP**: Model Context Protocol — bridge translates MCP ↔ A2A
- **AgentCard CRD**: Kubernetes CR caching agent capabilities for discovery

## Architecture

The supervisor (Claude Code or in-cluster agent) discovers running agents via the A2A bridge, which reads AgentCard CRDs created by the kagenti-operator. Agents expose skills that the supervisor delegates to for K8s operations and code analysis.
