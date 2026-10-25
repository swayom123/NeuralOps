# Technical decisions

## ADR-001 — modular monolith, separate processes
Preserve Next.js + FastAPI + PostgreSQL from Architecture.md. API, OTLP gateway and worker share domain modules but run separately. Keep infrastructure small; do not introduce Kafka, Redis, ClickHouse or LLM dependencies without workload evidence.

## ADR-002 — OTLP boundary
Customer telemetry enters the authenticated gateway on port 4318 using standard `/v1/traces` OTLP/HTTP. Control API `/v1/traces` is read-only. Normalize allowlisted metadata before persistence. Credential record supplies organization/project/environment; producer tenant claims have no authority.

## ADR-003 — durable jobs
PostgreSQL jobs are inserted in the telemetry/evaluation transaction (transactional outbox). Workers use leases, bounded retries and SKIP LOCKED. Domain handlers must tolerate redelivery; no in-memory queue is a source of truth.

## ADR-004 — trace accounting
Composite tenant/project/trace/span identity prevents cross-scope collisions. Root wall-clock latency and explicit eligibility prevent parallel-span double counting. Missing roots, cycles and unknown token/pricing fields remain visible; unknown is not zero.

## ADR-005 — identity and authorization
Opaque, hashed, expiring server sessions; HttpOnly cookie, CSRF and strict origin checks. OIDC Authorization Code + PKCE for production. Development identity is explicitly enabled, loopback-only and rejected in production. Resource queries always include canonical organization and permitted project constraints.

## ADR-006 — no ambient remediation authority
An immutable proposal is not execution authority. Remote actions remain disabled. Approval/execution must fail closed while isolated target adapter, health checks and rollback are absent. No shell or broad cloud credentials.

## ADR-007 — bounded deterministic replay evaluation
First evaluator compares explicitly supplied baseline/candidate outputs against immutable expected outputs using exact equality. This is replay grading, not live model execution or proof of generalization. Store manifest hashes and paired results; use an explicit minimum sample gate and report INCONCLUSIVE when evidence is insufficient.

## Design reference
The reference image is absent. Implement the exact documented dark palette, responsive shell and dense operational UI. No synthetic telemetry is seeded into application views.

## ADR-008 — durable, evidence-linked diagnosis
Diagnosis is background work, not a control-API computation. Detection queues a project-scoped diagnosis job; the worker derives bounded deterministic hypotheses and persists normalized hypothesis/evidence-link records. Evidence changes enqueue a refresh while duplicate queued/running work is suppressed. The API only reads persisted results and reports processing, failed, partial, or insufficient-evidence state. This preserves reproducibility and keeps high-volume span analysis outside request handlers without introducing an LLM.

## ADR-009 — project-scoped audit disclosure
Audit rows carry a nullable canonical `project_id`. Organization-level identity/security events remain visible to administrators, while project-limited operators and approvers must provide a project scope that passes the same server authorization used by resource APIs. Historical or organization-level rows with no project scope fail closed for non-admin readers. This prevents an organization member assigned to one project from enumerating actors, resource identifiers, or activity belonging to another project.

## ADR-010 — durable detections and measured SLO snapshots
Detection evaluation is a durable fact distinct from an incident. Each rule/evaluation minute upserts a tenant-scoped record containing detector inputs, measured window, sample count, baseline/deviation/score and bounded trace references. Threshold, EWMA and robust median/MAD detectors retain `NORMAL`, `ANOMALY`, or `INSUFFICIENT_DATA`; statistical detectors require both the absolute guard and anomaly sensitivity. SLO definitions use the same eligible trace source and persist per-minute snapshots for compliance, remaining error budget and multi-window burn. Missing, incomplete, sparse, or oversized telemetry cannot become a healthy result.

## ADR-011 — deterministic critical path and change correlation
Critical-path attribution is inferred during idempotent trace reconstruction from parent-child timing, selecting the longest branch among overlapping siblings while retaining sequential work. Malformed graphs return unavailable attribution. RCA remains deterministic and bounded: it ranks observed failing services using symptom coverage, dependency locality and explicitly recorded nearby deployment/configuration events, while persisting healthy contradictory spans and missing measurements. Temporal correlation is labeled evidence and never presented as proof or a calibrated probability.

## ADR-012 — remove vulnerable PostgreSQL privilege helper without changing database semantics
The current pinned upstream PostgreSQL Alpine image embeds a Go-built `gosu` with fixable high/critical standard-library findings. NeuralOps replaces only that user-switch helper with Alpine's packaged `su-exec`, preserves the entrypoint's `gosu user command` invocation through a symlink, and flattens the final filesystem so the deleted binary is absent from distributable layers. The actual image was rebuilt, migrated, health-checked, and used for integration/browser verification. Debian backend/web findings without vendor fixed versions remain open rather than suppressed.

## ADR-013 — soft rule deletion and immutable incident investigation notes
PostgreSQL table `rule_versions` enforces immutability via the `neuralops_immutable_record()` trigger, which strictly forbids `DELETE` mutations. Hard-deleting a parent rule row violates referential integrity or cascading deletion constraints against existing immutable versions. Therefore, rule deletion uses soft deletion via `deleted_at = now()` while retaining historical versions and audit trails. Furthermore, deletion fails closed with `409 RULE_IN_USE` if any incident references the rule, preventing dangling references in active investigations. Incident investigation notes are modeled as tenant-, project-, and incident-scoped append-only records with authenticated author identity, preserving collaborative incident timeline evidence without permitting retroactive alteration.

## Audit interpretation — 2026-10-25
The implementation phases are tracked separately from production qualification. Local OIDC protocol fixtures, RLS tests, browser accessibility automation, restore checks, and hardened containers establish useful implementation evidence, but they do not prove a target IdP, ingress, encrypted backup, manual assistive-technology review, sustained load behavior, or clean container-vulnerability gate. A route that falls through to a shared page is not counted as its dedicated workflow, and an intentionally disabled remediation control is not counted as execution capability.


## ADR-014 — fail closed until an independently isolated evaluator exists

The resumed Phase 3 implementation launched submitted Python with the worker identity. CPU/memory limits and a Python socket audit hook did not isolate filesystem access, native libraries, child processes, output buffering, or inherited host authority. A probe using a disposable synthetic file confirmed worker filesystem reads. The API now rejects execution/code submissions, the worker marks previously queued execution jobs FAILED without running code, and the runner interface returns BLOCKED without starting a process. No opt-in bypass is provided. Existing offline replay remains available. A future executor needs separate credentials, disposable filesystem, enforced egress/resource/output bounds, and adversarial isolation tests before activation.

Offline checks accept only known grader versions and bounded literal patterns. Missing configured guardrail measurements prevent PASS, guardrail violations fail even on sparse samples, duplicate input cases cannot establish an independent-sample PASS, and identical supplied outputs cannot be advertised as new repeats. Token limits are not monetary cost. Training/tuning overlap remains unknown without provenance. Export hashes cover the exact typed public JSON so recipients can independently reproduce them.

## ADR-015 — preserve dataset versions and enforce publication integrity

Keep the existing immutable dataset rows and use the original version-1 row ID as stable dataset identity; later versions point to that root. No dataset rows or hashes are rewritten. A new additive migration adds tenant/project-scoped lineage references, a lineage/version shape check, and a unique index over scope, coalesced root ID and version. Project-scoped transaction advisory locks serialize both quota checks and version allocation without requiring UPDATE privileges on immutable rows. The migration also enforces the previously documented append-only incident-note contract. Existing applied migrations remain unchanged.

## ADR-016 — reduce measured frontend render work without caching operational responses

The 2026-10-25 performance audit found a single catch-all client console eagerly importing all five feature modules, global-search draft state owned by the entire workspace, repeated ICU formatter construction, an unused refresh-start state update, and a trace waterfall constructing up to 2,000 buttons with repeated ancestry walks and linear critical-path lookups during selection/tab renders. The evaluation list also fetched and polled dataset manifests while its setup form was closed. Native SVG charts already receive 24 server-aggregated buckets; trace lists already use 50-record cursor pagination. Recharts and React Flow are not installed. Existing sidebar transforms and reduced-motion rules remain in place.

Use Next dynamic imports at feature entry points with the existing loading component; retain SSR defaults and the authenticated shell. Isolate the global-search draft in its own component. Reuse locale formatters and preserve missing/invalid-value semantics. Compute trace timing, bounded hierarchy depths, and critical-path membership once per returned trace object. For traces over 100 spans, window the existing 60px rows inside a 480px scroller with overscan, exact original timing values, and Up/Down/Home/End navigation. Small traces keep their natural layout. This changes large-list scrolling rather than removing evidence; all 2,000 spans remain accessible. No dependency, design-token, authentication, authorization, CSRF, or tenant-query change is introduced.

Do not introduce a completed-response cache or speculative database indexes without workload evidence. Operational fetches remain `no-store`; refresh errors still disclose stale retained data. The resource hook avoids an otherwise invisible refresh-start render, clears disabled resource state, and continues aborting obsolete requests. The fixed-upstream proxy now combines the incoming request cancellation signal with its existing timeout. Dataset-list requests run only while evaluation setup is visible, revalidating when reopened.

The reproducible offline benchmark runs real React server rendering with a synthetic loaded resource, not browser paint/hydration or API timing. Final recorded medians: 4,000 number formats **78.92 → 1.76 ms**; initial 2,000-span render **180.34 → 11.94 ms**; mounted span-button markup **2,000 → 16**. Timing varies across runs; raw samples and baseline source snapshots are under `artifacts/performance/`. The CPU harness also checks formatter equivalence, invalid-date handling, bounded large-trace markup, and complete small-trace rendering with a cyclic parent reference. These numbers do not establish 60 FPS or navigation latency.

`npm run lint --prefix web` and `npm run typecheck --prefix web` pass. Production compilation succeeds, but full `next build` fails when Next parses TypeScript CLI `--showConfig` output; the webpack attempt hits the same boundary. Localhost sockets are prohibited, and both a direct Chrome launch and a Playwright regression attempt fail at Chrome `setsockopt: Operation not permitted`. React DevTools profiling, browser accessibility, responsive/visual checks and live API/database measurements therefore remain unverified. New synthetic Playwright coverage targets waterfall access, selection retention, inspector tabs, mobile navigation, reduced motion, axe, all requested widths, and on-demand datasets. `graphify update .` was attempted and failed with `[Errno 1] Operation not permitted`; the knowledge graph still requires refresh. See `docs/PERFORMANCE.md` for reproduction and follow-up checks.
