# NeuralOps implementation progress

Status: audited against `Design.md`, `Architecture.md`, `Component.md`, `Security.md`, and `Flow.md` on 2026-10-25. This is an implementation-status record, not a production-readiness claim. Executed evidence is recorded in `docs/VERIFICATION.md`.

## Phase status (0–7)

### Phase 0 — foundation and threat model — FULLY IMPLEMENTED
- [x] Next.js/TypeScript web, FastAPI control API, PostgreSQL migrations, worker, and authenticated OTLP/HTTP gateway.
- [x] Modular-monolith boundaries, seven ADRs, threat model, release gates, generated OpenAPI contract, and local Compose topology.
- [x] Bounded bodies/windows/queues, metadata allowlist, append-only audit records, and hardened local containers.

### Phase 1 — secure first working vertical slice — FULLY IMPLEMENTED
- [x] Local development session and production OIDC Authorization Code + PKCE implementation.
- [x] Server-side tenant/project authorization, CSRF/origin checks, RLS/runtime-role checks, one-time hashed ingestion credentials, rotation by revoke/reissue, and retention policy.
- [x] Create project → issue credential → ingest OTLP → reconstruct trace → measured dashboard/detail workflow.
- [x] Integration and browser coverage for revocation, idempotency, unordered spans, missing parents, cycles, redaction, project cache isolation, stale refresh, and retention.

### Phase 2 — detection and evidence-based investigation — FULLY IMPLEMENTED
- [x] Versioned threshold, EWMA, and robust median/MAD rules for measured error-rate and latency signals, with minimum samples, bounded windows, dry-run preview, configurable sensitivity, cooldown/grouping, and incident lifecycle.
- [x] Durable, idempotent detection records preserve normal, anomalous, and insufficient-data outcomes separately from incidents; PostgreSQL jobs, leases, per-project serialization, queue bounds, and uniqueness constraints tolerate concurrent redelivery.
- [x] Configurable success-rate and latency SLOs calculate eligible samples, compliance, remaining error budget, and short/long-window burn rates from actual trace records; sparse windows stay `INSUFFICIENT_DATA`.
- [x] Trace reconstruction persists a parallelism-aware critical path. Durable RCA correlates observed dependency edges and explicitly recorded deployment/configuration changes, ranks hypotheses, and persists supporting and contradicting evidence, coverage, missing measurements, and algorithm version.
- [x] Detection Rules, SLO Management, trace critical-path, and incident RCA/change-recording interfaces use generated API types and implement loading, empty, error, authorization, responsive, and accessible states.
- [x] Dedicated Rule Builder (`/rules/new`), dedicated Rule Editor (`/rules/:id/edit`), immutable rule version history inspection, safe rule deletion with incident guards (409 `RULE_IN_USE`), and tenant/incident-scoped operator investigation notes (`/incidents/:id/notes`).

### Phase 3 — reproducible evaluations — PARTIALLY IMPLEMENTED
- [x] Immutable bounded datasets, manifest hashes, paired replay exact-match grading, durable jobs, per-case results, conservative paired interval, and `INCONCLUSIVE` sample gate.
- [x] Stable root dataset identity with multiple immutable versions, scoped lineage constraints, unique version numbers, serialized publication, and version-pinned evaluations.
- [x] Allowlisted exact-match/strict JSON-validity replay graders, bounded literal safety checks, supplied latency/token guardrails, duplicate-input checks, and audited finished-run exports with reproducible public-JSON checksums.
- [x] Missing guardrail measurements remain unknown and prevent PASS; explicit guardrail failures fail regardless of sample size. Replay repeats above one are rejected rather than counted as independent runs.
- [ ] Independently isolated baseline/candidate live execution, actual repeat execution, training/tuning contamination provenance, measured latency, monetary cost/pricing, and external model-call/concurrency budgets. The prior subprocess runner was unsafe and is now fail-closed at API, worker, and runner boundaries; no submitted code executes.

### Phase 4 — approval-controlled remediation — PARTIALLY IMPLEMENTED
- [x] Immutable scoped proposal, manifest hash, TTL, idempotency, rejection, independent-role/hash checks, audit, and fail-closed approve/execute endpoints.
- [ ] Validation/dry-run adapter, persisted independent approvals, isolated executor identity/service, precondition and target-version checks, receipts, post-checks, rollback, kill switch, and recovery drills.
- [x] Remote target mutation remains disabled until all required controls exist.

### Phase 5 — product surface and administration — PARTIALLY IMPLEMENTED
- [x] Live-data Command Center, system health/service map, trace explorer/detail, model/tool/token analytics, rules, incidents, evaluations, datasets, remediation queue, projects/instrumentation, keys, audit, and retention settings.
- [x] Loading/empty/error/forbidden handling, conspicuous synthetic-project `DEMO` banner, mobile navigation, responsive layouts, keyboard focus handling, and no fabricated pricing.
- [x] Dedicated `/slos` objective management, compliance, error-budget, burn-rate, and reliability-trend experience.
- [ ] Dedicated `/team`, `/onboarding`, dataset-version, remediation-history, evaluation wizard, and project wizard experiences.
- [ ] Saved trace views, full filters, deployment/anomaly panels, notification settings, self-service membership management, dataset export, and incident bulk actions.
- [ ] The specified reference image is absent; exact visual comparison remains impossible. Captured 375/430/768/1024/1440/1920 layouts match the documented dark token system and do not overflow in automated checks.

### Phase 6 — security and operational hardening — PARTIALLY IMPLEMENTED
- [x] BOLA/RLS negative tests, production config fail-closed checks, SAST, dependency/secret scans, restore drill, non-root/read-only containers, dropped capabilities, and pinned base digests.
- [x] 2026-10-25 fix: project-limited operators/approvers can no longer query organization-wide audit records; audit events now carry canonical project scope and the API requires/authorizes that scope for non-admins.
- [ ] Load/backpressure/collector interoperability tests, platform metrics export and alerting, sustained fault tests, encrypted backup automation, egress/network policies, and independent penetration/accessibility reviews.
- [x] Rechecked all pinned upstream image tags on 2026-10-25. Replaced PostgreSQL's vulnerable Go-based `gosu` binary with Alpine `su-exec` in a flattened, tested image while preserving the upstream entrypoint contract.
- [ ] Debian backend/web OS findings remain open: the rebuilt, upgraded pinned images have no vendor-fixed versions for their reported high/critical packages. No exception has been accepted.

### Phase 7 — production qualification and release — MISSING / NOT QUALIFIED
- [ ] Target IdP/TLS/MFA and session-rotation/outage evidence.
- [ ] Dedicated production runtime accounts, encrypted database/service transport, secret-manager rotation, ingress/egress policy, encrypted backups, RPO/RTO and restore evidence.
- [ ] Clean container vulnerability gate or documented reviewed exceptions, load/SLO evidence, manual screen-reader/keyboard review, incident-response ownership, signed release/deployment rollback evidence, and remediation recovery drill.

## Verified gaps and honest capability boundaries

- The OTLP gateway is an application adapter accepting JSON and protobuf, not a deployed upstream OpenTelemetry Collector distribution; production collector interoperability and load shedding are unqualified.
- Critical path is a deterministic hierarchy-based inference over recorded span timing; malformed/incomplete graphs explicitly report unavailable attribution.
- Hypotheses are deterministic advisory localization over at most 5,000 linked spans. Deployment/configuration correlation is temporal evidence, never a causal claim; controlled causal experiments remain an evaluation/remediation concern.
- Evaluation is offline replay of supplied outputs; it does not execute a model or arbitrary fixture code.
- Remediation approval/execution buttons are intentionally disabled and explained. No remote executor, webhook, shell, or cloud connector exists.
- Cost remains unavailable without a pricing source. No billing totals or confidence percentages are fabricated; SLO and change records are user-configured and calculated from retained telemetry.
- Several specification URLs resolve through shared screens, but dedicated workflows are incomplete: `/evaluations/new`, `/datasets/:id`, `/remediations/history`, `/projects/new`, `/team`, and `/onboarding`.

## Next priorities

1. Continue Phase 3 with an independently isolated executor boundary, credential/filesystem/network denial tests, total run deadlines, and concurrency/model-call budgets before enabling any live evaluator. Stable multi-version replay datasets are implemented.
2. Add measured task/safety/latency/monetary-cost provenance, real repeat execution and training/tuning overlap evidence; expose dataset-version and evaluator configuration workflows in the UI. Existing replay checks operate on supplied fixtures only.
3. Build remediation validation/approval persistence independently of execution; do not enable execution until the isolated adapter, rollback, verification, and kill-switch drills pass.
4. Close remaining Debian image findings through vendor-fixed base updates or documented reviewed exceptions; do not suppress the vulnerability gate.
5. Close Phase 7 target-infrastructure identity/TLS/backup, sustained-load, manual accessibility, signing, and rollback evidence.

## Resume audit — 2026-10-25

The source directory has no Git metadata; commits, diffs, and agent attribution cannot be reconstructed. Reviewed all seven specification/status documents, migrations, backend tests, frontend checks and existing browser journeys. See `docs/RESUME_AUDIT.md` for the inspected changes, repaired conflicts, preserved baseline and current handoff. Existing rule editor/builder, soft deletion and incident notes remain implemented. Notes now have a database immutability trigger and are included in the production RLS startup gate.
