"""AutoGen agent definitions for the Orchestrator Agent."""

import logging
import sys

from autogen import ConversableAgent
from autogen.mcp.mcp_client import Toolkit

from orchestrator_agent.config import settings
from orchestrator_agent.prompts import ORCHESTRATOR_SYSTEM_PROMPT

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=settings.LOG_LEVEL, stream=sys.stdout, format="%(levelname)s: %(message)s"
)


class Agents:
    """AutoGen agent definitions for orchestration."""

    def __init__(self, mcp_toolkit: Toolkit = None):
        """Initialize agents with optional MCP toolkit for a2a-bridge."""
        self.llm_config = {
            "config_list": [
                {
                    "model": settings.TASK_MODEL_ID,
                    "base_url": settings.LLM_API_BASE,
                    "api_type": "openai",
                    "api_key": settings.LLM_API_KEY,
                }
            ],
            "temperature": settings.MODEL_TEMPERATURE,
        }

        # Main orchestrator agent that routes tasks
        self.orchestrator = ConversableAgent(
            name="Orchestrator",
            system_message=ORCHESTRATOR_SYSTEM_PROMPT,
            llm_config=self.llm_config,
            code_execution_config=False,
            human_input_mode="NEVER",
        )

        # User proxy that executes tools
        self.user_proxy = ConversableAgent(
            name="User",
            human_input_mode="NEVER",
            code_execution_config=False,
            is_termination_msg=lambda msg: msg
            and "content" in msg
            and msg["content"] is not None
            and (
                "##DONE##" in msg["content"]
                or "##TERMINATE##" in msg["content"]
                or ("tool_calls" not in msg and msg["content"] == "")
            ),
        )

        # Register MCP tools (a2a-bridge) if available
        if mcp_toolkit is not None:
            logger.info("Registering a2a-bridge MCP tools")
            mcp_toolkit.register_for_execution(self.user_proxy)
            mcp_toolkit.register_for_llm(self.orchestrator)
            for tool in mcp_toolkit.tools:
                logger.info(f"  - {tool.name}: {tool.description}")
        else:
            logger.warning("No MCP toolkit provided - orchestrator will have no tools")
