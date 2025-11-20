import json


class AgentWorkflowError(Exception):
    """Raised when an unrecoverable issue occurs in the agent workflow."""


def extract_text_response(response, description: str) -> str:
    chat_history = getattr(response, "chat_history", None)
    if not isinstance(chat_history, list) or not chat_history:
        raise AgentWorkflowError(f"{description} returned an empty conversation.")

    try:
        content = chat_history[-1]["content"]
    except (TypeError, KeyError) as exc:
        raise AgentWorkflowError(f"{description} returned malformed content.") from exc

    if not isinstance(content, str) or not content.strip():
        raise AgentWorkflowError(f"{description} returned empty text content.")

    return content


def extract_json_response(response, description: str) -> dict:
    content = extract_text_response(response, description)
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise AgentWorkflowError(f"{description} returned invalid JSON.") from exc

    if not isinstance(parsed, dict):
        raise AgentWorkflowError(f"{description} returned JSON that was not an object.")

    return parsed
