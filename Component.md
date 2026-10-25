# NeuralOps — Component & Element Contract

**Purpose:** Catalog every shared interface component, its function, data contract, interactions, state handling, accessibility and security implications. See `Design.md` for layouts, `Architecture.md` for APIs, `Security.md` for authorization and `Flow.md` for sequencing. Components marked *planned* are not implemented by this document.

## 1. Conventions
Use React + TypeScript component props with explicit types, no `any`. Each async element supports loading, empty, error, unauthorized and stale results as applicable. UI permissions only aid usability; backend enforces every operation. No component may expose tokens, unredacted prompt content or privileged actions without authorization. IDs displayed in monospace and copyable (except secrets). User-visible data must be sourced from API or clearly marked Demo.

## 2. Global shell components
| Component | Purpose / visual elements | Inputs and outputs / event | States and important rules |
|---|---|---|---|
| `AppShell` | sidebar + topbar + content | `organization, project, route, children` | handles desktop/mobile and global errors |
| `BrandMark` | wordmark + icon | `variant, compact` | no interaction except home link |
| `SidebarNav` | grouped route entries + icons | `groups, activeRoute, permissions`; navigation | hide unavailable routes but never rely on hiding for security |
| `NavGroup` | expandable group label | `items, expanded, onToggle` | keyboard Enter/Space, aria-expanded |
| `WorkspaceSwitcher` | organization selector | organizations, selected, onSelect | clear/reload cache on scope change |
| `ProjectEnvironmentSwitcher` | active project/environment | permitted projects, active, onChange | filter all downstream queries |
| `Topbar` | breadcrumbs, search, time filter, alerts, avatar | layout context | sticky, responsive |
| `Breadcrumbs` | navigational context | segments | keyboard-operable links |
| `GlobalSearch` | command palette + result groups | query, debounce, search API, onOpen | result must be permission-scoped, loading/none/error |
| `TimeRangePicker` | absolute / relative window | `from,to,timezone,onChange` | validate ordering; communicate timezone |
| `NotificationBell` | unread badge | count, onOpen | avoid exposing restricted incident titles |
| `NotificationCenter` | alerts and destination links | notifications, markRead | paginated and access checked |
| `UserMenu` | profile, preferences, sign out | current identity | session-safe logout |
| `ThemeToggle` | theme preference | value, change | maintain contrast and tokens |

## 3. Shared primitives
| Component | Behavior and required elements |
|---|---|
| `PageHeader` | title, subtitle, breadcrumbs, primary and secondary contextual actions |
| `MetricCard` | name, value, unit, sample window, trend, optional sparkline, source-state tooltip |
| `TrendSparkline` | compact history, accessible text equivalent, absent data fallback |
| `StatusBadge` | label + icon/color with known vocabulary `healthy/degraded/critical/unknown` |
| `SeverityBadge` | `critical/high/medium/low` with text and semantic color |
| `StateBadge` | typed lifecycle state, no uncontrolled ad-hoc strings |
| `DataTable` | typed columns, sort/filter, pagination, row action menu, sticky headers as needed |
| `FilterBar` | typed filter chips, search, clear and saved filter sets |
| `SearchInput` | debounced query, clear action, keyboard focus/shortcut |
| `DateTimeCell` | absolute timestamp tooltip; relative with timezone-aware formatting |
| `CopyField` | non-secret copy, success announcement; never copies masked secret as if real |
| `ChartPanel` | title, legend, axes/units, hover, range switch, accessible table summary |
| `EmptyState` | explains absence and next appropriate action; no pretend data |
| `ErrorState` | useful error, request ID, retry where safe; no stack traces |
| `LoadingSkeleton` | geometry matches eventual content, not fake metrics |
| `StaleDataBanner` | last seen time + retry; no misleading live badge |
| `ConfirmDialog` | explicitly names target/effect, focus trap, cancel default, destructive style |
| `SideDrawer` | contextual details, Escape dismissal, focus restoration |
| `Tabs` | semantic tablist and controlled state; preserves deep links if needed |
| `Tooltip` | optional explanatory content, keyboard accessible, never sole source of important data |
| `JsonViewer` | sanitized structured attributes, expand/collapse, bounded nesting, copy with policies |
| `CodeSnippet` | syntax-highlighted setup instruction, copy; mask sensitive values |
| `AuditEventRow` | actor/action/target/time/result, immutable display |
| `PermissionGuard` | visual gate only; must reflect server permissions, never replace server check |
| `ToastRegion` | success/error confirmation from server response; accessible live region |

## 4. Observability feature components
| Component | Elements / function | Interaction/data dependency |
|---|---|---|
| `OverviewKpiGrid` | success, executions, p95, incidents, tokens, cost cards | `/metrics/summary`, navigate to filtered explorer |
| `LatencyTimeSeries` | p50/p95/p99 across selected window | aggregation with explicit sample counts |
| `ErrorCategoryChart` | errors grouped by known classes | click to filter traces |
| `IncidentPreviewTable` | recent incident rows, severity, status, owner | open incident detail |
| `ServiceHealthTable` | service, state, latency, errors, SLO, last seen | sort/filter and service details |
| `ServiceMapCanvas` | dependency graph nodes, edges, zoom, minimap optional | service graph data; selection opens inspector |
| `ServiceNode` | service icon/name/status/latency and error overlay | keyboard focus + accessible list equivalent |
| `ServiceDetailDrawer` | metadata, health trend, traces, incidents | scoped service queries |
| `TraceFilterBar` | trace ID, operation, model, status, duration, window | URL-synced filters |
| `TraceTable` | trace id, root operation, status, duration, spans, tokens, cost, time | pagination; open trace |
| `TraceSummary` | trace id, start, duration, success, completeness | actual normalized trace |
| `SpanTree` | parent-child hierarchy, orphan markers and links | focus/selection synced to waterfall |
| `TraceWaterfall` | horizontal timing bars, offset ruler, duration and critical path | zoom/pan/selection; never sum overlapping spans |
| `SpanInspector` | attributes/events/links/exceptions/JSON | redacted per field permissions |
| `ModelInventoryTable` | provider/model/version/requests/errors/latency/tokens/cost | model detail/filter |
| `ModelComparisonChart` | multiple version curves with legend and sample count | aligned comparable windows |
| `ToolPerformanceTable` | calls, retries, failures, duration and downstream errors | trace links |
| `UsageBreakdown` | by model, project, period; tokens and estimated spend | pricing provenance and unknown state |

## 5. Reliability feature components
| Component | Function | Interaction/data dependency |
|---|---|---|
| `DetectionRuleTable` | rules, enabled state, severity, last firing | edit, duplicate, disable, delete |
| `RuleBuilderForm` | metric, aggregation, scope, operator, threshold, minimum sample count, window, cooldown | validate input, request rule preview, save versioned rule |
| `RulePreviewChart` | historical signals vs threshold | must label simulation/backtest, not actual alert |
| `SloSummaryCard` | objective, observed value, remaining budget, period | navigate to SLO detail |
| `BurnRateChart` | consumption and alert thresholds | sample and missing interval labels |
| `IncidentTable` | filterable incident ownership and workflow states | open, assign based on permissions |
| `IncidentHeader` | title, severity, status, time, assignee | only valid state transitions |
| `IncidentTimeline` | chronological detection, investigation, approval, resolution | source-backed event links |
| `EvidenceList` | trace IDs, metrics, deploy changes, links | open source and permission check |
| `DependencyInvestigationGraph` | affected nodes/path | evidence provenance per edge |
| `HypothesisCard` | rank, summary, supporting/contrary evidence, missing data | navigate to evidence, never fabricate probability |
| `RcaWorkspace` | graph + hypotheses + inspector (desktop); tabs (mobile) | coordinated selection |
| `InvestigationNotes` | authored notes/comments | sanitize input, audit edits, version history |

Phase 2 implementation mapping (verified 2026-10-25): `RulesPage` implements the rule table/builder, bounded preview and durable detection history; `SLOsPage` implements objective creation, enablement, summary cards, burn values and measured trend; `TraceDetailPage` renders persisted critical-path attribution; `IncidentPage` renders persisted supporting/contradicting links, coverage, dependency context and recorded change evidence. Dedicated rule creation/editing, immutable rule-version inspection, guarded soft deletion and scoped investigation notes are also implemented. Notes have database-enforced append-only protection; graph editing remains planned.

## 6. Evaluation feature components
| Component | Function | Contract |
|---|---|---|
| `EvaluationOverviewCards` | totals by pending/running/passed/failed/inconclusive | statuses from API, not inferred from color |
| `DatasetTable` | name, owner, case count, versions, last update | scoped dataset list |
| `DatasetVersionInspector` | immutable manifest hash, cases, graders, access | published versions read-only |
| `EvaluationWizard` | steps: select project/dataset, baseline, candidate, evaluators, limits, review | validates each step, saves pending job id |
| `EvaluatorConfig` | grader type, weights, deterministic checks, guardrails | disallow unknown remote execution without consent |
| `EvaluationProgress` | queued/running/finished; counts and progress | poll job status, no estimated completion promises |
| `ScoreComparison` | baseline/candidate, CIs, pass/fail/inconclusive | confidence method and sample size shown |
| `CaseDiffTable` | individual cases, output diff, score deltas, links | protected/redacted content |
| `EvaluationReportExport` | download immutable report for run/version | permission and audit check |

## 7. Remediation feature components
| Component | Function | Security requirement |
|---|---|---|
| `RemediationQueue` | proposed actions, target, risk, validation, approver | role/tenant scoped |
| `ProposalEvidencePanel` | incident, supporting evidence, configuration diff | exact evidence identifiers |
| `ActionManifestViewer` | typed allowlisted action, target, hash, TTL | immutable after approval |
| `PreconditionChecklist` | health and version preconditions, rollback readiness | backed by server validation |
| `RemediationApprovalPanel` | approve/reject + notes | approver identity, no self-approval when segregation policy enabled |
| `ExecuteApprovedAction` | execution confirmation with target/effect | server verifies approval hash, time, role, state |
| `ExecutionTimeline` | retries, action receipt, verify/rollback | audit every attempt, masked secrets |
| `RollbackPanel` | permitted rollback action and status | separate allowlisted and authorized procedure |

## 8. Administration components
| Component | Function | Special rules |
|---|---|---|
| `ProjectTable` | project status, environment, last telemetry | click to details/setup |
| `InstrumentationWizard` | metadata, runtime, scoped credential, snippets, verify | show credential once, never persist in UI storage |
| `ConnectionVerifier` | test-spans status, last received, retry | differentiate waiting vs failed |
| `TeamMemberTable` | member, role, invite state | admins only for mutations |
| `RoleEditor` | role assignments, descriptions and permissions | server policy validation |
| `ApiKeyTable` | key name, prefix, scope, expiry, last used | never secret value |
| `CreateKeyDialog` | scope, expiry, one-time secret reveal | redact screenshots and logs |
| `KeyRotationDialog` | rotate/revoke with confirmation | server records audit, old key invalidated per policy |
| `AuditLogTable` | filter/export immutable events | privileged read, no edit/delete controls |
| `RetentionSettings` | per-project retention and deletion policy | high-risk change confirmation |
| `PrivacySettings` | payload opt-in, sampling/redaction policies | backend enforces, clear tradeoffs |
| `NotificationPreferences` | routing preferences | validate destinations and authorization |
| `OnboardingChecklist` | project, integration, first trace, first rule | genuine verification state, not decorative checkmarks |

## 9. Shared design contracts / props (illustrative TypeScript)
```ts
type Loadable<T> =
  | { state: 'loading' }
  | { state: 'empty' }
  | { state: 'error'; requestId?: string; message: string }
  | { state: 'forbidden' }
  | { state: 'stale'; data: T; lastUpdatedAt: string }
  | { state: 'ready'; data: T; lastUpdatedAt: string };

type ScopedQuery = {
  organizationId: string;
  projectId: string;
  environment?: string;
  from: string; // ISO-8601
  to: string;   // ISO-8601
};

type MetricValue = {
  value: number | null;
  unit: '%' | 'ms' | 'count' | 'tokens' | 'currency';
  sampleCount: number;
  source: 'measured' | 'estimated' | 'demo';
  calculatedAt: string;
};

type EvidenceReference = {
  kind: 'trace' | 'span' | 'metric' | 'deployment' | 'evaluation';
  id: string;
  observedAt: string;
  summary: string;
};
```
These are design contracts to refine in `packages/contracts` and validate against OpenAPI. API response types should be generated or checked automatically rather than independently drifting.

## 10. Component validation checklist
Each component gets unit tests for rendering and state transitions, interaction tests (including keyboard), loading/empty/error cases, permission negative tests, responsive screenshot review and a11y checks. E2E suites cover: create project → verify trace; trace → incident → evidence; evaluation setup → comparison; remediation approval → execute or reject. See `Flow.md` and `Security.md`.
