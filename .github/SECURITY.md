# Security Policy

## Supported Versions

NeuralOps is actively maintained. Security patches are applied to the `main` branch.

| Version | Supported          |
| ------- | ------------------ |
| `main`  | :white_check_mark: |
| < 0.2.0 | :x:                |

## Reporting a Vulnerability

The NeuralOps team takes the security of our control plane, telemetry ingestion pipelines, and multi-tenant isolation seriously. If you believe you have discovered a vulnerability, please report it responsibly.

### Responsible Disclosure Guidelines

- **Do NOT file public GitHub issues for security vulnerabilities.**
- Report security findings privately via **GitHub Private Vulnerability Reporting** on the repository or via email to the maintainer (`swayom123` via GitHub profile).
- Include detailed steps to reproduce the issue, proof of concept (PoC) if available, and any relevant logs or error codes.
- Do not attempt to access, modify, or delete tenant data without authorization.
- Please give maintainers a reasonable window (standard 90 days or until a patch is released) to triage and resolve the issue before public disclosure.

### Response SLA

- **Initial Acknowledgment:** Within 48 hours.
- **Triage and Impact Assessment:** Within 5 business days.
- **Patch & Advisory:** Timelines depend on severity, with critical issues addressed expeditiously.

## Security Model & Technical Specification

For the complete technical threat model, trust boundaries, tenant isolation protocols, and verification gates, refer to [Security Specification (Security.md)](../Security.md) and [docs/security/threat-model.md](../docs/security/threat-model.md).

### Core Architectural Invariants

1. **Metadata-Only Default:** Ingestion normalizes and retains only allowlisted metadata and numeric usage metrics. Prompts, completions, tool inputs/outputs, headers, and full exception bodies are dropped prior to persistence.
2. **Deterministic Control:** AI hypotheses and failure localizations are strictly advisory failure localization with counterevidence. Automated remediation remote execution is deliberately disabled by default.
3. **Tenant & Project Isolation:** All storage records enforce composite tenant/project keys and PostgreSQL Row-Level Security (RLS) with dedicated runtime roles (`neuralops_api`, `neuralops_ingest`, `neuralops_worker`).
4. **Credential Segregation:** Ingestion keys store only SHA-256 verifiers. OTLP gateway credentials cannot access the control plane API or console, and user sessions cannot ingest telemetry.
