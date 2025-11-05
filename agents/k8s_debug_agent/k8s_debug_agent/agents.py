import logging
import sys

from autogen import ConversableAgent
from autogen.mcp.mcp_client import Toolkit

from k8s_debug_agent.config import settings
from k8s_debug_agent.llm import LLMConfig
from k8s_debug_agent.prompts import (
    ASSISTANT_PROMPT,
    GOAL_JUDGE_PROMPT,
    PLANNER_MESSAGE,
    REFLECTION_ASSISTANT_PROMPT,
    REPORT_WRITER_PROMPT,
)

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=settings.LOG_LEVEL, stream=sys.stdout, format="%(levelname)s: %(message)s"
)


class Agents:
    def __init__(
        self,
        mcp_toolkit: Toolkit = None,
    ):
        llm_config = LLMConfig()

        self.k8s_assistant = ConversableAgent(
            system_message=ASSISTANT_PROMPT,
            name="Kubernetes_Assistant",
            llm_config=llm_config.openai_llm_config,
            code_execution_config=False,
            human_input_mode="NEVER",
        )

        # User Proxy chats with assistant on behalf of user and executes tools
        self.user_proxy = ConversableAgent(
            name="User",
            human_input_mode="NEVER",
            code_execution_config=False,
            is_termination_msg=lambda msg: msg
            and "content" in msg
            and msg["content"] is not None
            and (
                "##ANSWER" in msg["content"]
                or "## Answer" in msg["content"]
                or "##TERMINATE##" in msg["content"]
                or ("tool_calls" not in msg and msg["content"] == "")
            ),
        )

        # Determines whether the ultimate objective has been met
        self.goal_judge = ConversableAgent(
            name="GoalJudge",
            system_message=GOAL_JUDGE_PROMPT,
            llm_config=llm_config.critic_llm_config,
            human_input_mode="NEVER",
        )

        # Step Critic
        self.step_critic = ConversableAgent(
            name="Step_Critic",
            llm_config=llm_config.critic_llm_config,
            human_input_mode="NEVER",
        )

        # Reflection Assistant: Reflect on plan progress and give the next step
        self.reflection_assistant = ConversableAgent(
            name="ReflectionAssistant",
            system_message=REFLECTION_ASSISTANT_PROMPT,
            llm_config=llm_config.reflection_llm_config,
            human_input_mode="NEVER",
        )

        # Report Generator
        self.report_generator = ConversableAgent(
            name="Report_Generator",
            llm_config=llm_config.openai_llm_config,
            code_execution_config=False,
            human_input_mode="NEVER",
            system_message=REPORT_WRITER_PROMPT,
        )

        tool_descriptions = []
        if mcp_toolkit is not None:
            logging.info("Registering MCP tool")
            logging.info(mcp_toolkit)
            mcp_toolkit.register_for_execution(self.user_proxy)
            mcp_toolkit.register_for_llm(self.k8s_assistant)
            for tool in mcp_toolkit.tools:
                tool_descriptions.append({tool.name: tool.description})
            tool_descriptions = str(tool_descriptions)
            logging.info("Tool descriptions: %s", tool_descriptions)
        else:
            logging.info("No MCP tools to register")

        # Provides the initial high level plan
        self.planner = ConversableAgent(
            name="Planner",
            system_message=PLANNER_MESSAGE.format(tool_descriptions=tool_descriptions),
            llm_config=llm_config.planner_llm_config,
            human_input_mode="NEVER",
        )
