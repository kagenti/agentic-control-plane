# Security Policy

## Reporting a Vulnerability

**Do NOT open a public GitHub issue for security vulnerabilities.**

Please report security vulnerabilities through GitHub Security Advisories:

**[Report a vulnerability](https://github.com/kagenti/agentic-control-plane/security/advisories/new)**

Include as much detail as possible:
- A description of the vulnerability and its potential impact
- Steps to reproduce or a proof-of-concept
- Affected versions or components
- Any suggested mitigations (optional)

## Response Timeline

| Stage | Target |
|-------|--------|
| Acknowledgment | Within 48 hours |
| Initial assessment | Within 7 days |
| Fix or mitigation | Based on severity (critical: ≤7 days, high: ≤30 days) |
| Public disclosure | Coordinated with reporter after fix is available |

## Security Controls

This repository employs the following security measures:

- **CI security scanning**: Trivy (filesystem + IaC), CodeQL, Bandit (Python SAST)
- **Dependency updates**: Dependabot monitors GitHub Actions, pip, and Docker dependencies weekly
- **OpenSSF Scorecard**: Weekly supply-chain health reporting
- **Pre-commit hooks**: Local lint and format checks before commits reach CI
- **Action pinning**: All GitHub Actions are pinned to full commit SHAs
- **Least-privilege CI**: Each workflow job declares only the permissions it needs

## Supported Versions

This project is under active development. Security fixes are applied to the
latest version on the `main` branch.

## Scope

In-scope for vulnerability reports:
- Source code in `agents/`, `tools/`
- CI/CD workflow configurations in `.github/workflows/`
- Kubernetes manifests in `deploy/`

Out of scope:
- Vulnerabilities in third-party dependencies (report upstream; Dependabot will track these)
- Issues already publicly disclosed in the [Security Advisories](https://github.com/kagenti/agentic-control-plane/security/advisories)
