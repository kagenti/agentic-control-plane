# Kubernetes Read-Only MCP Server Deployment

This directory contains Kubernetes manifests for deploying the k8s-readonly-server MCP tool.

## Current Approach

This deployment uses a **ServiceAccount with ClusterRole RBAC** for Kubernetes API access.

## Future Enhancement

In a future iteration, we plan to support **JWT token delegation** where:
- Agents pass their own Kubernetes service account tokens to the MCP server
- The server uses the caller's identity for API requests
- No static ServiceAccount needed - better security and audit trails

For now, the server uses a shared read-only ServiceAccount with cluster-wide permissions.

## Deployment

```bash
# Deploy to cluster
kubectl apply -k deploy/k8s-readonly-server/

# Verify
kubectl get deployment k8s-readonly-server -n kagenti-agents
kubectl get pods -n kagenti-agents -l app=k8s-readonly-server
kubectl logs -n kagenti-agents -l app=k8s-readonly-server
```

## RBAC Permissions

The server has cluster-wide read-only access to:
- `pods`, `pods/log` (CoreV1)
- `events` (CoreV1)
- `services` (CoreV1)
- `deployments` (apps/v1)

## Testing

Test the MCP server using MCP Inspector or curl:

```bash
# Port forward
kubectl port-forward -n kagenti-agents deployment/k8s-readonly-server 8080:8080

# Test with curl
curl http://localhost:8080/health
```
