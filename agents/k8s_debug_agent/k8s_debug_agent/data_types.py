from pydantic import BaseModel, Field


class Plan(BaseModel):
    steps: list[str]


class CriticDecision(BaseModel):
    decision: bool = Field(
        description="A true or false decision on whether the goal has been fully accomplished"
    )
    explanation: str = Field(
        description="A thorough yet concise explanation of why you came to this decision."
    )


class Step(BaseModel):
    step_instruction: str = Field(
        description="A concise instruction of what the next step in the plan should be"
    )
    requirement_to_fulfill: str = Field(
        description="Explain your thinking around the requirement of the plan that this step will accomplish and why you chose the step instruction"
    )
