# A2A Kubernetes Control Plane Demo

A multi-agent demonstration showcasing AI agents as first-class Kubernetes citizens that collaborate to manage, monitor, and troubleshoot cluster workloads.

## Vision

Transform Kubernetes operations from manual troubleshooting into collaborative agent workflows. Instead of running kubectl commands and reading logs yourself, delegate to specialized agents that can discover problems, analyze source code, correlate errors, and propose solutions autonomously.

## The Demo

Jane is experimenting with Kagenti as a potential agent management platform. She notices that a pod is periodically crashing, causing delays due to frequent restarts. Jane opens Claude Code and asks for help troubleshooting the cluster.

**What happens:**

1. Claude discovers running agents in the `kagenti-system-agent-team` namespace that expose skills related to monitoring and debugging
2. Claude delegates to the `k8s-monitoring-agent` to fetch logs and sees stack traces referencing a particular class in Kagenti's codebase
3. Claude sees that a `source-code-specialist-agent` exists, so it forwards the stack trace and asks about the area of the codebase where it originated
4. Using the codebase analysis, Claude generates a hypothesis about where the problem originates and proposes solutions

**The magic:** All of this happens through agent-to-agent communication using the A2A protocol, with agents discovering and invoking each other's skills dynamically.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│       Supervisor (Claude Code/IDE or in-cluster Agent)       │
│  • Orchestrates workflow                                     │
│  • Has access to local files and git                         │
│  • Discovers cluster agents via MCP                          │
└────────────────┬─────────────────────────────────────────────┘
                 │
                 │ MCP Protocol
                 │
┌────────────────▼─────────────────────────────────────────────┐
│           A2A-to-MCP Bridge                                  │
│                                                              │
│  • Discovers agents via AgentCard CRDs                       │
│  • Translates MCP <-> A2A protocols                          │
│  • Can run locally OR as agent in cluster                    │
└────────────────┬─────────────────────────────────────────────┘
                 │
                 │ Kubernetes API (read AgentCards)
                 │
┌────────────────▼─────────────────────────────────────────────┐
│              Kubernetes Cluster                              │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │         AgentCard Controller                           │  │
│  │   (kagenti-operator/agentcard_controller.go)           │  │
│  │  • Watches Agent Pods with appropriate labels          │  │
│  │  • Periodically fetches /.well-known/agent.json        │  │
│  │  • Caches agent capabilities in AgentCard CRs          │  │
│  │  • Makes agents discoverable cluster-wide              │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  Namespace: kagenti-system-agent-team                        │
│  ┌──────────────────┐  ┌──────────────────┐                  │
│  │ k8s-monitoring   │  │ source-code      │                  │
│  │ Agent Pod        │  │ Agent Pod        │  ...             │
│  │                  │  │                  │                  │
│  │ Skills:          │  │ Skills:          │                  │
│  │ • get_pod_logs   │  │ • search_repo    │                  │
│  │ • get_events     │  │ • analyze_trace  │                  │
│  │ • get_metrics    │  │ • git_blame      │                  │
│  └──────────────────┘  └──────────────────┘                  │
│         ▲                      ▲                             │
│         │                      │                             │
│  ┌──────┴──────────────────────┴───────────────────────────┐ │
│  │           AgentCard CRs (created by controller)         │ │
│  │  • k8s-monitoring-agent.kagenti-system                  │ │
│  │  • source-code-agent.kagenti-system                     │ │
│  │  (contain cached agent capabilities)                    │ │
│  └─────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────┘
```

## Building Blocks

### 1. AgentCard CRD (IMPLEMENTED ✓)

**Location:** [Here](https://github.com/usize/kagenti-operator/blob/0c3d8b5641bab7ee9b65419338b1abfccb5d3e45/kagenti-operator/api/v1alpha1/agentcard_types.go)

**What it does:**
- Defines a Kubernetes CR that caches an agent's capabilities
- Syncs from agent's `/.well-known/agent.json` endpoint
- Stores A2A-compliant agent cards in cluster
- Makes agents discoverable via kubectl/API

**Status:** Core CRD and controllers implemented with tests

### 2. A2A <-> Kagenti Bridge (REFERENCE)

[reference implementation](https://github.com/redhat-et/agent-orchestration/blob/main/mcp/oc_agent_bridge.py)

**What it provides:**
- Discovers agents via AgentCard CRD 
- Allows invocation of discovered agents

**What it enables:**
- A supervisor can discover and use agents in a cluster to solve problems.

### 3. Control Plane Agents

**What they provide:**
- Each agent exposes some skills, and has access to tools, which enable some aspect of cluster management: reading logs, listing crds, etc...
- Together with a `supervisor` or the `A2A <-> Kagenti Bridge` they act as a unified control plane.

## Key Design Decisions


### Why MCP bridge instead of direct A2A implementation?

- **Discovery abstraction:** MCP tools model maps cleanly to agent skills
- **Deployment flexibility:** Bridge can run locally or in-cluster
- **Future-proof:** Can swap out supervisor without changing agents

### Why specialist agents instead of one big agent?

- **Scalability:** Different agents can run on different nodes
- **Separation of concerns:** Clear skill boundaries
- **Context Hygiene:** Federating tools across agents reduces context pollution
- **Reusability:** Same monitoring agent works for multiple use cases
- **Security:** Can grant minimal RBAC per agent role

## Success Criteria

The demo is successful when:

1. Jane can ask the Supervisor: "Why is my pod crashing?"
2. Supervisor automatically discovers k8s-monitoring-agent and source-code-agent
3. Supervisor fetches logs from monitoring agent
4. Supervisor asks source-code agent to analyze the stacktrace
5. Supervisor synthesizes findings and proposes a fix
6. All of this happens through A2A agent collaboration, visible to the user

## Contributing

This is a proof-of-concept demo. To contribute:

1. Check/file issues to discuss approach before major work
2. Test against real Kagenti deployments
3. Document your specialist agent's skills clearly in a directory scoped README.md

Thank you for your contributions!!
