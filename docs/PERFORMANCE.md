# Frontend performance audit — 2026-10-25

NeuralOps operators navigate the authenticated console, request project-scoped telemetry through the fixed Next API proxy, and inspect FastAPI/PostgreSQL measurements and persisted worker results. This pass reduces client work in that flow. It does **not** certify browser responsiveness or production readiness: the execution environment prohibits sockets and Chrome launch.

## Findings and changes

| Evidence in the original code | Resulting change |
| --- | --- |
| `Console` statically imports overview, observability, reliability, workflows and administration under one client route | On-demand feature chunks using installed Next's documented `dynamic` API; existing loading UI and SSR defaults |
| Global search updates `Workspace` state for every character, revisiting its feature subtree | Draft state is local to `GlobalSearch`; submission and routing are preserved |
| Every number/date cell constructs a locale formatter | Reuse formatters, retaining units, precision, null and invalid-date output |
| 2,000-span traces render every row; tab/selection changes rebuild hierarchy maps and use repeated array membership scans | Window large waterfalls, memoize trace-derived layout, use a Set for critical-path membership |
| Every successful polling cycle first changes an unused `refreshing` flag | Retained-data refresh begins with the existing state object; returned data still updates normally |
| Closed evaluation setup still fetches/polls dataset manifests | Fetch only while setup is open; reopening issues a fresh request |
| Browser aborts stop the client fetch, but proxy upstream fetch only has a timeout | Combine request signal and existing 15-second deadline |

No dependencies were added. `Design.md` and `Component.md` are unchanged. Palette, typography, timing values, operational statuses, evidence and permissions are retained. Large waterfalls now scroll internally after 100 rows; smaller waterfalls retain their natural height. The virtual viewport renders 16 rows at a time with overscan. Up/Down/Home/End traverse the full evidence list; buttons retain selection and inspector actions.

The app uses native SVG charts and HTML topology, not Recharts/React Flow. Summary charts are already server-aggregated to 24 buckets; no further downsampling is justified. The trace explorer already has 50-record server cursor pagination. Evaluation tables are bounded at 500 cases. Additional table virtualization, chart memoization, and broad React.memo/useCallback wrappers were not added without browser evidence of benefit.

Resource effects already cancel obsolete paths and clean up their controllers. Workspace interval, toast timeout and navigation listeners already have cleanup. No memory leak was established from the available evidence.

## Reproducible CPU baseline

Run from the repository root, with the existing installed web dependencies:

```sh
node web/scripts/performance-bench.cjs --baseline
node web/scripts/performance-bench.cjs
```

The baseline loads snapshots of the original API helper and observability component from `artifacts/performance/baseline/`. Both versions use the same installed React/Next/TypeScript dependencies and a synthetic 2,000-span chain. `useResource` is replaced **only inside the Node benchmark** with a loaded fixture; no application data adapter or production fixture is introduced. Compilation and module loading are outside the timed region. Each operation warms up, then runs seven number-formatting samples or five component-render samples; the median is reported. Semantic assertions compare formatting against Intl and render a complete small trace with a cyclic parent link.

Recorded on Node v22.22.1 / React 19.3.1 in this restricted environment:

| Operation | Before median | After median |
| --- | ---: | ---: |
| Format 4,000 numbers | 78.92 ms | 1.76 ms |
| Initial React server render, synthetic 2,000-span trace | 180.34 ms | 11.94 ms |
| Span buttons in initial rendered markup | 2,000 | 16 |

Raw samples: `artifacts/performance/before.json` and `after.json`. This is an offline render/formatting CPU comparison. It excludes data fetching, client effects, DOM layout, paint, scrolling, hydration and network latency. It is not a React DevTools profile or proof of 60 FPS. Samples vary with host load, React development checks and garbage collection; there is no timing threshold in correctness tests.

## Verification status

| Check | Result |
| --- | --- |
| ESLint, zero warnings | Passed |
| TypeScript, no emit | Passed |
| CPU benchmark and semantic assertions, original and optimized | Passed |
| `next build` | Compiled successfully; full build failed parsing TypeScript CLI `--showConfig` output |
| `next build --webpack` | Failed at the same TypeScript configuration boundary |
| Playwright large-waterfall regression | Blocked before page creation by Chrome `setsockopt: Operation not permitted`; recorded in `artifacts/performance/playwright.txt` |
| React DevTools Profiler / browser performance trace | Unavailable because Chrome cannot start |
| 375/768/1024/1440/1920 responsive and axe checks | Added in `web/tests/performance.spec.ts`; not executed past browser launch |
| Existing authenticated backend integration journeys | Not run: localhost sockets prohibited |
| `graphify update .` | Failed with `[Errno 1] Operation not permitted` |

The full build failure also occurred before edits with webpack. Type checks were run independently and passed; no build check was disabled or relaxed. Actual transferred bundle sizes, hydration timing, API percentiles, long tasks, frame rates and visual comparisons remain unmeasured.

## Finish browser and production verification in an unrestricted environment

1. Run `npm run build --prefix web` and resolve the TypeScript CLI environment failure if it recurs. Start the real backend stack and production web server. Do not use development compilation latency as a navigation benchmark.
2. Run `npm run test:e2e --prefix web -- tests/performance.spec.ts` for deterministic rendering/accessibility checks, then the full existing integration suite against the authorized local development stack. That suite creates explicit synthetic projects and telemetry. Inspect screenshots at the requested widths, including long operation/service labels and browser text zoom.
3. Use React DevTools Profiler with the same synthetic 2,000-span trace on a baseline and optimized build. Record global-search typing, first/last span selection, inspector tabs, manual refresh and 30-second polling. Confirm search keystrokes no longer commit the workspace feature tree and selection does not redo trace layout. For a production React profiling build use the installed Next CLI's `next build --profile` option.
4. Use Chrome Performance/Network with identical machine, viewport, cache conditions and CPU/network throttling. Record five cold and warm navigations and interaction runs; retain traces and report medians/tails for transferred JS, hydration/main-thread work, long tasks, event duration and frame time. Compare the first uncached lazy navigation as well as subsequent navigations.
5. Check scroll access and keyboard navigation to span 1 and span 2,000, inspector accuracy after polling, reduced motion, sidebar focus return, obsolete filter cancellation, refresh failures, project changes and session expiry. Run axe and a manual screen-reader review of the virtual list.
6. Measure API and database latency separately on representative tenant-scoped datasets. Summary aggregation currently scans eligible rows for each of 24 buckets and repeatedly sorts percentile inputs; service analytics also aggregates bounded spans in application code. Scope/time indexes exist. Profile these endpoints and query plans before introducing a one-pass aggregation or additional indexes. Do not conceal oversized windows or serve old operational results to mask latency.
7. Run `graphify update .` to refresh the graph.

Remaining architecture costs include client-side `/me` → `/projects` → telemetry discovery and coarse feature-module chunks. Removing that waterfall would require deliberate server/session boundary work and browser evidence, rather than duplicating identity checks or adding a long-lived authenticated cache. High-cardinality service topology and 500-case evaluation filtering should be profiled next. No claim is made that a particular endpoint or database query is slow without live measurements.
