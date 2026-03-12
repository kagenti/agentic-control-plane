# Commit Conventions

## Format

```
<type>(<scope>): <short description>

[optional body]

Signed-off-by: Your Name <email>
Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
```

## Types

- `feat`: new feature or agent capability
- `fix`: bug fix
- `chore`: maintenance, deps, config
- `docs`: documentation only
- `test`: test additions or changes
- `refactor`: code restructuring without behavior change

## Scopes

- `agents/k8s-debug` — k8s debugging agent
- `agents/src-analyzer` — source code analyzer agent
- `tools/a2a-bridge` — A2A-to-MCP bridge
- `tools/k8s-readonly` — K8s read-only tool server
- `deploy` — Kubernetes manifests

## Rules

- DCO sign-off required: `git commit -s`
- Subject line ≤ 72 chars
- No Co-Authored-By; use Assisted-By for AI assistance
