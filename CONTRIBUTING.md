# Contributing to agentic-control-plane

Thank you for contributing! This guide covers how to set up your development
environment, run tests, and submit pull requests.

## Development Setup

### Prerequisites

- Python 3.10+ (`k8s_debug_agent` requires ≥3.10; `a2a_bridge_server` requires ≥3.12; CI tests with 3.11 and 3.12 respectively)
- [`uv`](https://docs.astral.sh/uv/) — package and virtualenv manager
- [`pre-commit`](https://pre-commit.com/) — local quality gates

### Getting started

```bash
# Clone the repo
git clone https://github.com/kagenti/agentic-control-plane.git
cd agentic-control-plane

# Install pre-commit hooks (run once)
pre-commit install

# Install dependencies for a specific subproject (subshells keep you at repo root)
(cd tools/a2a_bridge_server && uv sync --frozen --extra dev)
(cd agents/k8s_debug_agent && uv sync --frozen --extra dev)
```

## Project Structure

```
agentic-control-plane/
├── agents/
│   ├── k8s_debug_agent/       # AG2-based K8s debugging agent (A2A)
│   └── source_code_analyzer/  # AG2-based source code analysis agent (A2A)
├── tools/
│   ├── a2a_bridge_server/     # MCP-to-A2A bridge (agent discovery + invocation)
│   └── k8s_readonly_server/   # K8s read-only MCP tool server
└── deploy/                    # Kubernetes manifests (kustomize)
```

## Running Tests

Each subproject has its own test suite managed with `uv`:

```bash
# a2a bridge server
(cd tools/a2a_bridge_server && uv run pytest tests/ -v)

# k8s debug agent
(cd agents/k8s_debug_agent && uv run pytest tests/ -v)
```

## Running Lint and Format Checks

```bash
# Run all pre-commit hooks on staged files
pre-commit run

# Or run on all files
make lint

# Auto-format
make fmt
```

## Pull Request Process

1. **Fork** the repository and create a feature branch from `main`:
   ```bash
   git checkout -b feat/my-feature main
   ```

2. **Make your changes** with accompanying tests.

3. **Run checks locally** before pushing:
   ```bash
   pre-commit run --all-files
   (cd tools/a2a_bridge_server && uv run pytest tests/ -v)
   (cd agents/k8s_debug_agent && uv run pytest tests/ -v)
   ```

4. **Commit** with a DCO sign-off (required — see below):
   ```bash
   git commit -s -m "feat: describe your change"
   ```

5. **Push** and open a pull request against `main`. Fill in the PR template
   and link any related issues.

6. **CI must pass** before a PR can be merged. Address any failures before
   requesting review.

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/) format:

| Prefix | When to use |
|--------|-------------|
| `feat:` | New feature or capability |
| `fix:` | Bug fix |
| `docs:` | Documentation only |
| `refactor:` | Code restructuring without behavior change |
| `test:` | Adding or updating tests |
| `chore:` | Build, tooling, or dependency updates |
| `ci:` | CI/CD workflow changes |

Examples:
```
feat: add streaming support to a2a bridge
fix: handle missing Synced condition in AgentCard CRD
docs: update README with Kind deployment steps
```

## DCO Sign-Off (Required)

All commits must include a Developer Certificate of Origin sign-off:

```bash
git commit -s -m "feat: my change"
# Adds: Signed-off-by: Your Name <your@email.com>
```

Pull requests without DCO sign-off will fail the DCO check in CI.
To retroactively sign off all commits on your branch:

```bash
git rebase --signoff main
```

## Code Style

- **Python 3.10+** with type hints where practical
- **Ruff** for linting and formatting (line length: 100, target: Python 3.10)
- Pre-commit hooks enforce style automatically on commit

## Reporting Bugs

Open a [GitHub Issue](https://github.com/kagenti/agentic-control-plane/issues/new)
with:
- A clear description of the problem
- Steps to reproduce
- Expected vs. actual behavior
- Relevant logs or error messages

For **security vulnerabilities**, see [SECURITY.md](SECURITY.md) — do not
open a public issue.
