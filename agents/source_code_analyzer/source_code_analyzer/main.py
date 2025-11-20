"""Orchestrator for the Source Code Analyzer pipeline."""

from __future__ import annotations

import logging
import traceback

from autogen.mcp.mcp_client import Toolkit

from source_code_analyzer.agents import Agents
from source_code_analyzer.config import Settings
from source_code_analyzer.data_types import AnalyzerContext, CandidateFiles, RepositoryInfo
from source_code_analyzer.event import Event, LoggingEvent
from source_code_analyzer.utils import AgentWorkflowError, extract_json_response


class SourceCodeAnalyzer:

    def __init__(
        self,
        eventer: Event = None,
        mcp_toolkit: Toolkit = None,
    ):
        self.logger = logging.getLogger(__name__)
        self.agents = Agents(mcp_toolkit)
        self.eventer = eventer or LoggingEvent(self.logger)
        self.context = AnalyzerContext()
        self.config = Settings()

    async def execute(self, body: str):
        try:
            # Extract Goal
            self.context.goal = self._extract_user_input(body)

            await self._identify_repository()
            search_assessment = await self._search_repository_for_files()
            candidate_files = await self._summarize_candidates(search_assessment)

            return await self._determine_best_file(candidate_files)

        except AgentWorkflowError as exc:
            error_message = str(exc)
            await self.eventer.emit_event(error_message, final=True)
            return error_message

    async def summarize_results(self, file_info):
        self.eventer.emit_event("📝 Generating a report.")
        determination_message = (
            "You are a savvy engineer who will determine which of the following files answer the user's query."
            "You will pick one file from the one or more files below and clearly state your reason for picking it, citing evidence from the file."
            "If you are uncertain which one to pick, state your reason why."
            "Do NOT make tool calls - You have no tools other than your own brain! Just explain your decision based off of the tool output from the previous helper."
            f"User query: {self.context.goal}"
            f"Files and their contents: {file_info}"
        )
        report = await self.agents.user_proxy.a_initiate_chat(
            recipient=self.agents.report_generator, message=determination_message, max_turns=1
        )

        return report.chat_history[-1]["content"]

    def _extract_user_input(self, body):
        content = body[-1]["content"]
        latest_content = ""

        if isinstance(content, str):
            latest_content = content
        else:
            for item in content:
                if item["type"] == "text":
                    latest_content += item["text"]
                else:
                    self.logger.warning(f"Ignoring content with type {item['type']}")

        return latest_content

    async def _identify_repository(self):
        """Ask the repo identifier agent for GitHub metadata."""
        output = await self.agents.user_proxy.a_initiate_chat(
            recipient=self.agents.repo_identifier,
            message=self.context.goal,
            max_turns=1,
        )
        try:
            self.context.repo_details = RepositoryInfo.model_validate(
                extract_json_response(output, "Repository identifier")
            )
        except Exception as e:
            self.logger.error(traceback.format_exception(e))
            raise AgentWorkflowError("Unable to determine the repository information needed")
        self.eventer.emit_event(
            f"🕵️‍♀️ Investigating the following Github repository: {str(self.context.repo_details.model_dump(mode="json"))}"
        )

    async def _search_repository_for_files(self):
        """Use the GitHub search assistant to gather candidate files."""
        self.eventer.emit_event("🔎 Searching Github for relevant files...")
        message = self._build_github_search_message()
        search_output = await self.agents.user_proxy.a_initiate_chat(
            recipient=self.agents.code_search_assistant,
            message=message,
            max_turns=3,
        )
        organized_output = self._organize_search_history(search_output)
        self.context.github_search_output.append(organized_output)
        return organized_output

    def _build_github_search_message(self) -> str:
        """Return the instructions for the GitHub search agent."""
        repo_details = str(self.context.repo_details.model_dump(mode="json"))
        return (
            "Your job is to use the github search tool gather a list of at least one file in a given github repository "
            "that will answer a user's query. When you are performing the search, be sure to include the repository name "
            "and owner in the query, i.e. repo:owner/repository, as well as a relevant search query. "
            f"Repository information: {repo_details} User query: {self.context.goal}"
        )

    def _organize_search_history(self, search_output):
        """Normalize assistant/tool responses into a compact dict."""
        output_dict = {}
        for item in search_output.chat_history:
            if item.get("name") == self.agents.code_search_assistant:
                output_dict["Assessment"] = item.get("content")
            elif item.get("role") == "tool":
                output_dict["Tool Call Results"] = item.get("content")
        return output_dict

    async def _summarize_candidates(self, search_assessment):
        """Summarize search output into candidate files."""
        self.eventer.emit_event("🧐 Analyzing gathered files...")
        message = f"User Query: {self.context.goal} \n {search_assessment}"
        search_summary = await self.agents.user_proxy.a_initiate_chat(
            recipient=self.agents.file_search_summarizer,
            message=message,
            max_turns=1,
        )
        try:
            return CandidateFiles.model_validate(
                extract_json_response(search_summary, "Git file search summary")
            )
        except Exception as e:
            self.logger.error(traceback.format_exception(e))
            raise AgentWorkflowError("Unable to determine the repository information needed")

    async def _determine_best_file(self, candidate_files: CandidateFiles):
        """Return early with a confident pick or fetch more detail for a final decision."""
        if self._has_confident_top_pick(candidate_files):
            self.eventer.emit_event("🎯 Identified most likely file")
            return await self.summarize_results(candidate_files.top_file_pick.strip())

        candidate_file_contents = await self._retrieve_candidate_file_contents(candidate_files)
        return await self.summarize_results(candidate_file_contents)

    def _has_confident_top_pick(self, candidate_files: CandidateFiles) -> bool:
        invalid_values = {"", "none", "null", "n/a", "unknown", "not sure"}
        top_file_pick = (candidate_files.top_file_pick or "").strip()
        return bool(top_file_pick) and top_file_pick.lower() not in invalid_values

    async def _retrieve_candidate_file_contents(self, candidate_files: CandidateFiles):
        """Fetch file contents for each candidate up to the configured limit."""
        candidates_to_fetch = candidate_files.candidate_files[: self.config.MAX_FILES_TO_RETRIEVE]
        candidate_file_contents = []
        for file in candidates_to_fetch:
            self.eventer.emit_event(f"🗃️ Fetching file contents of candidate {file}")
            message = self._build_file_retrieval_message(file)
            file_grab_output = await self.agents.user_proxy.a_initiate_chat(
                recipient=self.agents.file_retrieval_assistant,
                message=message,
                max_turns=3,
            )
            for item in file_grab_output.chat_history:
                if item.get("role") == "tool":
                    candidate_file_contents.append({"file": file, "contents": item.get("content")})
        return candidate_file_contents

    def _build_file_retrieval_message(self, file: str) -> str:
        """Describe how the retrieval assistant should grab file contents."""
        repo_details = str(self.context.repo_details.model_dump(mode="json"))
        return (
            "Fetch the contents of the following file from Github. Do NOT populate the SHA field. "
            "Do NOT populate the ref field. Leave both those fields untouched - don't even put a blank. Leave them alone. \n"
            f"File: {file} \n Repository: {repo_details}"
        )
