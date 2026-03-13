# RCA: CI Failures

Systematic root cause analysis when CI fails.

## Step 1: Identify failing job

```bash
gh pr checks <PR_NUMBER> --repo kagenti/agentic-control-plane
```

## Step 2: Fetch failed logs

```bash
export LOG_DIR=/tmp/rca/$(date +%s)
mkdir -p $LOG_DIR
gh run view <RUN_ID> --repo kagenti/agentic-control-plane --log-failed \
  > $LOG_DIR/failed.log 2>&1
echo "Logs at $LOG_DIR/failed.log"
```

## Step 3: Analyze (use subagent to avoid context pollution)

```
Agent(Explore): "Grep $LOG_DIR/failed.log for ERROR|FAILED|error:|assert.
  Return: job name, first error, file and line if available."
```

## Common failure patterns

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `ruff check` fails | Import order or unused var | `make fmt` locally |
| `pytest` collection error | Bad import in test | Check `sys.path.insert` |
| `bandit` HIGH severity | Security issue in new code | Review flagged lines |
| `hadolint` warning | Dockerfile best practice | See DL code at hadolint.github.io |
| `dependency-review` fail | New dep with vulnerability | Pin to safe version or suppress |
| Trivy config CRITICAL | Misconfigured K8s manifest | Check RBAC, securityContext |
| CodeQL finding | Security vulnerability in code | Fix before merge |
