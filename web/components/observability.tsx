"use client";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { VirtualSpanList } from "./virtual-span-list";
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  GitBranch,
  Search,
} from "lucide-react";
import { date, number, useResource } from "@/lib/api";
import type {
  Analytics,
  Page,
  Services,
  Trace,
  TraceDetail,
} from "@/lib/types";
import type { Scope } from "./console";
import {
  Empty,
  Json,
  PageHeading,
  Panel,
  Resource,
  SafetyNotice,
  Status,
} from "./primitives";

export function TracePage({ scope }: { scope: Scope }) {
  const params = useSearchParams(),
    router = useRouter();
  const status = params.get("status") ?? "",
    service = params.get("service") ?? "",
    search = params.get("search") ?? "",
    cursor = params.get("cursor") ?? "";
  const [input, setInput] = useState(search);
  const query = new URLSearchParams({
    project_id: scope.project.id,
    hours: String(scope.hours),
    limit: "50",
  });
  if (status) query.set("status", status);
  if (service) query.set("service", service);
  if (search) query.set("search", search);
  if (cursor) query.set("cursor", cursor);
  const data = useResource<Page<Trace>>(`/traces?${query}`, scope.refresh);
  function filter(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "cursor") next.delete("cursor");
    router.push(`${scope.base}/traces?${next}`);
  }
  return (
    <>
      <PageHeading
        title="Trace Explorer"
        description="Follow each execution across your models, services, and tools."
      />
      <div className="filter-bar">
        <form
          className="search-field"
          onSubmit={(e) => {
            e.preventDefault();
            filter("search", input);
          }}
        >
          <Search size={16} />
          <input
            aria-label="Filter traces by operation or ID"
            placeholder="Search operation or trace ID…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
          />
          <button type="submit" className="button small">
            Search
          </button>
        </form>
        <label className="inline-field">
          Status
          <select
            value={status}
            onChange={(e) => filter("status", e.target.value)}
          >
            <option value="">All statuses</option>
            <option value="ok">OK</option>
            <option value="error">Error</option>
            <option value="incomplete">Incomplete</option>
          </select>
        </label>
        {service && (
          <button
            className="button small"
            onClick={() => filter("service", "")}
          >
            Clear service: {service}
          </button>
        )}
        {(status || service || search) && (
          <button
            className="button small"
            onClick={() => {
              setInput("");
              router.push(`${scope.base}/traces`);
            }}
          >
            Clear filters
          </button>
        )}
      </div>
      <Panel
        title="Executions"
        description="Stable ID order · 50 records per page · metadata only"
      >
        <Resource state={data}>
          {(page) => (
            <>
              {page.items.length ? (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Trace / operation</th>
                        <th>Service</th>
                        <th>Status</th>
                        <th>Duration</th>
                        <th>Spans</th>
                        <th>Tokens</th>
                        <th>Started</th>
                      </tr>
                    </thead>
                    <tbody>
                      {page.items.map((trace) => (
                        <tr key={trace.id}>
                          <td>
                            <Link
                              href={`${scope.base}/traces/${trace.trace_id}`}
                              className="row-link"
                            >
                              {trace.operation}
                              <small className="mono">
                                {trace.trace_id.slice(0, 16)}…
                              </small>
                            </Link>
                          </td>
                          <td>{trace.service}</td>
                          <td>
                            <Status value={trace.status} />
                          </td>
                          <td className="mono">
                            {number(trace.duration_ms, 1)} ms
                          </td>
                          <td>{trace.span_count}</td>
                          <td>{number(trace.tokens)}</td>
                          <td className="muted nowrap">
                            {date(
                              new Date(
                                Number(trace.start_ns) / 1e6,
                              ).toISOString(),
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <Empty
                  title={
                    status || search
                      ? "No matching traces"
                      : "No traces received"
                  }
                  href={`${scope.base}/projects`}
                >
                  Try a different filter or send telemetry to your
                  project&apos;s OTLP gateway.
                </Empty>
              )}
              <div className="pagination">
                <span>{page.items.length} records on this page</span>
                <div>
                  {cursor && (
                    <button
                      className="button small"
                      onClick={() => filter("cursor", "")}
                    >
                      First page
                    </button>
                  )}
                  {page.next_cursor && (
                    <button
                      className="button small"
                      onClick={() => filter("cursor", page.next_cursor!)}
                    >
                      Next page
                      <ArrowRight size={14} />
                    </button>
                  )}
                </div>
              </div>
            </>
          )}
        </Resource>
      </Panel>
    </>
  );
}
export function TraceDetailPage({ scope, id }: { scope: Scope; id: string }) {
  const state = useResource<TraceDetail>(
    `/traces/${encodeURIComponent(id)}?project_id=${scope.project.id}`,
    scope.refresh,
  );
  const [selected, setSelected] = useState(""),
    [tab, setTab] = useState("attributes");
  const layout = useMemo(() => {
    const spans = state.data?.spans ?? [];
    let first = Infinity,
      last = -Infinity;
    const lookup = new Map(spans.map((span) => [span.span_id, span]));
    const depths = new Map<string, number>();
    for (const span of spans) {
      first = Math.min(first, Number(span.start_ns));
      last = Math.max(last, Number(span.end_ns) || Number(span.start_ns));
      let node = span,
        depth = 0;
      const seen = new Set<string>();
      while (
        node.parent_span_id &&
        lookup.has(node.parent_span_id) &&
        !seen.has(node.span_id) &&
        depth < 8
      ) {
        seen.add(node.span_id);
        depth++;
        node = lookup.get(node.parent_span_id)!;
      }
      depths.set(span.span_id, depth);
    }
    return {
      first,
      length: Math.max(1, last - first),
      depths,
      critical: new Set(state.data?.critical_path),
    };
  }, [state.data]);
  return (
    <>
      <Link className="back-link" href={`${scope.base}/traces`}>
        <ArrowLeft size={14} />
        Trace Explorer
      </Link>
      <PageHeading title="Trace investigation" description={id} />
      <Resource state={state}>
        {(trace) => {
          const span =
            trace.spans.find((s) => s.span_id === selected) ?? trace.spans[0];
          const { first, length, depths, critical } = layout;
          return (
            <>
              <div className="trace-summary">
                <div>
                  <span>Root operation</span>
                  <strong>{trace.operation}</strong>
                </div>
                <div>
                  <span>Status</span>
                  <Status value={trace.status} />
                </div>
                <div>
                  <span>Wall-clock duration</span>
                  <strong>{number(trace.duration_ms, 2)} ms</strong>
                </div>
                <div>
                  <span>Spans</span>
                  <strong>{trace.span_count}</strong>
                </div>
                <div>
                  <span>Critical path</span>
                  <strong>
                    {number(trace.critical_path_duration_ms, 2)} ms ·{" "}
                    {trace.critical_path.length} spans
                  </strong>
                </div>
                <div>
                  <span>Attributed tokens</span>
                  <strong>{number(trace.tokens)}</strong>
                </div>
              </div>
              {trace.issues.length > 0 && (
                <SafetyNotice>
                  Trace coverage: {trace.issues.join(", ")}. Incomplete traces
                  are excluded from success and latency metrics.
                </SafetyNotice>
              )}
              {trace.truncated && (
                <SafetyNotice>
                  The span display is truncated at 2,000 spans.
                </SafetyNotice>
              )}
              <div className="investigation-grid">
                <Panel
                  title="Execution waterfall"
                  description="Relative offsets · parent hierarchy · wall-clock timing"
                >
                  <div className="waterfall-ruler">
                    <span>Operation / service</span>
                    <span>0 → {number(length / 1e6, 2)} ms</span>
                  </div>
                  <VirtualSpanList count={trace.spans.length}>
                    {(start, end) =>
                      trace.spans.slice(start, end).map((s, index) => (
                        <button
                          className={`span-row ${span?.span_id === s.span_id ? "selected" : ""} ${critical.has(s.span_id) ? "critical-path" : ""}`}
                          key={s.span_id}
                          data-span-index={start + index}
                          aria-label={`${s.operation} · ${s.service} · ${s.status}${critical.has(s.span_id) ? " · critical path" : ""} · ${s.end_ns ? `${number((Number(s.end_ns) - Number(s.start_ns)) / 1e6, 2)} ms` : "incomplete"}, span ${start + index + 1} of ${trace.spans.length}`}
                          onClick={() => setSelected(s.span_id)}
                          aria-pressed={span?.span_id === s.span_id}
                        >
                          <span
                            className="span-label"
                            style={{
                              paddingLeft: `${8 + (depths.get(s.span_id) ?? 0) * 12}px`,
                            }}
                          >
                            <GitBranch size={13} />
                            <span>
                              <strong>{s.operation}</strong>
                              <small>
                                {s.service} · {s.status}
                                {critical.has(s.span_id)
                                  ? " · critical path"
                                  : ""}
                              </small>
                            </span>
                          </span>
                          <span className="span-track">
                            <span
                              className={`span-bar ${s.status === "error" ? "failed" : ""}`}
                              style={{
                                left: `${((Number(s.start_ns) - first) / length) * 100}%`,
                                width: `${Math.max(1, (((Number(s.end_ns) || Number(s.start_ns)) - Number(s.start_ns)) / length) * 100)}%`,
                              }}
                            />
                            <span className="span-duration">
                              {s.end_ns
                                ? `${number((Number(s.end_ns) - Number(s.start_ns)) / 1e6, 2)} ms`
                                : "incomplete"}
                            </span>
                          </span>
                        </button>
                      ))
                    }
                  </VirtualSpanList>
                </Panel>
                <Panel title="Evidence inspector" description={span?.span_id}>
                  {span && (
                    <>
                      <div
                        className="tabs"
                        role="tablist"
                        aria-label="Span inspector"
                      >
                        {["attributes", "links", "privacy"].map((t) => (
                          <button
                            key={t}
                            id={`tab-${t}`}
                            role="tab"
                            aria-selected={tab === t}
                            aria-controls="span-panel"
                            tabIndex={tab === t ? 0 : -1}
                            className={tab === t ? "active" : ""}
                            onKeyDown={(e) => {
                              const list = ["attributes", "links", "privacy"];
                              if (
                                e.key === "ArrowRight" ||
                                e.key === "ArrowLeft"
                              ) {
                                const next =
                                  list[
                                    (list.indexOf(t) +
                                      (e.key === "ArrowRight" ? 1 : 2)) %
                                      3
                                  ];
                                setTab(next);
                                document.getElementById(`tab-${next}`)?.focus();
                              }
                            }}
                            onClick={() => setTab(t)}
                          >
                            {t}
                          </button>
                        ))}
                      </div>
                      <div
                        id="span-panel"
                        role="tabpanel"
                        aria-labelledby={`tab-${tab}`}
                        className="inspector-body"
                      >
                        {tab === "attributes" ? (
                          <Json value={span.attributes} />
                        ) : tab === "links" ? (
                          <Json value={span.links} />
                        ) : (
                          <>
                            <SafetyNotice>{trace.privacy}</SafetyNotice>
                            <p>
                              {span.redacted_count} attributes or events removed
                              before storage. Full exception payloads are
                              excluded.
                            </p>
                          </>
                        )}
                      </div>
                    </>
                  )}
                </Panel>
              </div>
            </>
          );
        }}
      </Resource>
    </>
  );
}
export function ServicesPage({
  scope,
  graph,
}: {
  scope: Scope;
  graph: boolean;
}) {
  const data = useResource<Services>(
    `/services?project_id=${scope.project.id}&hours=${scope.hours}`,
    scope.refresh,
  );
  return (
    <>
      <PageHeading
        title={graph ? "Service Map" : "System Health"}
        description="Observed service dependencies and span-level measurements."
      />
      <Resource state={data}>
        {(services) => (
          <>
            {graph && (
              <Panel
                title="Observed topology"
                description="Directed edges come from parent-child span relationships; no inferred links."
              >
                {services.items.length ? (
                  <>
                    <div className="service-map">
                      {services.items.map((s) => (
                        <Link
                          key={s.name}
                          href={`${scope.base}/traces?service=${encodeURIComponent(s.name)}`}
                          className="service-node"
                        >
                          <span className="service-node-icon">
                            <Activity size={22} />
                          </span>
                          <strong>{s.name}</strong>
                          <Status value={s.status} />
                          <span>
                            {s.calls} spans · {number(s.p95_ms, 1)} ms P95
                          </span>
                        </Link>
                      ))}
                    </div>
                    <div
                      className="edge-list"
                      aria-label="Directed dependency list"
                    >
                      {services.edges.length ? (
                        services.edges.map((e) => (
                          <div key={`${e.source}:${e.target}`}>
                            <span>{e.source}</span>
                            <ArrowRight size={17} />
                            <span>{e.target}</span>
                            <small>{e.provenance}</small>
                          </div>
                        ))
                      ) : (
                        <p>
                          No cross-service parent-child relationships observed
                          in this window.
                        </p>
                      )}
                    </div>
                  </>
                ) : (
                  <Empty
                    title="No topology observed"
                    href={`${scope.base}/projects`}
                  />
                )}
              </Panel>
            )}
            <Panel
              title="Service health"
              description="Observed means spans were received; it is not an availability or SLO guarantee."
            >
              {services.items.length ? (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Service</th>
                        <th>State</th>
                        <th>Calls</th>
                        <th>Errors</th>
                        <th>P95 latency</th>
                        <th>Last received</th>
                      </tr>
                    </thead>
                    <tbody>
                      {services.items.map((s) => (
                        <tr key={s.name}>
                          <td>
                            <Link
                              className="row-link"
                              href={`${scope.base}/traces?service=${encodeURIComponent(s.name)}`}
                            >
                              {s.name}
                            </Link>
                          </td>
                          <td>
                            <Status value={s.status} />
                          </td>
                          <td>{s.calls}</td>
                          <td>{s.errors}</td>
                          <td>{number(s.p95_ms, 1)} ms</td>
                          <td>{date(s.last_seen)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <Empty
                  title="No service measurements"
                  href={`${scope.base}/projects`}
                />
              )}
            </Panel>
            <SafetyNotice>
              SLO objectives, burn rates, and deployment health probes are not
              configured in this release. Received telemetry alone cannot
              establish service availability.
            </SafetyNotice>
          </>
        )}
      </Resource>
    </>
  );
}
export function AnalyticsPage({ scope, mode }: { scope: Scope; mode: string }) {
  const state = useResource<Analytics>(
    `/analytics?project_id=${scope.project.id}&hours=${scope.hours}`,
    scope.refresh,
  );
  const title =
    mode === "models"
      ? "Model Performance"
      : mode === "tools"
        ? "Tool Analytics"
        : "Token & Cost";
  return (
    <>
      <PageHeading
        title={title}
        description="Measured semantic attributes from your OpenTelemetry spans."
      />
      <Resource state={state}>
        {(data) => (
          <>
            {mode === "usage" ? (
              <>
                <div className="summary-grid">
                  <Panel title="Input tokens">
                    <div className="big-number">
                      {number(data.input_tokens)}
                    </div>
                  </Panel>
                  <Panel title="Output tokens">
                    <div className="big-number">
                      {number(data.output_tokens)}
                    </div>
                  </Panel>
                  <Panel title="Estimated cost">
                    <div className="big-number">—</div>
                    <p className="panel-note">No pricing source configured</p>
                  </Panel>
                </div>
                <SafetyNotice>
                  {data.usage_coverage} of {data.span_count} spans include usage
                  metadata. These are reported span totals, which may overlap
                  across ancestors; billing and execution totals cannot be
                  inferred.
                </SafetyNotice>
              </>
            ) : null}
            <Panel
              title={mode === "tools" ? "Observed tools" : "Observed models"}
            >
              {mode === "tools" ? (
                data.tools.length ? (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Tool</th>
                          <th>Calls</th>
                          <th>Errors</th>
                          <th>P95 ms</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.tools.map((t) => (
                          <tr key={t.name}>
                            <td>{t.name}</td>
                            <td>{t.calls}</td>
                            <td>{t.errors}</td>
                            <td>{number(t.p95_ms, 1)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <Empty title="No tool calls observed">
                    Include gen_ai.operation.name=execute_tool and
                    gen_ai.tool.name as metadata.
                  </Empty>
                )
              ) : data.models.length ? (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Model</th>
                        <th>Provider</th>
                        <th>Calls</th>
                        <th>Errors</th>
                        <th>P95 ms</th>
                        <th>Input tokens</th>
                        <th>Output tokens</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.models.map((m) => (
                        <tr key={`${m.provider}:${m.model}`}>
                          <td>{m.model}</td>
                          <td>{m.provider}</td>
                          <td>{m.calls}</td>
                          <td>{m.errors}</td>
                          <td>{number(m.p95_ms, 1)}</td>
                          <td>{number(m.input_tokens)}</td>
                          <td>{number(m.output_tokens)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <Empty title="No model metadata received">
                  Include gen_ai.request.model, provider and usage attributes in
                  your model spans.
                </Empty>
              )}
            </Panel>
          </>
        )}
      </Resource>
    </>
  );
}
