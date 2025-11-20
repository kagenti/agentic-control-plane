import logging
import sys

from autogen import ConversableAgent
from autogen.mcp.mcp_client import Toolkit

from source_code_analyzer.config import settings
from source_code_analyzer.llm import LLMConfig
from source_code_analyzer.prompts import (
    ASSISTANT_PROMPT,
    FILE_SEARCH_SUMMARIZER_PROMPT,
    REPO_IDENTIFIER,
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

        # No tool assistant
        self.report_generator = ConversableAgent(
            name="Report_Generator_Assistant",
            llm_config=llm_config.openai_llm_config,
            code_execution_config=False,
            human_input_mode="NEVER",
        )

        # Git tool assistant
        self.file_retrieval_assistant = ConversableAgent(
            system_message=ASSISTANT_PROMPT,
            name="File_Retrieval_Assistant",
            llm_config=llm_config.openai_llm_config,
            code_execution_config=False,
            human_input_mode="NEVER",
        )

        # Git code search assistant
        self.code_search_assistant = ConversableAgent(
            system_message=ASSISTANT_PROMPT,
            name="Git_Code_Search_Assistant",
            llm_config=llm_config.openai_llm_config,
            code_execution_config=False,
            human_input_mode="NEVER",
        )

        self.file_search_summarizer = ConversableAgent(
            system_message=FILE_SEARCH_SUMMARIZER_PROMPT,
            name="File_Search_Summarizer",
            llm_config=llm_config.file_search_summarizer_llm_config,
            code_execution_config=False,
            human_input_mode="NEVER",
        )

        # Repository Identifier extracts the repository information from the user's request
        self.repo_identifier = ConversableAgent(
            system_message=REPO_IDENTIFIER,
            name="Repo_ID_Assistant",
            llm_config=llm_config.repo_id_llm_config,
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

        code_search_tools = []
        file_retrieval_tools = []
        if mcp_toolkit is not None:
            logging.info("Registering MCP tool")
            logging.info(mcp_toolkit)
            mcp_toolkit.register_for_execution(self.user_proxy)
            for tool in mcp_toolkit.tools:
                # Filter out specific tools for specific agents
                if tool.name in "search_code":
                    code_search_tools.append(tool)
                if tool.name in "get_file_contents":
                    file_retrieval_tools.append(tool)

            logging.info(f"Code Search Tools {code_search_tools}")
            code_search_toolkit = Toolkit(code_search_tools)
            code_search_toolkit.register_for_llm(self.code_search_assistant)

            logging.info(f"File retrieval tools {file_retrieval_tools}")
            file_retrieval_toolkit = Toolkit(file_retrieval_tools)
            file_retrieval_toolkit.register_for_llm(self.file_retrieval_assistant)
        else:
            logging.info("No MCP tools to register")
