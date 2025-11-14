## Source Code Analyzer Agent

The Source Code Analyzer is an [A2A](https://github.com/a2a) compatible agent that takes a log or
error message plus a GitHub repository hint and returns the most likely source file(s) that caused
the failure. It uses the ag2 runtime, GitHub’s MCP tools for repository access, and a lightweight,
locally-deployable LLM so it can run on a laptop or inside automation.

---

### Highlights
- Maps stack traces or free-form logs to concrete files inside a GitHub repo, returning reasoning
  and evidence.
- Streams status updates and a final artifact over the A2A protocol for UI consumption.
- Uses a staged agentic workflow (repo identifier → code search → summarizer → reporter) to minimize
  token use and GitHub API calls.
- Works with small local models (default `gpt-oss:20b`) and any MCP server exposing `search_code`
  and `get_file_contents`.

---

### Architecture Overview
1. **`a2a_agent.py`** boots the HTTP server exposed through Starlette, registers the agent card, and
   wires request handling, event streaming, and optional MCP connectivity.
2. **`SourceCodeAnalyzer` (`source_code_analyzer/main.py`)** orchestrates the workflow:
   - Extracts the latest user message.
   - Uses the **Repo Identifier** agent to normalize `{owner, repo, branch}`.
   - Invokes the **Code Search Assistant** (with MCP `search_code`) to gather likely files.
   - Runs the **File Search Summarizer** to produce a structured list of candidates.
   - Fetches file contents via the **File Retrieval Assistant** when more evidence is required.
   - Hands the gathered context to the **Report Generator**, which produces the final explanation.
3. **`Agents` (`source_code_analyzer/agents.py`)** configures the individual ConversableAgents,
   applies the prompts in `prompts.py`, and optionally scopes MCP tools to specific assistants.
4. **Events** (`source_code_analyzer/event.py`) abstract status reporting so the agent can either log
   to stdout or push updates to the A2A event queue.

---

### Prerequisites
- Python **3.10+** (3.12 recommended)
- [uv](https://github.com/astral-sh/uv) for dependency management, or `pip`
- Access to a GitHub MCP server (e.g., `githubcopilot` MCP) plus a token with repo read scope
- An OpenAI-compatible API (local or hosted) that serves the configured `TASK_MODEL_ID`

---

### Running Locally
```bash
cd agents/source_code_analyzer

# 1. Configure environment variables
cp .env.template .env
# edit .env to set LLM_API_KEY, MCP_URL, MCP_TOKEN, etc.

# 2. Install dependencies (creates .venv via uv)
uv sync

# 3. Run the A2A server locally
uv run server 
```
The process exposes the agent card at `http://localhost:8000/` and listens for A2A tasks. Point your
A2A coordinator/UI to that URL and submit a task whose text includes the log snippet plus a GitHub
repo identifier, for example:
```
"Find the file causing 'ValueError: bad config' in kagenti/agent-examples."
```

---

### Configuration
All settings are managed through environment variables defined in `.env`. Key options:

| Variable | Description |
| --- | --- |
| `TASK_MODEL_ID` | Model name passed to ag2 (default `gpt-oss:20b`). |
| `LLM_API_BASE` | OpenAI-compatible base URL (Ollama, vLLM, etc.). |
| `LLM_API_KEY` | API key for the model endpoint. |
| `MODEL_TEMPERATURE` | Sampling temperature for every agent. |
| `EXTRA_HEADERS` | JSON string of extra HTTP headers for the LLM client. |
| `MCP_URL` | URL of the GitHub MCP server exposing search/file tools. |
| `MCP_TOKEN` | Bearer token (e.g., GitHub PAT) forwarded to the MCP server. |
| `MAX_FILES_TO_RETRIEVE` | Upper bound on full file downloads per task. |
| `LOG_LEVEL` | Python logging level. |
| `SERVICE_PORT` | Port used when running the bundled A2A server. |

`config.py` loads these values via `pydantic-settings`, so any env var (shell export, container env,
or `.env`) will be respected.

