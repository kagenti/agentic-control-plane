#!/usr/bin/env python3
"""
Kubernetes Read-Only MCP Server

Provides read-only introspection tools for Kubernetes resources.
Scoped to specific namespaces via RBAC.
"""

import os
import logging
import sys
from typing import Optional
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from fastmcp import FastMCP

logger = logging.getLogger(__name__)
logging.basicConfig(
    level="DEBUG",
    stream=sys.stdout,
    format="%(levelname)s: %(message)s",
)
# Initialize Kubernetes client
try:
    config.load_incluster_config()
except config.ConfigException:
    config.load_kube_config()

v1 = client.CoreV1Api()
apps_v1 = client.AppsV1Api()

# Create MCP server
mcp = FastMCP("Kubernetes Read-Only")

# Get allowed namespaces from environment
ALLOWED_NAMESPACES = [_.lower() for _ in os.getenv("ALLOWED_NAMESPACES", "default").split(",")]


def validate_namespace(namespace: str) -> None:
    """Validate that namespace is in allowed list."""
    if namespace.lower() not in ALLOWED_NAMESPACES:
        raise ValueError(
            f"Namespace '{namespace}' not allowed. Allowed namespaces: {ALLOWED_NAMESPACES}"
        )


@mcp.tool()
def get_pods(namespace: str, label_selector: Optional[str] = None) -> str:
    """
    List pods in a namespace.

    Args:
        namespace: Kubernetes namespace
        label_selector: Optional label selector (e.g., "app=myapp")

    Returns:
        JSON array of pod information
    """
    validate_namespace(namespace)

    try:
        pods = v1.list_namespaced_pod(
            namespace=namespace, label_selector=label_selector or ""
        )

        pod_list = []
        for pod in pods.items:
            pod_info = {
                "name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "phase": pod.status.phase,
                "node": pod.spec.node_name,
                "containers": [],
                "restart_count": 0,
            }

            # Container info
            if pod.status.container_statuses:
                for container_status in pod.status.container_statuses:
                    pod_info["containers"].append(
                        {
                            "name": container_status.name,
                            "ready": container_status.ready,
                            "restart_count": container_status.restart_count,
                            "state": str(container_status.state),
                        }
                    )
                    pod_info["restart_count"] += container_status.restart_count

            pod_list.append(pod_info)

        return f"Found {len(pod_list)} pod(s) in namespace '{namespace}':\n\n" + str(
            pod_list
        )

    except ApiException as e:
        raise Exception(f"Kubernetes API error: {e.reason}")


@mcp.tool()
def get_pod_logs(
    namespace: str,
    pod_name: str,
    container: Optional[str] = None,
    tail_lines: int = 100,
) -> str:
    """
    Get logs from a pod.

    Args:
        namespace: Kubernetes namespace
        pod_name: Name of the pod
        container: Optional container name (if pod has multiple containers)
        tail_lines: Number of recent lines to return (default: 100)

    Returns:
        Pod logs as text
    """
    validate_namespace(namespace)

    try:
        logs = v1.read_namespaced_pod_log(
            name=pod_name,
            namespace=namespace,
            container=container,
            tail_lines=tail_lines,
        )

        return f"Logs for pod '{pod_name}' in namespace '{namespace}' (last {tail_lines} lines):\n\n{logs}"

    except ApiException as e:
        raise Exception(f"Kubernetes API error: {e.reason}")


@mcp.tool()
def get_events(namespace: str, field_selector: Optional[str] = None) -> str:
    """
    List events in a namespace.

    Args:
        namespace: Kubernetes namespace
        field_selector: Optional field selector (e.g., "involvedObject.name=mypod")

    Returns:
        JSON array of event information
    """
    validate_namespace(namespace)

    try:
        events = v1.list_namespaced_event(
            namespace=namespace, field_selector=field_selector or ""
        )

        event_list = []
        for event in events.items:
            event_info = {
                "type": event.type,
                "reason": event.reason,
                "message": event.message,
                "object": f"{event.involved_object.kind}/{event.involved_object.name}",
                "count": event.count,
                "first_timestamp": str(event.first_timestamp),
                "last_timestamp": str(event.last_timestamp),
            }
            event_list.append(event_info)

        return (
            f"Found {len(event_list)} event(s) in namespace '{namespace}':\n\n"
            + str(event_list)
        )

    except ApiException as e:
        raise Exception(f"Kubernetes API error: {e.reason}")


@mcp.tool()
def get_deployments(namespace: str) -> str:
    """
    List deployments in a namespace.

    Args:
        namespace: Kubernetes namespace

    Returns:
        JSON array of deployment information
    """
    validate_namespace(namespace)

    try:
        deployments = apps_v1.list_namespaced_deployment(namespace=namespace)

        deployment_list = []
        for deploy in deployments.items:
            deployment_info = {
                "name": deploy.metadata.name,
                "namespace": deploy.metadata.namespace,
                "replicas": deploy.spec.replicas,
                "ready_replicas": deploy.status.ready_replicas or 0,
                "available_replicas": deploy.status.available_replicas or 0,
                "conditions": [],
            }

            if deploy.status.conditions:
                for condition in deploy.status.conditions:
                    deployment_info["conditions"].append(
                        {
                            "type": condition.type,
                            "status": condition.status,
                            "reason": condition.reason,
                            "message": condition.message,
                        }
                    )

            deployment_list.append(deployment_info)

        return (
            f"Found {len(deployment_list)} deployment(s) in namespace '{namespace}':\n\n"
            + str(deployment_list)
        )

    except ApiException as e:
        raise Exception(f"Kubernetes API error: {e.reason}")


@mcp.tool()
def get_services(namespace: str) -> str:
    """
    List services in a namespace.

    Args:
        namespace: Kubernetes namespace

    Returns:
        JSON array of service information
    """
    validate_namespace(namespace)

    try:
        services = v1.list_namespaced_service(namespace=namespace)

        service_list = []
        for svc in services.items:
            service_info = {
                "name": svc.metadata.name,
                "namespace": svc.metadata.namespace,
                "type": svc.spec.type,
                "cluster_ip": svc.spec.cluster_ip,
                "ports": [],
            }

            if svc.spec.ports:
                for port in svc.spec.ports:
                    service_info["ports"].append(
                        {
                            "name": port.name,
                            "port": port.port,
                            "target_port": str(port.target_port),
                            "protocol": port.protocol,
                        }
                    )

            service_list.append(service_info)

        return (
            f"Found {len(service_list)} service(s) in namespace '{namespace}':\n\n"
            + str(service_list)
        )

    except ApiException as e:
        raise Exception(f"Kubernetes API error: {e.reason}")


@mcp.tool()
def describe_pod(namespace: str, pod_name: str) -> str:
    """
    Get detailed information about a specific pod.

    Args:
        namespace: Kubernetes namespace
        pod_name: Name of the pod

    Returns:
        Detailed pod information
    """
    validate_namespace(namespace)

    try:
        pod = v1.read_namespaced_pod(name=pod_name, namespace=namespace)

        if not pod:
            return f"No pod {pod_name} found in namespace {namespace}"

        pod_info = {
            "name": pod.metadata.name,
            "namespace": pod.metadata.namespace,
            "labels": pod.metadata.labels,
            "phase": pod.status.phase,
            "node": pod.spec.node_name,
            "pod_ip": pod.status.pod_ip,
            "start_time": str(pod.status.start_time),
            "conditions": [],
            "containers": [],
        }

        # Conditions
        if pod.status.conditions:
            for condition in pod.status.conditions:
                pod_info["conditions"].append(
                    {
                        "type": condition.type,
                        "status": condition.status,
                        "reason": condition.reason,
                        "message": condition.message,
                    }
                )

        # Container details
        if pod.status.container_statuses:
            for container_status in pod.status.container_statuses:
                container_info = {
                    "name": container_status.name,
                    "ready": container_status.ready,
                    "restart_count": container_status.restart_count,
                    "image": container_status.image,
                    "state": str(container_status.state),
                }
                pod_info["containers"].append(container_info)

        return f"Detailed information for pod '{pod_name}':\n\n" + str(pod_info)

    except ApiException as e:
        raise Exception(f"Kubernetes API error: {e.reason}")


def main():
    """Run the MCP server."""
    port = os.getenv("MCP_SERVER_PORT")
    if port:
        # Run as HTTP server for Kubernetes (use modern HTTP transport)
        import uvicorn

        # Use modern http_app instead of deprecated sse_app
        app = mcp.http_app()

        uvicorn.run(app, host="0.0.0.0", port=int(port))
    else:
        # Run in STDIO mode for local testing
        mcp.run()


if __name__ == "__main__":
    main()
