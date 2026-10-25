# NeuralOps verification record

Updated 2026-10-25 after the verified Phase 2 milestone. This records current checks and distinguishes them from saved artifacts. No production qualification is claimed.

## Resume repair checks — 2026-10-25

Source audit and scope: [resume audit](RESUME_AUDIT.md). These checks supersede the earlier Phase 2 numbers below for the repaired source. Production qualification remains open.

| Check | Executed result |
| --- | --- |
| Baseline before repairs | 45 backend tests passed; Ruff, ESLint and standalone TypeScript passed |
| Final backend suite | 59 passed in 22.36s; two upstream httpx/Authlib deprecation warnings |
| Added runtime-role and note checks | 2 targeted tests passed; the final full suite also includes both changes |
| Migration lifecycle | Full suite passed fresh upgrade/schema parity/downgrade/re-upgrade; local additive upgrade applied and `alembic check` reported no new operations |
| Ruff | Passed on backend, tests and migrations |
| Contract generation | OpenAPI and TypeScript regenerated successfully |
| Frontend | ESLint, standalone TypeScript and production build passed |
| Bandit | No findings; 4,324 lines scanned |
| Known-secret check | Passed across 57 source/browser files |
| Pinned source secret scan | Passed using `uv run --directory services python ../scripts/scan-secrets.py`; public migration revision identifiers narrowly allowlisted |
| Graph update | `graphify update .` passed: 690 nodes, 1,946 edges, 44 communities |
| Existing browser suite | All 3 passed in 1.1m against the current local API, gateway, worker and production web build; main journey, axe/routes, six responsive widths, stale refresh, project scope and retention |
| New browser regression | Missing replay guardrail measurements rendered as insufficient data; INCONCLUSIVE state, 35 case rows and no false regression rows; 1 focused test passed in 5.1s |

One intermediate backend run failed with a RUNNING evaluation while a second pytest process was operating on the same database. The subsequent sequential full run passed all 59 tests. The first source-scanner invocation used system Python and failed to find detect-secrets; the pinned-environment invocation passed after reviewing the public migration identifiers. These failed attempts are retained here and are not successful checks.

The synthetic filesystem probe confirmed the prior subprocess runner could read a worker file. The repaired runner is intentionally BLOCKED; this is not evidence of a completed execution sandbox. No live evaluator or remediation execution is enabled. Container/dependency audits, restore drills and production infrastructure checks below are historical evidence and were not rerun during this source repair.

## Previous Phase 2 checks

| Check | Result |
| --- | --- |
| Backend Ruff (`ruff check neuralops tests migrations`) | Passed |
| Frontend ESLint | Passed |
| Standalone TypeScript (`npm run typecheck --prefix web`) | Passed |
| Bandit (`bandit -r neuralops -ll`) | Passed; no findings reported, 3,065 lines scanned |
| Known-secret check (`python3 scripts/check-secrets.py`) | Passed across 56 source/browser files; no secret values printed |
| Backend pytest | Passed: 33 tests in 8.82 seconds; two upstream httpx/Authlib deprecation warnings |
| Production web build | Passed; full `make check` completed successfully |
| Source secret scanner (`scripts/scan-secrets.py`) | Passed |
| Graph update (`graphify update .`) | Passed: 559 nodes, 1,511 edges, 35 communities |
| Disposable restore drill | Passed: seven table counts and immutable dataset hashes matched; test source preserved |
| Dependency audits | npm audit: zero vulnerabilities; pip-audit: no known vulnerabilities |
| Contract generation | Passed: OpenAPI and generated TypeScript were regenerated from the current API schema, then linted and typechecked |
| Browser | Passed: all 3 tests in 53.3 seconds against rebuilt Compose images; includes detection preview/history, measured SLO calculation, change-correlated RCA, critical path, evaluation, retention cancellation, project cache isolation, stale refresh, 17-route axe and six responsive sizes |
| Fresh container scans | PostgreSQL hardened image: 0 high/critical; no Node high/critical findings in web; Debian backend/web base findings remain open (see below) |

Earlier restricted-session cache, database, source-scanner, graph-update and local build failures cleared after access was restored. No application workaround was needed for those failures. Docker now exposes the local Compose stack on loopback.

## Saved evidence

`artifacts/web-build.log` records a previously successful Docker web build, including compilation, TypeScript and page generation. The current local production build also passes. Six saved overview screenshots cover widths 375, 430, 768, 1024, 1440 and 1920. Screenshots establish captured layouts; they do not establish a current browser test pass.

The supplied Playwright suite covers the authenticated telemetry-to-incident workflow, detection preview, SLO creation/calculation, recorded change evidence, critical-path display, durable diagnosis, replay evaluations, disabled execution, rejection, 17 routes with axe, six responsive widths, stale refresh, project scope and retention confirmation. Backend tests additionally cover reproducible EWMA/MAD false-positive/anomaly cases, insufficient telemetry, SLO arithmetic, critical-path parallelism, concurrent detection jobs, negative authorization, OIDC fixtures, telemetry normalization, migrations, RLS, runtime roles and safety invariants.

## Container scan review

The following counts are package/advisory occurrences reported by scanner JSON, not unique CVE counts. Current reports were regenerated on 2026-10-25 around 08:29–08:30 UTC with Trivy 0.76.1. Findings have not been independently validated or accepted as exceptions.

| Current report | High | Critical | Disposition |
| --- | ---: | ---: | --- |
| `artifacts/backend-cves-current.json` | 61 | 2 | Unresolved; 63 Debian package findings, no fixed version listed |
| `artifacts/web-cves-current.json` | 56 | 1 | Unresolved Debian findings; zero Node high/critical findings after removing unused npm/Yarn from the final runtime |
| `artifacts/postgres-cves-phase2.json` | 0 | 0 | Remediated: vulnerable Go `gosu` replaced by packaged `su-exec`; flattened image has no language binary finding |

Backend critical entries identify `libsqlite3-0` (CVE-2025-7458) and `zlib1g` (CVE-2023-45853). The web critical entry identifies `zlib1g` (CVE-2023-45853). These identifiers describe saved scanner output, not an exploitability conclusion. The earlier PostgreSQL report attributed 26 findings to the removed Go `gosu` helper; the exact flattened replacement image reports zero high/critical vulnerabilities.

Fresh upstream pulls reproduce the pinned source digests. The web runtime starts directly with Node and excludes unused npm/Yarn; its report contains zero Node-package high/critical findings. The PostgreSQL derivative preserves the pinned upstream database filesystem and entrypoint, substitutes only the privilege helper, starts healthy, completes Alembic migration, and was used for the passing integration/browser suites.

Before release, validate the findings against vendor advisories and actual runtime reachability, rebuild with reviewed patched bases/toolchains, and rescan the exact resulting image digests. Record remediation or an explicitly reviewed exception for each remaining finding. Missing fixed-version fields and hardened runtime settings do not close findings. The saved images do not pass a clean high/critical vulnerability gate.

## Remaining qualification

Core checks, browser tests, contract parity, source/dependency scans and the local restore drill pass. Backend/web Debian high/critical findings remain unresolved; no exceptions were accepted. See [release gates](security/release-gates.md) for deployment identity, TLS, backup, load, accessibility and operational evidence still required. Recovery approval/execution remains disabled until the independent approval and isolated executor requirements are met.

## Verified user flow

Story: an operator signs into the local console, creates a project and scoped ingestion key, sends telemetry through the OTLP gateway, and inspects worker-generated incidents, durable diagnosis evidence, and replay results.

| Boundary | Status | Evidence |
| --- | --- | --- |
| UI renders | Passed | Playwright checked all 17 implemented routes and six viewport widths |
| Client → API | Passed | Browser signed in, created a project/key, and performed scoped mutations |
| API → PostgreSQL | Passed | Backend integration suite: 33 tests, including tenant/RLS, Phase 2 resource authorization, migration parity, durable records and actual runtime roles |
| Gateway → worker → response | Passed | Measured traces produced durable detections, SLO snapshots, a grouped incident, critical path and persisted hypothesis/change evidence; replay evaluation completed |
| Response → UI | Passed | Browser inspected rule preview/history, SLO state, correlated RCA, critical-path waterfall and evaluation; verified disabled execution, rejection and retention confirmation |

The browser suite also checks JavaScript page errors on the main journey and automated accessibility violations. These results cover local fixtures; production IdP, load and manual accessibility qualification remain open.
