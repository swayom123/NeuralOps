# NeuralOps threat model

Scope: delivered local vertical slice and bounded later-phase capabilities. See Security.md for the target model and release-gates.md for unfulfilled deployment controls.

| Boundary / attacker | Data and threat | Enforced controls | Remaining qualification |
| --- | --- | --- | --- |
| Browser → web/API; anonymous or compromised user | Session theft, CSRF, XSS, resource abuse | Opaque hashed server sessions; expiry/logout; HttpOnly cookie; Secure in production; exact-origin + token CSRF; escaped React rendering; nonce CSP; bounded body/time/query; shared quotas | Real IdP/TLS deployment, MFA enforcement and independent penetration test |
| IdP → API callback | Forged ID tokens, state/nonce/code replay | Authlib code + S256 PKCE; signed discovery/JWKS ID-token validation; issuer/audience/expiry/nonce/state checks; pre-provisioned subject; consumed callback state | Fixture protocol tests pass; actual provider, rotation and outage qualification remain |
| Tenant A → tenant B / another project | BOLA/BFLA and accidental unscoped SQL | Server-derived organization; role and project policies; scoped resource lookup; Postgres RLS under API role; composite project/resource foreign keys; negative integration tests | Real deployment role/account provisioning and review of new queries on every feature |
| Customer SDK → OTLP gateway | Forged tenant claim, secrets in spans, oversized/nested payloads, duplicates | Canonical scope from hashed credential; immediate revocation check under lock; JSON/protobuf limits; explicit metadata allowlist; label validation; bounded quota/backlog; transactional spans + jobs; idempotent insert/upgrade | Ingress connection/IP limits, TLS, collector interoperability/load shedding qualification; labels remain untrusted producer text and cannot guarantee identification of every possible secret |
| Gateway/API → PostgreSQL | Cross-scope writes, SQL injection, credential leakage | Parameterized SQLAlchemy; immutable audit/dataset/version/manifest triggers; role-specific SQL grants; RLS context; random development secrets outside source; no secrets in browser build | Production encrypted storage, managed rotation, IAM and network restrictions |
| Worker → stored jobs/telemetry | Job redelivery, crash, poisoned evidence | SKIP LOCKED leases; compare attempt/state; transactional handlers; retries/dead letter; project advisory lock; no LLM or executable telemetry; bounded evidence and honest partial localization | Queue/load SLOs and controlled fault/load testing; scheduler scale above 1,000 projects |
| Fixture upload → evaluator | Prompt injection, arbitrary code, network exfiltration, cost abuse | Bounded typed immutable strings; exact-match equality only; no eval/exec, shell, network or model call; pinned manifest; paired case results and conservative decision gate | Live runners require a separate disposable CPU/memory/time/network sandbox; not enabled |
| Proposal → approval/executor | Stale/changed action, privilege escalation, double execution | Immutable exact manifest; scoped role/hash/TTL/independent identity guards; durable idempotency; no VALIDATED transition or executor supplied; approval/execute fail closed; rejection audited | Real allowlisted target adapters, independent machine identity, health preconditions/receipts, rollback, kill switch drills; no execution authorized by model text |
| Persistence → retention/backup | Sensitive data held beyond policy, expired evidence, recovery failure | Metadata minimization; configurable retention; bounded worker deletion; 410 tombstones; local disposable restore verified | Backlog monitoring/SLA, tombstone/audit/dataset deletion policy, encrypted durable backups, restore drills in target infrastructure and defined RPO/RTO |

## Trust decisions

- Development sign-in is intentionally passwordless only when explicitly enabled, origin is loopback, the caller is on the local/private control network, and environment is not production. Compose binds ports only to loopback. Never expose this topology on a shared network or tunnel. Production refuses development auth.
- Membership role and project IDs are loaded afresh for each authenticated request. Frontend navigation is not authorization. API session loss clears the browser view; project changes remount scoped state. No tenant data or bearer credential is cached in localStorage.
- The API role cannot mutate audit or dataset history; database triggers also protect these records from ordinary owner-mediated writes. A database provisioning administrator remains privileged and can alter policies; use separate operational authority and backups.
- The trusted worker intentionally reads across organizations to claim jobs and enforce retention. It cannot read membership/session contents or credential verifiers through its runtime role, and has no production action or model credential.
- No external URL connector or webhook is implemented. The only identity destination comes from trusted deployment configuration. The web proxy has a fixed operator-configured upstream and allowlisted forwarding headers.

## Response runbooks

Credential compromise: revoke the affected ingestion credential as admin; verify new ingest is rejected; issue a new one through the one-time handoff; inspect audit and span metadata; rotate any accidentally emitted workload secret at its source.

Tenant leak suspicion: stop affected API ingress, preserve minimal audit identifiers, disable impacted sessions/memberships through deployment administration, verify SQL role/RLS configuration, investigate query scope and caches, and follow the organization's notification policy. Do not export raw customer evidence to an LLM.

Poisoned telemetry: revoke the producer key, stop downstream processing for the affected project through operational controls, preserve IDs and redacted evidence only, review allowlist and label handling, and verify new ingestion with adversarial fixtures before reenabling.

Evaluator breach: current grader has no code/network/tool execution. If a future sandbox is compromised, terminate it, revoke its isolated credentials, preserve manifests/receipts, and keep remote runners disabled until isolation is requalified.

Unsafe remediation: remote execution is disabled in this release. Never change database states or add a broad shell adapter to bypass validation. Future executor installation must include a separate emergency disable mechanism and an exercised target-specific rollback.
