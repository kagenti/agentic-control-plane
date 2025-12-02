"""A2A-compatible Orchestrator Agent entrypoint."""

# CRITICAL: Initialize OpenTelemetry instrumentation BEFORE importing any libraries
# that we want to instrument (autogen, openai). This ensures the instrumentors can
# properly patch the library classes before they are used.
from orchestrator_agent.observability import (
    setup_observability,
    create_agent_span,
    trace_context_from_headers,
    set_baggage_context,
    extract_baggage_from_headers,
)

setup_observability()

# Import OpenInference context manager for adding attributes to all spans
try:
    from openinference.instrumentation import using_attributes
except ImportError:
    from contextlib import nullcontext as using_attributes

# Now import remaining dependencies (autogen imports happen AFTER instrumentation)
import logging
import sys
import traceback
from typing import Optional

import uvicorn
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events.event_queue import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    TaskState,
    TextPart,
)
from a2a.utils import new_agent_text_message, new_task
from autogen.mcp.mcp_client import Toolkit, create_toolkit
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from orchestrator_agent.config import settings
from orchestrator_agent.event import Event
from orchestrator_agent.main import OrchestratorAgent

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=settings.LOG_LEVEL,
    stream=sys.stdout,
    format="%(levelname)s: %(message)s",
)


def get_agent_card(host: str, port: int):
    """Returns the Agent Card for the Orchestrator agent."""

    capabilities = AgentCapabilities(streaming=True)
    skill = AgentSkill(
        id="orchestrate",
        name="Task Orchestration",
        description="Routes tasks to specialized agents based on their capabilities.",
        tags=["orchestration", "routing", "coordination", "a2a"],
        examples=[
            "Get the weather in London and check Kubernetes pod status",
            "List all available agents and their capabilities",
            "Delegate this task to the most appropriate agent",
        ],
    )
    return AgentCard(
        name="Orchestrator Agent",
        description="Intelligent task router that discovers and coordinates specialized agents via A2A protocol.",
        url=f"http://{host}:{port}/",
        version="1.0.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=capabilities,
        skills=[skill],
    )


class A2AEvent:
    """Task event bridge that streams updates back to the A2A control plane."""

    def __init__(self, task_updater: TaskUpdater):
        self.task_updater = task_updater
        self._completed = False

    async def emit_event(self, message: str, final: bool = False) -> None:
        logger.info("Emitting event %s", message)

        if self._completed:
            logger.warning("Task already completed, skipping emit_event")
            return

        if final:
            parts = [TextPart(text=message)]
            try:
                await self.task_updater.add_artifact(parts)
                await self.task_updater.complete()
                self._completed = True
            except RuntimeError as e:
                if "terminal state" in str(e):
                    logger.warning("Task already in terminal state: %s", e)
                    self._completed = True
                else:
                    raise
        else:
            await self.task_updater.update_status(
                TaskState.working,
                new_agent_text_message(
                    message,
                    self.task_updater.context_id,
                    self.task_updater.task_id,
                ),
            )


class OrchestratorExecutor(AgentExecutor):
    """Adapter that wires the Orchestrator agent into the A2A runtime."""

    async def _run_agent(
        self,
        messages: list[dict[str, str]],
        event_emitter: Event,
        toolkit: Optional[Toolkit],
    ) -> None:
        agent = OrchestratorAgent(
            eventer=event_emitter,
            mcp_toolkit=toolkit,
        )
        result = await agent.execute(messages)
        await event_emitter.emit_event(result, True)

    async def execute(self, context: RequestContext, event_queue: EventQueue):
        """Executes the orchestration task."""

        user_input = [context.get_user_input()]
        task = context.current_task
        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)
        task_updater = TaskUpdater(event_queue, task.id, task.context_id)
        event_emitter = A2AEvent(task_updater)
        messages: list[dict[str, str]] = []
        for message in user_input:
            messages.append({"role": "User", "content": message})

        # Extract headers for trace propagation
        headers = {}
        if hasattr(context, 'headers'):
            headers = dict(context.headers)
        elif hasattr(context, 'message') and context.message:
            if hasattr(context.message, 'headers') and context.message.headers:
                headers = dict(context.message.headers)
            elif hasattr(context.message, 'metadata') and context.message.metadata:
                headers = context.message.metadata.get('headers', {})

        # Extract baggage from headers
        baggage_data = extract_baggage_from_headers(headers)
        if task:
            baggage_data['task_id'] = task.id
            baggage_data['context_id'] = task.context_id
        if 'user_id' not in baggage_data:
            baggage_data['user_id'] = 'anonymous'

        # OpenInference attributes
        oi_session_id = task.context_id if task else baggage_data.get('context_id')
        oi_user_id = baggage_data.get('user_id', 'anonymous')
        oi_metadata = {
            'task_id': task.id if task else baggage_data.get('task_id'),
            'request_id': baggage_data.get('request_id'),
        }

        toolkit: Optional[Toolkit] = None
        try:
            with trace_context_from_headers(headers):
                set_baggage_context(baggage_data)

                with using_attributes(
                    session_id=oi_session_id,
                    user_id=oi_user_id,
                    metadata=oi_metadata,
                ):
                    with create_agent_span(
                        name="orchestrator_agent",
                        task_id=task.id if task else None,
                        context_id=task.context_id if task else None,
                        user_id=oi_user_id,
                        input_text=user_input[0] if user_input else None,
                    ):
                        if settings.MCP_URL:
                            logging.info("Connecting to a2a-bridge at %s", settings.MCP_URL)
                            async with (
                                streamablehttp_client(url=settings.MCP_URL) as (
                                    read_stream,
                                    write_stream,
                                    _,
                                ),
                                ClientSession(read_stream, write_stream) as session,
                            ):
                                await session.initialize()
                                toolkit = await create_toolkit(
                                    session=session,
                                    use_mcp_resources=False,
                                )
                                await self._run_agent(messages, event_emitter, toolkit)
                        else:
                            logging.warning("No MCP_URL configured - orchestrator has no tools")
                            await self._run_agent(messages, event_emitter, toolkit)

        except Exception as exc:
            traceback.print_exc()
            await event_emitter.emit_event(
                f"Orchestration failed: {exc}",
                True,
            )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Not implemented."""
        raise Exception("cancel not supported")


def run():
    """Runs the A2A Agent application."""

    agent_card = get_agent_card(host="0.0.0.0", port=settings.SERVICE_PORT)

    request_handler = DefaultRequestHandler(
        agent_executor=OrchestratorExecutor(),
        task_store=InMemoryTaskStore(),
    )

    server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

    app = server.build()

    uvicorn.run(app, host="0.0.0.0", port=settings.SERVICE_PORT)


def main():
    """Console script entrypoint for packaging compatibility."""
    run()


if __name__ == "__main__":
    main()
