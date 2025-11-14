from dataclasses import dataclass, field

from pydantic import BaseModel, Field


##########
# Objects for LLM structured output
##########
class RepositoryInfo(BaseModel):
    owner: str = Field(
        description="The exact name of the owner of the repository. The owner may be a username or an organization name."
    )
    repository_name: str = Field(description="The exact name of the repository")

    branch: str = Field(
        default="main",
        description="The exact name of the branch of the repository, if not the main branch.",
    )


class CandidateFiles(BaseModel):
    top_file_pick: str = Field(
        description="Populate this field only if the helper is certain it has identified the file that answers the user's query. This should be the full path of the file within the git repo."
    )
    candidate_files: list[str] = Field(
        description="If the helper has a list of possible files that answer the user's query, list them here, in order of certainty, starting with most certain."
        "This should be the full path of the file within the git repo."
    )


##########
### Objects used for agent context
##########
@dataclass
class AnalyzerContext:
    goal: str = ""
    repo_details: RepositoryInfo = None
    github_search_output: list[dict] = field(default_factory=list)
