"""
OpenTelemetry and OpenInference observability setup for K8s Debug Agent.

This module provides:
- Auto-instrumentation with OpenInference semantic conventions
- OpenInference context managers for session/user tracking
- Phoenix project routing via resource attributes
- Cross-agent trace propagation via W3C Trace Context

Key Features:
- `using_attributes`: Add session_id, user_id, metadata to all spans in scope
- `create_agent_span`: Create a root AGENT span for the conversation
- `trace_context_from_headers`: Extract/propagate traceparent across agents
- Auto-instrumentation of OpenAI SDK (used by AutoGen)

Usage:
    from k8s_debug_agent.observability import (
        setup_observability,
        create_agent_span,
        trace_context_from_headers,
    )
    from openinference.instrumentation import using_attributes

    # At agent startup
    setup_observability()

    # In request handler - wrap execution with context
    with trace_context_from_headers(headers):
        with using_attributes(
            session_id="context-123",
            user_id="alice",
            metadata={"task_id": "task-456"},
        ):
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
# IMPORTANT: Do NOT import instrumentors at module level!
# They internally import openai/autogen, which defeats the purpose of early instrumentation.
# Instead, import them lazily inside setup_observability().
from openinference.semconv.trace import SpanAttributes, OpenInferenceSpanKindValues

logger = logging.getLogger(__name__)


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


def _patch_autogen_async_methods() -> None:
    """
    Patch AutoGen's async methods to propagate OpenTelemetry trace context.

    The openinference-instrumentation-autogen package only patches synchronous methods.
    This patches the async counterparts to ensure LLM spans are properly nested.

    Additionally patches the OpenAI client create method to restore context.
    """
    import sys
    print("DEBUG: _patch_autogen_async_methods() CALLED", file=sys.stderr, flush=True)

    import asyncio
    from functools import wraps
    from autogen import ConversableAgent

    tracer = trace.get_tracer(TRACER_NAME)

    # Store original methods
    original_a_initiate_chat = ConversableAgent.a_initiate_chat
    original_a_generate_reply = ConversableAgent.a_generate_reply

    # Patch BOTH sync and async OpenAI Completions.create with manual span creation
    # We do this instead of using OpenAIInstrumentor because it doesn't
    # properly propagate async context through AutoGen.
    try:
        from openai.resources.chat.completions import Completions, AsyncCompletions
        import json

        original_sync_create = Completions.create
        original_async_create = AsyncCompletions.create

        def _serialize_messages(messages: list) -> str:
            """Serialize messages list to JSON for span attributes."""
            try:
                return json.dumps([
                    {"role": m.get("role", ""), "content": m.get("content", "")}
                    for m in messages
                ])
            except Exception:
                return str(messages)

        def _extract_output(result) -> str:
            """Extract output text from OpenAI ChatCompletion response."""
            try:
                if hasattr(result, 'choices') and result.choices:
                    choice = result.choices[0]
                    if hasattr(choice, 'message') and choice.message:
                        return choice.message.content or ""
                return ""
            except Exception:
                return ""

        def _set_llm_span_attributes(span, kwargs, result):
            """Set OpenInference LLM span attributes for input, output, and tokens."""
            try:
                # Input messages
                messages = kwargs.get('messages', [])
                if messages:
                    span.set_attribute(SpanAttributes.INPUT_VALUE, _serialize_messages(messages))
                    # Set individual message attributes per OpenInference spec
                    for i, msg in enumerate(messages):
                        span.set_attribute(f"llm.input_messages.{i}.message.role", msg.get("role", ""))
                        span.set_attribute(f"llm.input_messages.{i}.message.content", msg.get("content", ""))

                # Output
                output_text = _extract_output(result)
                if output_text:
                    span.set_attribute(SpanAttributes.OUTPUT_VALUE, output_text)
                    # Set output message attributes per OpenInference spec
                    if hasattr(result, 'choices') and result.choices:
                        choice = result.choices[0]
                        if hasattr(choice, 'message') and choice.message:
                            span.set_attribute("llm.output_messages.0.message.role", choice.message.role or "assistant")
                            span.set_attribute("llm.output_messages.0.message.content", output_text)

                # Token usage
                if hasattr(result, 'usage') and result.usage:
                    usage = result.usage
                    if hasattr(usage, 'prompt_tokens') and usage.prompt_tokens:
                        span.set_attribute(SpanAttributes.LLM_TOKEN_COUNT_PROMPT, usage.prompt_tokens)
                    if hasattr(usage, 'completion_tokens') and usage.completion_tokens:
                        span.set_attribute(SpanAttributes.LLM_TOKEN_COUNT_COMPLETION, usage.completion_tokens)
                    if hasattr(usage, 'total_tokens') and usage.total_tokens:
                        span.set_attribute(SpanAttributes.LLM_TOKEN_COUNT_TOTAL, usage.total_tokens)

                # Invocation parameters (temperature, max_tokens, etc.)
                invocation_params = {}
                for param in ['temperature', 'max_tokens', 'top_p', 'frequency_penalty', 'presence_penalty']:
                    if param in kwargs:
                        invocation_params[param] = kwargs[param]
                if invocation_params:
                    span.set_attribute(SpanAttributes.LLM_INVOCATION_PARAMETERS, json.dumps(invocation_params))

            except Exception as e:
                logger.debug(f"Failed to set LLM span attributes: {e}")

        @wraps(original_sync_create)
        def patched_sync_create(self, *args, **kwargs):
            """Wrap sync OpenAI create with manual LLM span using parent context."""
            parent_ctx = get_global_parent_context()
            print(f"DEBUG patched_SYNC_create: parent_ctx={parent_ctx is not None}", file=sys.stderr, flush=True)

            model = kwargs.get('model', 'unknown')

            if parent_ctx is not None:
                token = context.attach(parent_ctx)
                try:
                    with tracer.start_as_current_span(
                        "ChatCompletion",
                        attributes={
                            SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.LLM.value,
                            SpanAttributes.LLM_MODEL_NAME: model,
                        },
                    ) as span:
                        try:
                            result = original_sync_create(self, *args, **kwargs)
                            _set_llm_span_attributes(span, kwargs, result)
                            span.set_status(Status(StatusCode.OK))
                            return result
                        except Exception as e:
                            span.set_status(Status(StatusCode.ERROR, str(e)))
                            span.record_exception(e)
                            raise
                finally:
                    context.detach(token)
            else:
                return original_sync_create(self, *args, **kwargs)

        @wraps(original_async_create)
        async def patched_async_create(self, *args, **kwargs):
            """Wrap async OpenAI create with manual LLM span using parent context."""
            parent_ctx = get_global_parent_context()
            print(f"DEBUG patched_ASYNC_create: parent_ctx={parent_ctx is not None}", file=sys.stderr, flush=True)

            model = kwargs.get('model', 'unknown')

            if parent_ctx is not None:
                token = context.attach(parent_ctx)
                try:
                    with tracer.start_as_current_span(
                        "ChatCompletion",
                        attributes={
                            SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.LLM.value,
                            SpanAttributes.LLM_MODEL_NAME: model,
                        },
                    ) as span:
                        try:
                            result = await original_async_create(self, *args, **kwargs)
                            _set_llm_span_attributes(span, kwargs, result)
                            span.set_status(Status(StatusCode.OK))
                            return result
                        except Exception as e:
                            span.set_status(Status(StatusCode.ERROR, str(e)))
                            span.record_exception(e)
                            raise
                finally:
                    context.detach(token)
            else:
                return await original_async_create(self, *args, **kwargs)

        Completions.create = patched_sync_create
        AsyncCompletions.create = patched_async_create
        print("DEBUG: Patched BOTH sync and async OpenAI Completions.create", file=sys.stderr, flush=True)
        logger.info("Patched OpenAI Completions.create (sync + async) with manual LLM span")
    except ImportError as e:
        logger.warning(f"Could not patch OpenAI - {e}")

    @wraps(original_a_initiate_chat)
    async def instrumented_a_initiate_chat(self, *args, **kwargs):
        """Instrumented async initiate_chat with trace context propagation."""
        recipient = args[0] if args else kwargs.get("recipient")
        recipient_name = getattr(recipient, "name", str(recipient)) if recipient else "unknown"

        with tracer.start_as_current_span(
            "autogen.a_initiate_chat",
            attributes={
                SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.CHAIN.value,
                "autogen.agent.name": getattr(self, "name", "unknown"),
                "autogen.recipient.name": recipient_name,
            },
        ) as span:
            # Store context for OpenAI calls
            set_global_parent_context()
            try:
                result = await original_a_initiate_chat(self, *args, **kwargs)
                span.set_status(Status(StatusCode.OK))
                return result
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    @wraps(original_a_generate_reply)
    async def instrumented_a_generate_reply(self, *args, **kwargs):
        """Instrumented async generate_reply with trace context propagation."""
        with tracer.start_as_current_span(
            "autogen.a_generate_reply",
            attributes={
                SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.CHAIN.value,
                "autogen.agent.name": getattr(self, "name", "unknown"),
            },
        ) as span:
            # Store context for OpenAI calls
            set_global_parent_context()
            try:
                result = await original_a_generate_reply(self, *args, **kwargs)
                span.set_status(Status(StatusCode.OK))
                return result
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    # Apply patches
    ConversableAgent.a_initiate_chat = instrumented_a_initiate_chat
    ConversableAgent.a_generate_reply = instrumented_a_generate_reply

    logger.info("Patched AutoGen async methods: a_initiate_chat, a_generate_reply")


# Global context store for cross-async-boundary propagation
_global_parent_context = None


def set_global_parent_context(ctx=None):
    """Set the global parent context for OpenAI calls."""
    global _global_parent_context
    _global_parent_context = ctx if ctx else context.get_current()


def get_global_parent_context():
    """Get the global parent context for OpenAI calls."""
    return _global_parent_context


# Tracer name constant used before setup_observability is called
TRACER_NAME = "openinference.instrumentation.agent"


class ObservabilityConfig:
    """
    Configuration for observability setup.

    Reads from environment variables with sensible defaults.
    """

    def __init__(self):
        # Service identification
        self.service_name = os.getenv("OTEL_SERVICE_NAME", "orchestrator-agent")
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
            "http://otel-collector.kagenti-system.svc.cluster.local:8335"
        )
        self.otlp_protocol = os.getenv(
            "OTEL_EXPORTER_OTLP_PROTOCOL",
            "http/protobuf"  # Default to HTTP for wider compatibility
        )

        # Additional resource attributes
        self.extra_resource_attrs = self._parse_resource_attrs()

    def _parse_resource_attrs(self) -> Dict[str, str]:
        """
        Parse OTEL_RESOURCE_ATTRIBUTES environment variable.

        Format: key1=value1,key2=value2
        """
        attrs = {}
        resource_attrs_str = os.getenv("OTEL_RESOURCE_ATTRIBUTES", "")

        if resource_attrs_str:
            for pair in resource_attrs_str.split(","):
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    attrs[key.strip()] = value.strip()

        return attrs

    def get_resource_attributes(self) -> Dict[str, str]:
        """
        Get complete set of resource attributes for OTEL tracer.

        Returns:
            Dict with service.name, namespace, Phoenix project, etc.
        """
        attrs = {
            # Service identification
            "service.name": self.service_name,
            "service.namespace": self.namespace,

            # Kubernetes metadata
            "k8s.namespace.name": self.namespace,

            # Phoenix project routing
            "phoenix.project.name": self.phoenix_project,

            # Deployment environment
            "deployment.environment": self.deployment_env,
        }

        # Merge extra attributes from env var
        attrs.update(self.extra_resource_attrs)

        return attrs


def setup_observability(config: Optional[ObservabilityConfig] = None) -> None:
    """
    Set up OpenTelemetry tracing with OpenInference instrumentation.

    This function:
    1. Creates OTEL tracer provider with proper resource attributes
    2. Configures OTLP exporter (HTTP or gRPC)
    3. Instruments OpenAI SDK with OpenInference (for AutoGen)

    Args:
        config: Optional ObservabilityConfig. If not provided, creates default.

    Example:
        >>> setup_observability()
        >>> # All OpenAI/AutoGen operations now automatically traced to Phoenix
    """
    if config is None:
        config = ObservabilityConfig()

    logger.info("=" * 70)
    logger.info("Setting up OpenTelemetry observability")
    logger.info("-" * 70)
    logger.info(f"Service Name:      {config.service_name}")
    logger.info(f"Namespace:         {config.namespace}")
    logger.info(f"Phoenix Project:   {config.phoenix_project}")
    logger.info(f"OTLP Endpoint:     {config.otlp_endpoint}")
    logger.info(f"OTLP Protocol:     {config.otlp_protocol}")
    logger.info(f"Deployment Env:    {config.deployment_env}")
    logger.info("=" * 70)

    # Create resource with all attributes
    resource_attrs = config.get_resource_attributes()
    resource = Resource(attributes=resource_attrs)

    # Create tracer provider
    tracer_provider = TracerProvider(resource=resource)

    # Create OTLP exporter based on configured protocol
    otlp_exporter = _get_otlp_exporter(config.otlp_endpoint, config.otlp_protocol)

    # Add batch span processor for efficiency
    tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    # Set global tracer provider
    trace.set_tracer_provider(tracer_provider)

    # Lazy import instrumentors to ensure they patch libraries BEFORE they're imported elsewhere.
    # These imports MUST happen here, not at module level, because they internally import
    # openai/autogen. Importing them at module level defeats the purpose of early instrumentation.
    from openinference.instrumentation.openai import OpenAIInstrumentor
    from openinference.instrumentation.autogen import AutogenInstrumentor

    # NOTE: We do NOT use OpenAIInstrumentor because it doesn't properly
    # propagate async context through AutoGen. Instead, we manually instrument
    # the OpenAI SDK in _patch_autogen_async_methods().
    # OpenAIInstrumentor().instrument(tracer_provider=tracer_provider)

    # Auto-instrument AutoGen with OpenInference
    # This captures AutoGen-specific spans (agent conversations, tool calls)
    # Note: AutogenInstrumentor uses the global tracer provider set above
    AutogenInstrumentor().instrument()

    # Configure W3C Trace Context and Baggage propagators for distributed tracing
    set_global_textmap(CompositePropagator([
        TraceContextTextMapPropagator(),
        W3CBaggagePropagator(),
    ]))

    # Patch AutoGen async methods to propagate trace context
    # This is required because openinference-instrumentation-autogen only patches sync methods
    _patch_autogen_async_methods()

    logger.info("OpenTelemetry observability configured successfully")
    logger.info("OpenAI SDK auto-instrumented with OpenInference")
    logger.info("AutoGen auto-instrumented with OpenInference (sync + async patched)")
    logger.info("W3C Trace Context and Baggage propagators configured")
    logger.info("Traces will route to Phoenix project: %s", config.phoenix_project)


# Global tracer for creating manual spans
_tracer: Optional[trace.Tracer] = None


def get_tracer() -> trace.Tracer:
    """Get the global tracer for creating manual spans.

    Uses OpenInference-compatible tracer name to ensure spans are routed
    to Phoenix by the OTEL Collector's filter/phoenix processor.
    """
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
    Create a root AGENT span for the conversation with OpenInference attributes.

    This span serves as the root for all AutoGen/OpenAI auto-instrumented
    spans, providing a clear entry point for each agent interaction.

    Args:
        name: Span name (default: "agent_task")
        task_id: A2A task ID for filtering conversations
        context_id: A2A context ID (conversation session)
        user_id: User identifier
        input_text: The user's input message

    Yields:
        The created span

    Example:
        with create_agent_span(
            task_id="task-123",
            context_id="ctx-456",
            user_id="alice",
            input_text="Why is pod crashing?"
        ) as span:
            result = await agent.execute(messages)
            span.set_attribute("output.value", str(result))
    """
    tracer = get_tracer()

    # Build attributes following OpenInference semantic conventions
    attributes = {
        # OpenInference span kind for AI observability
        SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.AGENT.value,
    }

    # Add A2A task/context IDs as custom attributes for filtering
    if task_id:
        attributes["a2a.task_id"] = task_id
    if context_id:
        attributes["a2a.context_id"] = context_id
    if user_id:
        attributes["user.id"] = user_id
    if input_text:
        attributes[SpanAttributes.INPUT_VALUE] = input_text

    with tracer.start_as_current_span(name, attributes=attributes) as span:
        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            raise


def extract_trace_context(headers: Dict[str, str]) -> context.Context:
    """
    Extract trace context from HTTP headers.

    This extracts both W3C Trace Context (traceparent) and Baggage headers,
    enabling proper parent-child span relationships across service boundaries.

    Args:
        headers: HTTP headers dict (can be any mapping type)

    Returns:
        Context with extracted trace information
    """
    return extract(headers)


def inject_trace_context(headers: Dict[str, str]) -> Dict[str, str]:
    """
    Inject current trace context into HTTP headers.

    This injects both W3C Trace Context (traceparent) and Baggage headers,
    enabling proper parent-child span relationships when calling other services.

    Args:
        headers: Dict to inject headers into (modified in place)

    Returns:
        The headers dict with trace context added
    """
    inject(headers)
    return headers


@contextmanager
def trace_context_from_headers(headers: Dict[str, str]):
    """
    Context manager that activates trace context from HTTP headers.

    Use this to wrap request handling code so that all spans created
    within the context become children of the incoming trace.

    Args:
        headers: HTTP headers containing traceparent/baggage

    Yields:
        The extracted context

    Example:
        >>> async def handle_request(request):
        ...     with trace_context_from_headers(request.headers) as ctx:
        ...         # All spans here are connected to incoming trace
        ...         result = await process_message(request.message)
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

    Baggage allows passing context (user_id, request_id, etc.) across
    all spans in a trace, even across service boundaries.

    Args:
        context_data: Dict with keys like:
            - user_id: User identifier
            - request_id: Request identifier
            - conversation_id: Conversation identifier
            - tenant_id: Tenant identifier (for multi-tenancy)

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

    Args:
        headers: Dict of HTTP headers (lowercase keys)

    Returns:
        Dict of extracted baggage context
    """
    baggage_data = {}

    # Normalize headers to lowercase
    headers_lower = {k.lower(): v for k, v in headers.items()}

    # Map header names to baggage keys
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
