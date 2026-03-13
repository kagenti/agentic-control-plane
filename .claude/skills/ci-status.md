# CI Status

Check the CI pipeline status for a PR or branch.

## Check PR CI

```bash
gh pr checks <PR_NUMBER> --repo kagenti/agentic-control-plane
```

## Watch until complete

```bash
gh pr checks <PR_NUMBER> --repo kagenti/agentic-control-plane --watch
```

## View failed run logs

```bash
# Get run ID
gh run list --repo kagenti/agentic-control-plane --branch <branch> --limit 5

# View failed step logs
gh run view <RUN_ID> --repo kagenti/agentic-control-plane --log-failed
```

## Workflow files

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `ci.yml` | PR + push to main | Lint, test |
| `security-scans.yml` | PR | Dep review, Bandit, Hadolint, Trivy, CodeQL |
| `build.yml` | Tag push | Multi-arch container images to GHCR |
| `scorecard.yml` | Push to main + weekly | OpenSSF Scorecard |
| `stale.yml` | Daily | Close stale issues/PRs |
