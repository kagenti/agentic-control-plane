"""
OpenTelemetry observability setup for K8s Debug Agent.

This module provides:
- Auto-instrumentation with OTEL GenAI semantic conventions (gen_ai.*)
- OpenInferenceSpanProcessor for Phoenix compatibility
- Cross-agent trace propagation via W3C Trace Context + Baggage

Key Features:
- `setup_observability`: Configure OTEL with GenAI instrumentation
- `create_agent_span`: Create a root AGENT span for the conversation
- `trace_context_from_headers`: Extract/propagate traceparent across agents
- Auto-instrumentation of OpenAI SDK with gen_ai.* attributes

Usage:
    from k8s_debug_agent.observability import (
        setup_observability,
        create_agent_span,
        trace_context_from_headers,
    )

    # At agent startup (BEFORE importing openai/autogen)
    setup_observability()

    # In request handler - wrap execution with context
    with trace_context_from_headers(headers):
        with create_agent_span("agent_task", task_id="task-456") as span:
            result = await agent.execute(messages)
"""

import logging
import os
from typing import Dict, Any, Optional
from contextlib import contextmanager
from opentelemetry import trace, baggage, context
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.trace import Status, StatusCode
from opentelemetry.propagate import set_global_textmap, extract, inject
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.baggage.propagation import W3CBaggagePropagator

logger = logging.getLogger(__name__)

# Tracer name for manual spans
TRACER_NAME = "k8s-debug-agent"


def _get_otlp_exporter(endpoint: str, protocol: str):
    """
    Get the appropriate OTLP exporter based on protocol.

    Args:
        endpoint: OTLP endpoint URL
        protocol: Protocol to use ('grpc' or 'http/protobuf')

    Returns:
        Configured OTLP span exporter
    """
    if protocol.lower() == "grpc":
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter as GrpcExporter,
        )
        # For gRPC, endpoint should not have http:// prefix
        grpc_endpoint = endpoint.replace("http://", "").replace("https://", "")
        return GrpcExporter(endpoint=grpc_endpoint, insecure=True)
    else:
        # Default to HTTP/protobuf
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter as HttpExporter,
        )
        # Ensure endpoint has /v1/traces path for HTTP
        if not endpoint.endswith("/v1/traces"):
            endpoint = endpoint.rstrip("/") + "/v1/traces"
        return HttpExporter(endpoint=endpoint)


class ObservabilityConfig:
    """
    Configuration for observability setup.

    Reads from environment variables with sensible defaults.
    """

    def __init__(self):
        # Service identification
        self.service_name = os.getenv("OTEL_SERVICE_NAME", "k8s-debug-agent")
        self.namespace = os.getenv("K8S_NAMESPACE_NAME", "kagenti-agents")
        self.deployment_env = os.getenv("DEPLOYMENT_ENVIRONMENT", "kind-local")

        # Phoenix project routing
        self.phoenix_project = os.getenv(
            "PHOENIX_PROJECT_NAME",
            f"{self.namespace}-agents"
        )

        # OTLP endpoint and protocol
        self.otlp_endpoint = os.getenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "http://otel-collector.kagenti-system.svc.cluster.local:4318"
        )
        self.otlp_protocol = os.getenv(
            "OTEL_EXPORTER_OTLP_PROTOCOL",
            "http/protobuf"
        )

        # Additional resource attributes
        self.extra_resource_attrs = self._parse_resource_attrs()

    def _parse_resource_attrs(self) -> Dict[str, str]:
        """Parse OTEL_RESOURCE_ATTRIBUTES environment variable."""
        attrs = {}
        resource_attrs_str = os.getenv("OTEL_RESOURCE_ATTRIBUTES", "")

        if resource_attrs_str:
            for pair in resource_attrs_str.split(","):
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    attrs[key.strip()] = value.strip()

        return attrs

    def get_resource_attributes(self) -> Dict[str, str]:
        """Get complete set of resource attributes for OTEL tracer."""
        attrs = {
            "service.name": self.service_name,
            "service.namespace": self.namespace,
            "k8s.namespace.name": self.namespace,
            "phoenix.project.name": self.phoenix_project,
            "deployment.environment": self.deployment_env,
        }
        attrs.update(self.extra_resource_attrs)
        return attrs


def setup_observability(config: Optional[ObservabilityConfig] = None) -> TracerProvider:
    """
    Set up OpenTelemetry tracing with OTEL GenAI instrumentation.

    This function:
    1. Creates OTEL tracer provider with proper resource attributes
    2. Adds OpenInferenceSpanProcessor for Phoenix compatibility
    3. Configures OTLP exporter (HTTP or gRPC)
    4. Instruments OpenAI SDK with OTEL GenAI semantic conventions

    IMPORTANT: Call this BEFORE importing openai or autogen to ensure
    proper instrumentation.

    Args:
        config: Optional ObservabilityConfig. If not provided, creates default.

    Returns:
        Configured TracerProvider (can be passed to AutoGen runtime)
    """
    if config is None:
        config = ObservabilityConfig()

    logger.info("=" * 70)
    logger.info("Setting up OpenTelemetry observability (OTEL GenAI)")
    logger.info("-" * 70)
    logger.info(f"Service Name:      {config.service_name}")
    logger.info(f"Namespace:         {config.namespace}")
    logger.info(f"Phoenix Project:   {config.phoenix_project}")
    logger.info(f"OTLP Endpoint:     {config.otlp_endpoint}")
    logger.info(f"OTLP Protocol:     {config.otlp_protocol}")
    logger.info("=" * 70)

    # Create resource with all attributes
    resource = Resource(attributes=config.get_resource_attributes())

    # Create tracer provider
    tracer_provider = TracerProvider(resource=resource)

    # Add OpenInferenceSpanProcessor FIRST
    # This converts gen_ai.* attributes to OpenInference format for Phoenix
    try:
        from openinference.instrumentation.openllmetry import OpenInferenceSpanProcessor
        tracer_provider.add_span_processor(OpenInferenceSpanProcessor())
        logger.info("OpenInferenceSpanProcessor added for Phoenix compatibility")
    except ImportError:
        logger.warning("openinference-instrumentation-openllmetry not installed, skipping Phoenix conversion")

    # Add OTLP exporter
    otlp_exporter = _get_otlp_exporter(config.otlp_endpoint, config.otlp_protocol)
    tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    # Set global tracer provider
    trace.set_tracer_provider(tracer_provider)

    # Auto-instrument OpenAI with OTEL GenAI semantic conventions
    # This creates spans with gen_ai.* attributes that Phoenix can understand via the SpanProcessor
    try:
        from opentelemetry.instrumentation.openai import OpenAIInstrumentor
        OpenAIInstrumentor().instrument(tracer_provider=tracer_provider)
        logger.info("OpenAI SDK instrumented with OTEL GenAI semantic conventions")
    except ImportError:
        logger.warning("opentelemetry-instrumentation-openai-v2 not installed, skipping OpenAI instrumentation")

    # Configure W3C Trace Context and Baggage propagators for distributed tracing
    set_global_textmap(CompositePropagator([
        TraceContextTextMapPropagator(),
        W3CBaggagePropagator(),
    ]))

    logger.info("W3C Trace Context and Baggage propagators configured")
    logger.info("Traces will route to Phoenix project: %s", config.phoenix_project)

    return tracer_provider


# Global tracer for creating manual spans
_tracer: Optional[trace.Tracer] = None


def get_tracer() -> trace.Tracer:
    """Get the global tracer for creating manual spans."""
    global _tracer
    if _tracer is None:
        _tracer = trace.get_tracer(TRACER_NAME)
    return _tracer


@contextmanager
def create_agent_span(
    name: str = "agent_task",
    task_id: Optional[str] = None,
    context_id: Optional[str] = None,
    user_id: Optional[str] = None,
    input_text: Optional[str] = None,
):
    """
    Create a root AGENT span for the conversation.

    This span serves as the root for all OpenAI auto-instrumented spans,
    providing a clear entry point for each agent interaction.

    Args:
        name: Span name (default: "agent_task")
        task_id: A2A task ID for filtering conversations
        context_id: A2A context ID (conversation session)
        user_id: User identifier
        input_text: The user's input message

    Yields:
        The created span
    """
    tracer = get_tracer()

    # Build attributes using OTEL GenAI semantic conventions
    attributes = {
        "gen_ai.operation.name": "agent",
    }

    # Add A2A task/context IDs as custom attributes for filtering
    if task_id:
        attributes["a2a.task_id"] = task_id
    if context_id:
        attributes["a2a.context_id"] = context_id
    if user_id:
        attributes["user.id"] = user_id
    if input_text:
        attributes["gen_ai.prompt"] = input_text

    with tracer.start_as_current_span(name, attributes=attributes) as span:
        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            raise


def extract_trace_context(headers: Dict[str, str]) -> context.Context:
    """Extract trace context from HTTP headers."""
    return extract(headers)


def inject_trace_context(headers: Dict[str, str]) -> Dict[str, str]:
    """Inject current trace context into HTTP headers."""
    inject(headers)
    return headers


@contextmanager
def trace_context_from_headers(headers: Dict[str, str]):
    """
    Context manager that activates trace context from HTTP headers.

    Use this to wrap request handling code so that all spans created
    within the context become children of the incoming trace.
    """
    ctx = extract(headers)
    token = context.attach(ctx)
    try:
        yield ctx
    finally:
        context.detach(token)


def set_baggage_context(context_data: Dict[str, Any]) -> context.Context:
    """
    Set OTEL baggage for context propagation across services.

    Args:
        context_data: Dict with keys like user_id, request_id, tenant_id

    Returns:
        Updated context with baggage
    """
    ctx = context.get_current()

    for key, value in context_data.items():
        if value is not None:
            ctx = baggage.set_baggage(key, str(value), context=ctx)
            logger.debug(f"Set baggage: {key}={value}")

    context.attach(ctx)
    return ctx


def extract_baggage_from_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """
    Extract baggage context from HTTP headers.

    Common headers to extract:
    - user-id, x-user-id
    - request-id, x-request-id
    - conversation-id, x-conversation-id
    """
    baggage_data = {}
    headers_lower = {k.lower(): v for k, v in headers.items()}

    header_mappings = {
        "user-id": "user_id",
        "x-user-id": "user_id",
        "request-id": "request_id",
        "x-request-id": "request_id",
        "conversation-id": "conversation_id",
        "x-conversation-id": "conversation_id",
        "tenant-id": "tenant_id",
        "x-tenant-id": "tenant_id",
    }

    for header_name, baggage_key in header_mappings.items():
        if header_name in headers_lower:
            baggage_data[baggage_key] = headers_lower[header_name]

    logger.debug(f"Extracted baggage from headers: {baggage_data}")
    return baggage_data
