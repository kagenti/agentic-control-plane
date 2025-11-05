import json
import logging
from dataclasses import dataclass, field
from typing import Any, List

from autogen.mcp.mcp_client import Toolkit

from k8s_debug_agent.agents import Agents
from k8s_debug_agent.config import Settings
from k8s_debug_agent.event import Event, LoggingEvent
from k8s_debug_agent.prompts import STEP_CRITIC_PROMPT


class AgentWorkflowError(Exception):
    """Raised when an unrecoverable issue occurs in the agent workflow."""


@dataclass
class PlanContext:
    goal: str = ""
    step_index: int = 0
    plan_dict: dict = field(default_factory=dict)
    answer_output: List[Any] = field(default_factory=list)
    steps_taken: List[str] = field(default_factory=list)
    last_step: str = ""
    last_output: Any = ""
    goal_fail_reason: str = ""


class K8sDebugAgent:
    def __init__(
        self,
        eventer: Event = None,
        mcp_toolkit: Toolkit = None,
        logger=None,
    ):
        self.logger = logger or logging.getLogger(__name__)
        self.agents = Agents(mcp_toolkit)
        self.eventer = eventer or LoggingEvent(self.logger)
        self.context = PlanContext()
        self.config = Settings()

    async def execute(self, body: str):
        try:
            # Parse instructions from user
            self.context.goal = self._extract_user_input(body)

            # Create an initial plan with the instructions
            self.context.plan_dict = await self._generate_plan(self.context.goal)

            if not isinstance(self.context.plan_dict, dict):
                raise AgentWorkflowError(
                    "Plan generation failed: planner response was not a JSON object."
                )

            steps = self.context.plan_dict.get("steps")
            if not isinstance(steps, list) or not steps:
                raise AgentWorkflowError(
                    "Plan generation failed: no steps were provided."
                )

            # Step through plan
            for self.context.step_index in range(self.config.MAX_PLAN_STEPS):
                # If this is the first step, just take first step already prescribed in plan
                if self.context.step_index == 0:
                    instructions = steps[0]
                    if not isinstance(instructions, str):
                        raise AgentWorkflowError(
                            "Plan generation returned a non-string step instruction."
                        )
                else:
                    # First call the step critic to check if the previous step was successful
                    await self.determine_last_step_success()

                    # Now call the goal critic to check if we met our goal yet
                    goal_reflection_message = await self.determine_goal_success()
                    if goal_reflection_message["decision"]:
                        # We've accomplished the goal, exit loop.
                        break

                    # Goal not met yet; grab next instruction
                    next_instruction = await self._determine_next_instruction()
                    if (
                        not isinstance(next_instruction, dict)
                        or "step_instruction" not in next_instruction
                    ):
                        raise AgentWorkflowError(
                            "Reflection assistant returned an invalid next step."
                        )
                    instructions = next_instruction["step_instruction"]
                    if not isinstance(instructions, str):
                        raise AgentWorkflowError(
                            "Reflection assistant returned a non-string step instruction."
                        )

                # Now that we have determined the next step to take, execute it
                self.context.last_output = await self.execute_instructions(instructions)

                # The previous instruction and its output will be recorded for the next iteration to inspect before determining the next step of the plan
                self.context.last_step = instructions

            # Create final report
            await self.eventer.emit_event(message="Summing up findings...")
            # Now that we've gathered all the information we need, we will summarize it to directly answer the original prompt
            final_prompt = f"User's query: {self.context.goal}. Information Gathered: {self.context.answer_output}"
            final_response = await self._invoke_agent(
                description="Report generation",
                recipient=self.agents.report_generator,
                message=final_prompt,
                max_turns=1,
            )
            return self._extract_text_response(final_response, "Report generation")

        except AgentWorkflowError as exc:
            error_message = str(exc)
            await self.eventer.emit_event(error_message, final=True)
            return error_message

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

    async def _invoke_agent(
        self,
        *,
        description: str,
        recipient,
        message: str,
        max_turns: int | None = None,
        **kwargs,
    ):
        try:
            return await self.agents.user_proxy.a_initiate_chat(
                recipient=recipient,
                message=message,
                max_turns=max_turns,
                **kwargs,
            )
        except Exception as exc:  # noqa: BLE001
            raise AgentWorkflowError(f"{description} failed: {exc}") from exc

    def _extract_text_response(self, response, description: str) -> str:
        chat_history = getattr(response, "chat_history", None)
        if not isinstance(chat_history, list) or not chat_history:
            raise AgentWorkflowError(f"{description} returned an empty conversation.")

        try:
            content = chat_history[-1]["content"]
        except (TypeError, KeyError) as exc:
            raise AgentWorkflowError(
                f"{description} returned malformed content."
            ) from exc

        if not isinstance(content, str) or not content.strip():
            raise AgentWorkflowError(f"{description} returned empty text content.")

        return content

    def _extract_json_response(self, response, description: str) -> dict:
        content = self._extract_text_response(response, description)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AgentWorkflowError(f"{description} returned invalid JSON.") from exc

        if not isinstance(parsed, dict):
            raise AgentWorkflowError(
                f"{description} returned JSON that was not an object."
            )

        return parsed

    async def _generate_plan(self, instruction):
        await self.eventer.emit_event(message="Creating a plan...")
        response = await self._invoke_agent(
            description="Plan generation",
            recipient=self.agents.planner,
            message=instruction,
            max_turns=1,
        )
        return self._extract_json_response(response, "Plan generation")

    async def _determine_next_instruction(self):
        await self.eventer.emit_event(message="Planning the next step...")
        message = {
            "Goal": self.context.goal,
            "Plan": str(self.context.plan_dict),
            "Last Step": self.context.last_step,
            "Last Step Output": str(self.context.last_output),
            "Missing Info for Goal": self.context.goal_fail_reason,
            "Steps Taken": str(self.context.steps_taken),
        }
        response = await self._invoke_agent(
            description="Next step planning",
            recipient=self.agents.reflection_assistant,
            max_turns=1,
            message=f"(```{str(message)}```",
        )
        return self._extract_json_response(response, "Next step planning")

    async def determine_last_step_success(self):
        response = await self._invoke_agent(
            description="Step evaluation",
            recipient=self.agents.step_critic,
            max_turns=1,
            message=STEP_CRITIC_PROMPT.format(
                last_step=self.context.last_step,
                context=self.context.answer_output,
                last_output=self.context.last_output,
            ),
        )
        was_job_accomplished = self._extract_json_response(response, "Step evaluation")

        # Only store the output of the last step to the context if it was successful
        # Throw away output of unsuccessful steps
        decision = was_job_accomplished.get("decision")
        explanation = was_job_accomplished.get("explanation")
        if not isinstance(decision, bool) or not isinstance(explanation, str):
            raise AgentWorkflowError("Step evaluation returned an unexpected schema.")

        if not decision:
            self.context.last_step = f"The previous step was {self.context.last_step} but was not accomplished: {explanation}."
        else:
            self.context.answer_output.append(self.context.last_output)
            self.context.steps_taken.append(self.context.last_step)

    async def determine_goal_success(self) -> dict:
        goal_message = {
            "Goal": self.context.goal,
            "Plan": self.context.plan_dict,
            "Information Gathered": self.context.answer_output,
        }
        response = await self._invoke_agent(
            description="Goal evaluation",
            recipient=self.agents.goal_judge,
            max_turns=1,
            message=f"(```{str(goal_message)}```",
        )
        output_dict = self._extract_json_response(response, "Goal evaluation")

        decision = output_dict.get("decision")
        explanation = output_dict.get("explanation")
        if not isinstance(decision, bool) or not isinstance(explanation, str):
            raise AgentWorkflowError("Goal evaluation returned an unexpected schema.")

        if not decision:
            self.context.goal_fail_reason = explanation

        return output_dict

    async def execute_instructions(self, instructions) -> dict:
        await self.eventer.emit_event(message="Executing step: " + str(instructions))
        if not isinstance(instructions, str) or not instructions.strip():
            raise AgentWorkflowError("Received an empty instruction to execute.")

        prompt = f"Instruction: {instructions}"
        if self.context.answer_output:
            prompt += f"\n Contextual Information: \n{self.context.answer_output}"

        response = await self._invoke_agent(
            description="Instruction execution",
            recipient=self.agents.k8s_assistant,
            message=prompt,
        )

        chat_history = getattr(response, "chat_history", None)
        if not isinstance(chat_history, list):
            raise AgentWorkflowError(
                "Instruction execution returned malformed chat history."
            )

        assistant_replies = []
        raw_tool_output = []
        for chat_item in chat_history:
            if not isinstance(chat_item, dict):
                continue
            role = chat_item.get("role")
            content = chat_item.get("content")
            if role == "tool" and content:
                raw_tool_output.append(content)
            if content and chat_item.get("name") == self.agents.k8s_assistant.name:
                assistant_replies.append(content)

        if not assistant_replies and not raw_tool_output:
            raise AgentWorkflowError(
                "Instruction execution produced no assistant response or tool output."
            )

        return {"answer": assistant_replies, "sources": raw_tool_output}
