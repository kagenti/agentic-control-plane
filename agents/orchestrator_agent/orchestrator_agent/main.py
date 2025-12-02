"""Main orchestration logic for the Orchestrator Agent."""

import logging
from typing import Optional

from autogen.mcp.mcp_client import Toolkit

from orchestrator_agent.agents import Agents
from orchestrator_agent.config import settings
from orchestrator_agent.event import Event, LoggingEvent


class OrchestratorAgent:
    """Orchestrator that routes tasks to specialized agents via A2A protocol."""

    def __init__(
        self,
        eventer: Event = None,
        mcp_toolkit: Toolkit = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.logger = logger or logging.getLogger(__name__)
        self.agents = Agents(mcp_toolkit)
        self.eventer = eventer or LoggingEvent(self.logger)

    async def execute(self, messages: list[dict]) -> str:
        """Execute the orchestration task.

        Args:
            messages: List of message dicts with role and content

        Returns:
            Final response string
        """
        try:
            # Extract user input from messages
            user_input = self._extract_user_input(messages)
            await self.eventer.emit_event(f"Received request: {user_input[:100]}...")

            # Start orchestration conversation
            await self.eventer.emit_event("Analyzing request and discovering agents...")

            response = await self.agents.user_proxy.a_initiate_chat(
                recipient=self.agents.orchestrator,
                message=user_input,
                max_turns=10,  # Allow multiple turns for tool use
            )

            # Extract final response
            chat_history = getattr(response, "chat_history", [])
            if not chat_history:
                return "I was unable to process your request."

            # Find the last meaningful response
            for msg in reversed(chat_history):
                if isinstance(msg, dict) and msg.get("content"):
                    content = msg["content"]
                    if isinstance(content, str) and content.strip():
                        return content

            return "Task completed but no response was generated."

        except Exception as e:
            error_msg = f"Orchestration failed: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return error_msg

    def _extract_user_input(self, messages: list[dict]) -> str:
        """Extract user input from message list."""
        if not messages:
            return ""

        # Get the last user message
        last_msg = messages[-1]
        content = last_msg.get("content", "")

        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            # Handle structured content (text parts)
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
            return " ".join(text_parts)

        return str(content)
