# Production release gates and known gaps

This is a working implementation, not a completed production qualification or certification.

Continuation status (2026-10-25): see [verification record](../VERIFICATION.md) for current results. All 28 backend tests, the production build, contract parity, source/dependency scans and local restore drill pass. All 3 browser tests pass against rebuilt images, including durable diagnosis, retention cancellation and accessibility/responsive coverage. Fresh container scans still contain unresolved high/critical findings, so production release gates remain open.

| Gate | Current state | Next evidence required |
| --- | --- | --- |
| Telemetry → incident vertical slice | Implemented and integration/browser verified | Real SDK interoperability, sustained load, collector failure/backpressure and completeness measurements |
| Authentication / tenant isolation | Local flow, OIDC protocol fixture, negative API and actual DB-role/RLS tests pass | Target IdP/TLS/MFA/session rotation/outage tests; dedicated runtime accounts and policy deployment |
| Metadata privacy | Allowlist, nested/pattern privacy tests, one-time credential and no-secret browser/source checks | Organization privacy review, adversarial metadata-label review, scoped deletion and backup policy |
| Runtime privilege | Non-root, read-only app containers, dropped capabilities, pinned base digests; production startup checks roles/RLS/encrypted DB | Target ingress and service transport, egress policy, credential rotation, image CVE triage |
| Detection | Versioned thresholds, minimum samples, cooldown/grouping, durable jobs | Statistical detectors, SLO/burn-rate definitions and historical replay qualification |
| Diagnosis | Durable worker-backed deterministic partial failure localization with persisted hypotheses, source links and counterevidence | Deployment/config inputs, hypothesis review workflow, critical-path attribution and causal validation |
| Evaluations | Bounded immutable paired replay, exact-match grading, conservative interval/sample gate | Stable dataset multi-version lifecycle, live execution sandbox, task-specific graders, contamination and budget controls |
| Remediation | Proposals/rejection and all fail-closed authorization boundaries | Isolated executor and identities, allowlisted adapters, validated preconditions, independent approval persistence, expiry/concurrency, receipts, rollback and emergency-disable drills |
| Observability | Request IDs, safe error logs, queue/dead-letter counts, separate health endpoints | Platform metrics export, alerts, incident-routing outbox and measured operating SLOs |
| Recovery | Fresh migration parity/rollback tests and disposable local PostgreSQL dump/restore | Encrypted managed backup, real restore drill, operator-defined RPO/RTO and documented owner |
| UI | Six breakpoints, 16-route axe coverage, actual end-to-end workflow and screenshots | Supplied reference image comparison (image absent), screen-reader/manual usability audit, remaining target screens |
| Supply chain | Dependency locks and CI definition; Bandit, source/known-secret checks and dependency audits pass; fresh container scans contain unresolved high/critical base-image findings; web Node findings cleared | Resolve findings or obtain reviewed exceptions; sign artifacts and complete real protected CI/deployment run |

## Explicitly unavailable capabilities

- No live LLM/model runner, paid model integrations, arbitrary tool execution or automatic diagnosis narrative.
- No actual remediation validation/approval/execution/verification or rollback adapter. No action can reach VERIFIED through the supplied API.
- No SLO manager, EWMA/MAD detector, routing notifications, deployments integration, user invitation UI, self-service multi-organization switching, pricing catalog, billing inference, or advanced ClickHouse/Kafka infrastructure.
- No graph critical-path attribution beyond structural parent checks and root wall-clock accounting. Waterfalls display actual spans and missing-data issues.
- Dataset snapshots are immutable version-1 publications with unique IDs; stable-ID multi-version editing is not implemented.
- Hard limits are deliberately conservative. Scheduler handles at most 1,000 projects/pass; retention drains at most 1,000 expired traces/project/pass. High-scale behavior is not qualified.
- Trivy/container findings, if any, must be triaged in docs/VERIFICATION.md before release. Dependency audits do not cover the operating system.

## Deployment safety

The supplied Compose file is local development infrastructure. It shares a privileged development DB account and an ignored environment file, so it must not be reused as production configuration. Supply separate migration/API/worker/ingest connections, apply infra/runtime-roles.sql, and set the correct NEURALOPS_RUNTIME. Only the API receives identity/session secrets. Production startup also requires encrypted PostgreSQL transport and rejects owner/superuser/bypass-RLS and cross-runtime role membership.

A missing external credential or adapter is an unavailable state, not grounds to enable development auth or remove a policy check in production.
