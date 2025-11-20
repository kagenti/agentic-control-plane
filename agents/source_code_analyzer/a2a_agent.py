"""A2A-compatible entrypoint for the Source Code Analyzer agent."""

from __future__ import annotations

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
from a2a.types import AgentCapabilities, AgentCard, AgentSkill, TaskState, TextPart
from a2a.utils import new_agent_text_message, new_task
from autogen.mcp.mcp_client import Toolkit, create_toolkit
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from source_code_analyzer.config import Settings, settings
from source_code_analyzer.event import Event
from source_code_analyzer.main import SourceCodeAnalyzer

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=settings.LOG_LEVEL,
    stream=sys.stdout,
    format="%(levelname)s: %(message)s",
)


def get_agent_card(host: str, port: int) -> AgentCard:
    capabilities = AgentCapabilities(streaming=True)
    skill = AgentSkill(
        id="source-code-analyzer",
        name="Source Code Analyzer",
        description="Map log/error messages to likely source code locations.",
        tags=["debugging", "code-search", "triage"],
        examples=[
            "Traceback (most recent call last): ... ValueError ... in foo.py:123",
            "TypeError: Cannot read properties of undefined in src/app.ts:84:17",
        ],
    )
    return AgentCard(
        name="Source Code Analyzer Agent",
        description="Connects logs to probable code locations within a GitHub repository.",
        url=f"http://{host}:{port}/",
        version="0.1.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=capabilities,
        skills=[skill],
    )


class A2AEvent(Event):
    def __init__(self, task_updater: TaskUpdater):
        self.task_updater = task_updater

    async def emit_event(self, message: str, final: bool = False) -> None:
        logger.info("event: %s", message)
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


class SourceAnalyzerExecutor(AgentExecutor):

    async def _run_agent(
        self,
        messages: list[dict[str, str]],
        settings: Settings,
        event_emitter: Event,
        toolkit: Optional[Toolkit],
    ) -> None:
        source_code_agent = SourceCodeAnalyzer(
            eventer=event_emitter,
            mcp_toolkit=toolkit,
        )
        result = await source_code_agent.execute(messages)
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
                logger.info("Connecting to MCP server at %s", settings.MCP_URL)
                headers = {"X-MCP-Readonly": "true"}
                if settings.MCP_TOKEN:
                    headers["Authorization"] = f"Bearer {settings.MCP_TOKEN}"
                async with (
                    streamablehttp_client(url=settings.MCP_URL, headers=headers or None) as (
                        read_stream,
                        write_stream,
                        _,
                    ),
                    ClientSession(read_stream, write_stream) as session,
                ):
                    await session.initialize()
                    toolkit = await create_toolkit(session=session, use_mcp_resources=False)
                    await self._run_agent(messages, settings, event_emitter, toolkit)
            else:
                await self._run_agent(messages, settings, event_emitter, None)

        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            await event_emitter.emit_event(
                "I'm sorry I was unable to fulfill your request. "
                f"I encountered the following exception: {exc}",
                True,
            )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise RuntimeError("cancel not supported")


def run() -> None:
    card = get_agent_card(host="0.0.0.0", port=settings.SERVICE_PORT)
    handler = DefaultRequestHandler(
        agent_executor=SourceAnalyzerExecutor(),
        task_store=InMemoryTaskStore(),
    )
    server = A2AStarletteApplication(agent_card=card, http_handler=handler)
    uvicorn.run(server.build(), host="0.0.0.0", port=settings.SERVICE_PORT)


def main() -> None:
    run()
