/* eslint-disable @typescript-eslint/no-require-imports -- Node-only benchmark uses a TS module loader. */
// Offline CPU benchmark: real component SSR, not browser FPS/hydration or API latency.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { performance } = require("node:perf_hooks");
const ts = require("typescript");
const React = require("react");
const { renderToString } = require("react-dom/server");
const root = path.resolve(__dirname, "..");
const cache = new Map();
const baseline = process.argv.includes("--baseline");
const baselineFiles = {
  "lib/api.ts": "api.ts.txt",
  "components/observability.tsx": "observability.tsx.txt",
};
let fixture;
function load(file) {
  if (cache.has(file)) return cache.get(file);
  const sourceFile =
    baseline && baselineFiles[path.relative(root, file)]
      ? path.resolve(
          root,
          "../artifacts/performance/baseline",
          baselineFiles[path.relative(root, file)],
        )
      : file;
  const code = ts.transpileModule(fs.readFileSync(sourceFile, "utf8"), {
    fileName: file,
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      jsx: ts.JsxEmit.ReactJSX,
      target: ts.ScriptTarget.ES2022,
      esModuleInterop: true,
    },
  }).outputText;
  const exports = {};
  cache.set(file, exports);
  const localRequire = (id) => {
    if (id.startsWith("@/") || id.startsWith(".")) {
      const target = id.startsWith("@/")
        ? path.join(root, id.slice(2))
        : path.resolve(path.dirname(file), id);
      const resolved = [".ts", ".tsx", ""]
        .map((ext) => target + ext)
        .find((p) => fs.existsSync(p));
      return load(resolved);
    }
    return require(id);
  };
  new Function("require", "exports", "module", code)(localRequire, exports, {
    exports,
  });
  if (file === path.join(root, "lib/api.ts"))
    exports.useResource = () => ({ data: fixture, loading: false });
  return exports;
}
const api = load(path.join(root, "lib/api.ts"));
const { TraceDetailPage } = load(
  path.join(root, "components/observability.tsx"),
);
const samples = (fn, count = 7) => {
  fn();
  return Array.from({ length: count }, () => {
    const start = performance.now();
    fn();
    return performance.now() - start;
  }).sort((a, b) => a - b);
};
fixture = {
  operation: "Synthetic benchmark",
  status: "ok",
  duration_ms: 2000,
  span_count: 2000,
  critical_path_duration_ms: 2000,
  critical_path: Array.from({ length: 2000 }, (_, i) => String(i)),
  tokens: 2000,
  issues: [],
  truncated: false,
  privacy: "Metadata only",
  spans: Array.from({ length: 2000 }, (_, i) => ({
    span_id: String(i),
    parent_span_id: i ? String(i - 1) : null,
    operation: `Synthetic operation ${i}`,
    service: "benchmark",
    status: "ok",
    start_ns: String(i * 1e6),
    end_ns: String((i + 1) * 1e6),
    attributes: {},
    links: [],
    redacted_count: 0,
  })),
};
const format = samples(() => {
  for (let i = 0; i < 4000; i++) api.number(i / 3, 2);
});
const trace = samples(
  () =>
    renderToString(
      React.createElement(TraceDetailPage, {
        scope: {
          project: { id: "benchmark" },
          refresh: 0,
          base: "/app/synthetic/benchmark",
        },
        id: "benchmark",
      }),
    ),
  5,
);
const markup = renderToString(
  React.createElement(TraceDetailPage, {
    scope: {
      project: { id: "benchmark" },
      refresh: 0,
      base: "/app/synthetic/benchmark",
    },
    id: "benchmark",
  }),
);
// Semantic regressions run against the real exported helpers and component.
for (const digits of [0, 1, 2, 5]) {
  for (const value of [
    undefined,
    null,
    0,
    -1000.125,
    1.005,
    1e15,
    NaN,
    Infinity,
  ]) {
    assert.equal(
      api.number(value, digits),
      value == null
        ? "—"
        : new Intl.NumberFormat("en-US", {
            maximumFractionDigits: digits,
          }).format(value),
    );
  }
}
for (const value of ["2026-10-25T12:34:00Z", "invalid"]) {
  assert.equal(
    api.date(value),
    new Date(value).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZoneName: "short",
    }),
  );
}
assert.match(markup, /Synthetic operation 0/);
assert.match(markup, /critical path/);
const renderedSpanButtons = (markup.match(/class="span-row /g) || []).length;
assert.ok(baseline ? renderedSpanButtons === 2000 : renderedSpanButtons <= 24);
fixture = {
  ...fixture,
  spans: fixture.spans.slice(0, 3),
  critical_path: ["0", "2"],
  span_count: 3,
};
fixture.spans[1] = { ...fixture.spans[1], parent_span_id: "1" }; // malformed cycle remains bounded
const small = renderToString(
  React.createElement(TraceDetailPage, {
    scope: { project: { id: "benchmark" }, refresh: 0, base: "/benchmark" },
    id: "benchmark",
  }),
);
assert.equal((small.match(/class="span-row /g) || []).length, 3);
for (let i = 0; i < 3; i++)
  assert.ok(small.includes(`Synthetic operation ${i}`));
console.log(
  JSON.stringify(
    {
      environment: { node: process.version, react: React.version },
      baseline,
      methodology:
        "Warmup then median of 7 formatting / 5 SSR samples; 2000-span synthetic chain; offline CPU only",
      formatting4000Ms: format[3],
      trace2000SSRMs: trace[2],
      renderedSpanButtons,
      correctnessChecks:
        "Passed: number formatting equivalence, date formatting equivalence, bounded large trace, complete small trace with cycle",
      formatSamplesMs: format,
      traceSamplesMs: trace,
    },
    null,
    2,
  ),
);
