# Kubernetes Read-Only MCP Server

A Model Context Protocol (MCP) server providing read-only introspection of Kubernetes resources.

## Features

Tools provided:
- `get_pods` - List pods in a namespace
- `get_pod_logs` - Get logs from a specific pod
- `get_events` - List events in a namespace
- `get_deployments` - List deployments
- `get_services` - List services
- `describe_pod` - Get detailed information about a pod

## Security

- Read-only access enforced by RBAC
- Namespace-scoped via ALLOWED_NAMESPACES environment variable
- Runs as non-root user

## Building

```bash
docker build -t ghcr.io/kagenti/k8s-readonly-mcp-server:latest .
docker push ghcr.io/kagenti/k8s-readonly-mcp-server:latest
```

## Configuration

Environment variables:
- `MCP_SERVER_PORT` - Port to listen on (default: 8080)
- `ALLOWED_NAMESPACES` - Comma-separated list of allowed namespaces (default: "default")

## Deployment

See `../../deployments/01-k8s-readonly-server/` for Kubernetes manifests.
