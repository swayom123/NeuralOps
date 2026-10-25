# NeuralOps — Design Specification

**Status:** Implementation blueprint | **Version:** 1.0 | **Reference:** `NeuralOps-reference.png` (visual concept, not an implementation or verified data source)

## 1. Product intent and design constraints
NeuralOps is an AI reliability and incident intelligence platform, **not** an agent chat application. The core operator journey is **Observe → Detect → Investigate → Evaluate → Approve → Verify**. This spec is authoritative for interface presentation; `Architecture.md` specifies runtime boundaries, `Component.md` specifies interaction contracts, `Security.md` defines enforceable safeguards, and `Flow.md` specifies sequences.

The nine-panel reference shows Command Center, Service Map, Trace Explorer, Trace Details, Incident Investigation, Evaluation Runs, Remediation Center, Model Performance, and Instrumentation Setup. Preserve the visual grammar, information density, and page hierarchy—not necessarily every illustrative label, number, or element. **All numbers in design mockups are synthetic and must be marked Demo.** A missing backend must produce explicit unavailable/loading/empty states; never secretly substitute pretend live telemetry.

## 2. Design system

### Tokens
| Token | Value | Meaning |
|---|---|---|
| `--bg` | `#0B111C` | app background |
| `--sidebar` | `#0E1522` | persistent navigation |
| `--surface` | `#151E2D` | cards, tables |
| `--surface-raised` | `#1B283A` | overlays, panels |
| `--hover` | `#243247` | hover/focus-adjacent surface |
| `--border` | `#293548` | subtle separators |
| `--text` | `#F1F5F9` | primary text |
| `--text-muted` | `#94A3B8` | secondary text |
| `--text-subtle` | `#64748B` | tertiary metadata (check contrast) |
| `--success` | `#22C55E` | healthy, success |
| `--info` | `#60A5FA` | selected, informational |
| `--warning` | `#F59E0B` | degraded |
| `--critical` | `#EF4444` | failing, dangerous |

Typography: Geist/Inter for UI; JetBrains Mono for IDs, timestamps, code and JSON. Type scale: 12 metadata, 13 dense rows, 14 base, 16 section heading, 22 page heading, 28 high-priority numerical value. Maintain accessible contrast; never communicate severity using color alone. 8px spacing base with 4px internal micro-spacing; 10–12px card radius; 1px borders. Icons: Lucide, consistent 16–18px common size. Dark mode required; light mode optional and must be token-based.

### Layout
Desktop ≥1280px: sidebar 248px expanded / 64px collapsed, topbar 56px, primary content width fluid with 24px gutters, 12-column responsive grid. 1024–1279px: reduced gutters, rearranged KPI cards. 768–1023px: sidebar as overlay, charts stack. <768px: single-column main content, tabbed incident/trace inspectors, internally scrollable dense tables, visible filter action. No viewport-wide horizontal overflow. Responsive breakpoints must be tested at 375, 430, 768, 1024, 1440, 1920px.

## 3. Information architecture and routes
All routes are within authenticated `/app/:orgSlug/:projectSlug` unless the screen is organization-level. Never concatenate untrusted slugs into direct backend resource queries: route identifiers are presentation only and server authorization remains mandatory.

| Navigation group | Route suffix | Screen |
|---|---|---|
| Overview | `/overview` | Command Center |
| Overview | `/health` | System Health |
| Overview | `/service-map` | Service dependency map |
| Observability | `/traces` | Trace Explorer |
| Observability | `/traces/:traceId` | Trace Detail waterfall |
| Observability | `/models` | Model Performance |
| Observability | `/tools` | Tool Analytics |
| Observability | `/usage` | Token & Cost |
| Reliability | `/rules` | Detection Rules |
| Reliability | `/rules/new`, `/rules/:id/edit` | Rule Builder |
| Reliability | `/incidents` | Incident List |
| Reliability | `/incidents/:id` | Incident Investigation |
| Reliability | `/incidents/:id/diagnosis` | Root Cause Analysis |
| Reliability | `/slos` | SLO Management |
| Evaluation | `/evaluations` | Evaluation Overview & Runs |
| Evaluation | `/evaluations/new` | Evaluation Wizard |
| Evaluation | `/evaluations/:id` | Evaluation Detail and comparison |
| Evaluation | `/datasets` | Dataset Library |
| Evaluation | `/datasets/:id` | Dataset Versions |
| Remediation | `/remediations` | Recommendations & approval queue |
| Remediation | `/remediations/:id` | Proposal, permissions, execution |
| Remediation | `/remediations/history` | Execution history |
| Administration | `/projects` | Projects/integrations |
| Administration | `/projects/new` | Instrumentation Setup Wizard |
| Administration | `/team` | Team and role management |
| Administration | `/keys` | Scoped API keys |
| Administration | `/audit` | Audit log |
| Administration | `/settings` | Organization settings |
| Global | `/onboarding` | First-run onboarding |

## 4. Screen-specific UI blueprints

### 4.1 Command Center
Header title, project/environment and time selectors, refresh and export. Six metric cards: success rate, execution count, p95 latency, active incidents, tokens, estimated cost. Show units, comparison window and unknown/missing-data states. Main row: latency chart (P50/P95/P99) ~2/3 width, failure category chart ~1/3; secondary row: active incidents table with severity, title, service, age, status, assignee. Bottom: recent deployments, anomalies, pending approvals. Every KPI links to supporting filtered records. Avoid implying live refresh when stale.

### 4.2 System Health and Service Map
System Health has SLI tiles, service table, SLO/burn-rate visualization and integration status. Service Map uses directed graph with accessible list/table alternative, zoom/pan, node selection, edge direction, status legend and service detail drawer. Graph nodes must be derived from observed dependencies; inferred/unavailable links labeled as such. Selected node navigates to traces and incidents.

### 4.3 Trace Explorer / Detail
Explorer filter bar (time range, project, operation, status, service, model, duration); saved views and pagination. Dense table: trace ID, root operation, service, status, duration, spans, tokens, cost estimate, timestamp. Detail: summary strip, waterfall timeline, hierarchical span tree, inspector tabs (Attributes, Events, Links, Exceptions, JSON). Indicate missing parents, clock skew and incomplete spans. Hover shows tooltips; keyboard navigation selects spans. Attributes with sensitive payloads must show redaction/permission status, not hidden dummy data.

### 4.4 Incidents / Root Cause Analysis
Incidents list supports status/severity/owner filters and bulk actions limited to safe mutations. Detail uses tabs Overview, Investigation, Evidence, Timeline, Evaluations, Remediation. Investigation uses 3 panels on desktop: dependency graph, ranked hypotheses, evidence inspector; on mobile use tabs. Each hypothesis has supporting AND contradicting evidence, data coverage and 'insufficient evidence' state. No uncalibrated percent confidence; use evidence labels. Link to trace artifacts and deployment records.

### 4.5 Model / Tool / Cost Analytics
Model list includes provider, model+version, requests, success, p95, tokens and estimated cost; table/detail and comparison charts. Tool analytics show calls, latency distributions, retries, failure categories. Usage screen shows input/output tokens, trends, breakdown by project/model and budget alerts. Show currency, cost pricing source and unavailable when pricing missing. Never equate estimated model cost with invoices.

### 4.6 Detection Rules and SLOs
Rules list with status, scope, threshold, window, last firing; builder form for metric, aggregation, comparator, threshold, min sample count, severity, cooldown, schedule, dry-run preview. SLO list includes SLI, objective, compliance, error budget and burn-rate windows. Distinguish insufficient samples from success. Destructive actions require confirmation.

Verified Phase 2 surface (2026-10-25): the rule builder exposes threshold, EWMA and robust median/MAD detectors and a real bounded dry-run; durable evaluation history includes normal and insufficient-data records. `/slos` creates/toggles success or latency objectives and renders measured compliance, remaining budget, short/long burn and snapshot trend. Trace detail marks inferred critical-path spans. Incident investigation separates supporting from contradicting spans, shows coverage/dependency context, records deployment/configuration events, and labels temporal correlation as non-causal. All values come from typed APIs; no reference numbers are seeded.

### 4.7 Evaluations and Datasets
Dataset library includes immutable version IDs and permissions. Evaluation wizard steps: project, dataset version, baseline, candidate, evaluators, resource limits, review. Evaluation detail shows progress, run manifest, scorecards, paired per-case diff, correctness/safety/latency/cost and statistical confidence or inconclusive. Enable case filtering and export. Avoid 'winner' badges unless gating policy is met.

### 4.8 Remediation Center
Queue lists incident, action, target, risk, validation, approval and proposed time. Detail shows evidence, exact action manifest hash, dry-run summary, preconditions, reviewer, expiry, rollback. Distinct Approve, Reject, Execute, Verify; dangerous actions require explicit confirmation and correct role. Clear disabled explanations. Timeline must show FAILED/REJECTED/TIMED_OUT/ROLLBACK states.

### 4.9 Integrations and Administration
Project wizard: metadata → runtime → generate scope-limited credential → show SDK/Collector snippet → send test span → verify. Secret shown once only and never in screenshots/demo. Team/roles, key rotation/revocation, audit search/export and retention/notification/security settings use consistent forms with explicit save/cancel, validation and permission errors.

## 5. Universal component states
Every async region must support: `idle`, `loading` (skeleton, never fake success), `success`, `empty`, `error`, `offline/stale`, `forbidden`, `partial` where applicable. A11y: semantic HTML, labels, visible focus, 44×44 touch targets where practical, keyboard graph alternative, no hover-only information, reduced motion, table header semantics, aria-live for meaningful status (not every telemetry tick). Animations 120–220ms except reduced-motion.

## 6. Data integrity and visual honesty
All examples use a `demoMode` adapter that is conspicuously labeled. Live components must render API responses via typed client, never static reference numbers; a mocked screenshot is not evidence of functionality. Every graph axes/units/timezone and series names must be inspectable. Loading, truncated series, gaps, stale timestamps, and p95 sample size must be visible.

## 7. Implementation and review order
1. Tokens, navigation shell, empty/loading/error primitives.
2. Command Center, Trace Explorer/Detail.
3. Incidents, Evidence and Root Cause workspace.
4. Evaluations, Remediation safety flow.
5. Remaining analytics and administrative routes.
6. Desktop/tablet/mobile/accessibility audit and consistent API wiring.

**Acceptance:** all listed routes resolve, no placeholder buttons, proper role restrictions and states, browser back/forward works, layout stable at tested breakpoints, demo data clearly labeled, no secret exposure, keyboard and screen-reader critical journeys validated. Screenshot match is a design criterion, not permission to sacrifice functionality.
