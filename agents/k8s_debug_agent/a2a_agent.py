"""A2A-compatible Kubernetes debugging agent entrypoint."""

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

from k8s_debug_agent.config import Settings, settings
from k8s_debug_agent.event import Event
from k8s_debug_agent.main import K8sDebugAgent

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=settings.LOG_LEVEL,
    stream=sys.stdout,
    format="%(levelname)s: %(message)s",
)


def get_agent_card(host: str, port: int):
    """Returns the Agent Card for the Kubernetes debugging agent."""

    capabilities = AgentCapabilities(streaming=True)
    skill = AgentSkill(
        id="k8s_debug",
        name="Kubernetes troubleshooting",
        description="Investigate Kubernetes workloads, events, and logs to explain failures.",
        tags=["kubernetes", "debug", "observability", "operations"],
        examples=[
            "Why is the payments-api deployment stuck in CrashLoopBackOff?",
            "Summarize recent warning events in the staging namespace.",
        ],
    )
    return AgentCard(
        name="Kubernetes Debug Agent",
        description="Diagnose Kubernetes workloads and provide actionable remediation guidance.",
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

    async def emit_event(self, message: str, final: bool = False) -> None:
        logger.info("Emitting event %s", message)

        if final:
            parts = [TextPart(text=message)]
            await self.task_updater.add_artifact(parts)
            await self.task_updater.complete()
        else:
            await self.task_updater.update_status(
                TaskState.working,
                new_agent_text_message(
                    message,
                    self.task_updater.context_id,
                    self.task_updater.task_id,
                ),
            )


class KubernetesDebugExecutor(AgentExecutor):
    """Adapter that wires the Kubernetes debug agent into the A2A runtime."""

    async def _run_agent(
        self,
        messages: list[dict[str, str]],
        settings: Settings,
        event_emitter: Event,
        toolkit: Optional[Toolkit],
    ) -> None:
        kubernetes_agent = K8sDebugAgent(
            eventer=event_emitter,
            mcp_toolkit=toolkit,
        )
        result = await kubernetes_agent.execute(messages)
        await event_emitter.emit_event(result, True)

    async def execute(self, context: RequestContext, event_queue: EventQueue):
        """Executes the debugging task."""

        user_input = [context.get_user_input()]
        task = context.current_task
        if not task:
            task = new_task(context.message)  # type: ignore[arg-type]
            await event_queue.enqueue_event(task)
        task_updater = TaskUpdater(event_queue, task.id, task.context_id)
        event_emitter = A2AEvent(task_updater)
        messages: list[dict[str, str]] = []
        for message in user_input:
            messages.append(
                {
                    "role": "User",
                    "content": message,
                }
            )

        toolkit: Optional[Toolkit] = None
        try:
            if settings.MCP_URL:
                logging.info("Connecting to MCP server at %s", settings.MCP_URL)
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
                    await self._run_agent(
                        messages,
                        settings,
                        event_emitter,
                        toolkit,
                    )
            else:
                await self._run_agent(
                    messages,
                    settings,
                    event_emitter,
                    toolkit,
                )

        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            await event_emitter.emit_event(
                "I'm sorry I was unable to fulfill your request. "
                f"I encountered the following exception: {exc}",
                True,
            )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Not implemented."""

        raise Exception("cancel not supported")


def run():
    """Runs the A2A Agent application."""

    agent_card = get_agent_card(host="0.0.0.0", port=settings.SERVICE_PORT)

    request_handler = DefaultRequestHandler(
        agent_executor=KubernetesDebugExecutor(),
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
