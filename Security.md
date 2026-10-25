# NeuralOps — Security Specification & Protocols

> **Vulnerability Reporting:** For reporting security vulnerabilities and responsible disclosure guidelines, please see [.github/SECURITY.md](.github/SECURITY.md).

**Rule:** Security requirements are implementation gates, not decorative UI. This document defines a target security model; it does not claim NeuralOps is currently secure or certified. Align design with OWASP ASVS, OWASP API Security Top 10, OWASP LLM guidance, applicable OpenTelemetry security recommendations and deployment policy. Verify exact library/standard versions before implementation.

## 1. Assets, attackers and trust boundaries
Protect identity/session tokens, ingestion credentials, organization/project metadata, telemetry (may include prompts, PII and secrets), incident evidence, evaluation datasets, audit events, and remediation authorities. Threats: unauthenticated internet clients, malicious tenants, compromised SDK producers, internal users exceeding their role, poisoned trace text, compromised worker dependencies, and SSRF/privilege escalation via integrations.

Trust boundaries: user browser ↔ authenticated API; customer workload ↔ authenticated Collector; collector ↔ ingestion processor; API/worker ↔ database; evaluation worker ↔ untrusted fixtures/tools; remediation controller ↔ isolated action executor; tenant A ↔ tenant B. Draw a separate data-flow threat model for each in `docs/security/threat-model.md`.

## 2. Identity, sessions, authz
- Web sign-in via OIDC Authorization Code + PKCE; only trusted redirect URIs; validate issuer, audience, signature, state, nonce and expiry. Favor backend-managed sessions with Secure, HttpOnly, SameSite cookies and CSRF protection on state changes; never store long-lived access tokens in localStorage.
- Production APIs authenticate every request. Distinguish user sessions from service credentials. Rotate/revoke credentials and enforce expiry. Require MFA through the identity provider for administrative accounts where supported.
- Roles: Viewer (read permitted telemetry), Developer (run evaluations/configure their projects), Operator (incident/workflow actions), Admin (members/keys/settings), Remediation Approver (explicit permission), Executor Service (machine identity only). Privileged scopes can be distinct from roles.
- Authorization: resource-aware deny-by-default policies; `organization_id` and `project_id` constrained server-side; protect object IDs (BOLA), function permissions (BFLA), field redaction and list query filtering. RBAC plus contextual checks on environment/action type. Prefer independent approver for production remediations.
- Validate session termination, credential revocation propagation, role changes and cross-org access in integration tests.

## 3. Network and secrets
- TLS 1.2+ or newer supported deployment policy at ingress; prefer TLS 1.3, HSTS on HTTPS domains. mTLS between services/collectors where feasible, otherwise authenticated encrypted transport with narrowly scoped network access.
- Deny public exposure of databases, queues, workers or executor endpoints. Enforce ingress restrictions, network policies and egress allowlists for high-risk workers.
- Credentials in secret manager or deployment secret store, not Git, images, frontend bundles, telemetry, error pages or screenshots. Rotate with planned overlap; redact logs. No secret interpolation into downloadable client snippets unless one-time controlled handoff is needed.
- Database least-privilege credentials separated by API, worker, migration and analytics roles. Encryption at rest via managed disk/database capabilities plus encrypted backups and key rotation policy.

## 4. Telemetry privacy and ingest controls
- **Default: metadata-only**. Prompt, response bodies, tool inputs, retrieved documents, headers and full exception payloads are excluded or redacted unless explicitly opted in by an authorized organization admin.
- Ingest credential bound to organization/project/environment and allowed data types; never trust `organization_id` emitted by SDK. Credential lookup supplies canonical scope.
- OTLP gateway: auth, TLS, bounded message size, rate limit, attribute count/length caps, collector memory limiter, retry/backoff, batching and circuit-breaker/load-shedding rules. Record dropped/rejected counts. Implement SDK backpressure so monitoring never stops the customer app.
- Redact at producer when possible and again before persistence. Test nested JSON, base64-like tokens, common secret patterns, HTTP headers, PII and adversarial field names. Regex alone is insufficient; maintain explicit allowlists for high-risk attribute groups.
- Per-tenant quotas, storage limits, retention/deletion with legal retention exception policy if applicable, logs of policy changes and deletion verification. Exported reports inherit data classification.

## 5. Application/API protections
- Strict Pydantic schema validation, typed identifiers, max input sizes, allowlisted sorting and filtering; parameterized SQL via safe query builder/ORM; HTML rendering escapes user content. Sanitize Markdown and JSON rendered into the UI.
- Cookie sessions: CSRF tokens / origin checks for mutations; correct CORS allowlist; avoid permissive wildcards with credentials. Limit login, search, export, ingest and job-start rates by tenant and credential; use quotas for expensive queries.
- Cursor pagination, query timeouts, constrained time windows and row limits prevent denial of service. Every error has stable code and request ID; no stack traces, SQL strings or secrets in client response.
- SSRF: connectors and webhooks must use destination allowlists or verified host policy, block private/metadata IP ranges and DNS rebinding, timeout connections, cap redirects and payloads. Treat user-supplied URLs as hostile.
- Signed object downloads or short-lived scoped URLs; no public datasets by default; integrity/hash for immutable artifacts.

## 6. Evaluation and AI-specific security
- Evaluation fixtures and trace text are untrusted **data**, not operational instructions. Any LLM explanation uses read-only, minimum-necessary evidence and must not receive secrets, unrestricted tools or broad network access.
- Tool outputs, documents and prompt content may contain prompt injection. Never let LLM-generated text authorize or directly invoke remediation. Separate deterministic policy controller from explanation model.
- Sandbox evaluation executors: bounded CPU/memory/time, read-only filesystem where practical, disposable workspace, no production credentials, restricted network, immutable dataset and configuration version manifests. Limit model budgets and concurrent runs.
- Detect/record contamination between benchmark and tuning sets; evaluation results store grader version, dataset version and relevant model/configuration metadata.
- LLM response is an untrusted proposal; validate typed structure and attach evidence references. Show 'insufficient evidence' rather than inventing confidence.

## 7. Remediation action protocol
1. Proposal references exact incident and evidence identifiers, action type, target project/environment, immutable action parameters hash, expiry and rollback plan.
2. Validate action against server-side allowlist and scoped operator permissions. Dry-run/precondition checks gather data without mutating the target.
3. Approval is explicit, recorded with approver identity, timestamp and **exact manifest hash**. Use segregation of duties for production actions where policy requires it.
4. Before execute, revalidate approval, expiry, target version, preconditions, idempotency key, environment, policy and executable action type. Fail closed on mismatch.
5. Action executor is a separate service identity with narrow rights, outbound allowlist, timeout, concurrency limits and kill switch. **No arbitrary shell commands, repository-wide secrets or unrestricted kubectl**.
6. Record signed/verified action receipt when available, verify health after execution and move to VERIFIED only on evidence. Otherwise FAILED or ROLLBACK_PENDING; rollback is itself allowlisted/authorized.
7. Idempotency, compare-and-swap state updates and locking prevent concurrent double execution and stale-approval races.

## 8. Auditing, monitoring, incident response
Audit: login/auth failures, role/credential changes, policy updates, data exports, dataset publishing, evaluation launch, remediation proposal/approval/execution/rollback, deletion. Include actor, scoped target, action, outcome, request/correlation ID, timestamp, minimal context; avoid secret-bearing payloads. Use append-only storage semantics; protect from standard application mutation roles. Monitor unusual export volume, privilege changes, repeated denied actions, redaction failures, executor errors and abnormal ingestion. Maintain incident response runbooks for credential compromise, tenant leak, poisoned telemetry, evaluation sandbox breach and unsafe remediation.

## 9. CI/CD and supply chain
- Branch protection and reviewed pull requests for privileged code; tests, lint/types, secret scan, dependency and container vulnerability scan, SAST and IaC scan as applicable.
- Pinned dependencies and lockfiles; generate SBOM, triage CVEs, minimize base images, non-root containers, no unnecessary Linux capabilities, drop privileges and immutable image tags for deployments.
- Production deploy uses short-lived credentials (e.g., OIDC federation where supported), signed release artifacts when infrastructure supports it, documented rollback and separation of build from deploy rights.
- Never auto-merge security changes or bypass CI based on an AI-generated success statement.

## 10. Verification matrix and release gate
| Control | Required test |
|---|---|
| Tenant isolation | API IDOR/BOLA and DB-scoped cross-tenant negative integration tests |
| Auth/session | invalid/expired/missing token, logout, CSRF, role downgrade |
| Credential handling | revoked key rejected, scope mismatch, expired key, redaction |
| Input safety | injection strings, malformed protobuf/JSON, oversized attributes, XSS payloads |
| Telemetry privacy | payloads blocked by default, opt-in controlled, post-redaction persistence checks |
| Resource abuse | rate limiting, query range limits, queue saturation, controlled rejection |
| Evaluator sandbox | time/resource/network isolation and secret non-access |
| Remediation | stale approval, changed payload, double-submit, wrong role, failed precondition, rollback |
| Audit | all sensitive operations logged without secrets, standard users cannot mutate logs |
| Recovery | backup restore and emergency executor disable drills |

Phase 2 security verification (2026-10-25): detections, SLOs, snapshots and change events have composite tenant/project foreign keys, forced PostgreSQL RLS policies and least-privilege API/worker grants. New write endpoints require admin/operator/developer roles, project scoping, strict schemas, bounded time windows/quotas and append-only audit events; cross-project and viewer-write negative tests cover the new resources. Worker inputs are measured database records, not executable change content. Remediation execution remains disabled.

Container triage replaced PostgreSQL's fixable vulnerable Go `gosu` helper with packaged `su-exec` while retaining the entrypoint contract and healthy migration/startup behavior. Backend/web Debian findings with no published vendor fixed version remain release-blocking risks; they are neither ignored nor allowlisted.

**Release criteria:** no untriaged critical security findings, key authorization/tenant-negative tests passing, secrets absent from builds/log fixtures, remediation dry-run and rollback tested, documented backup restoration and security response owner. Track risks and exceptions explicitly. No claim of compliance certification without an actual audit.
