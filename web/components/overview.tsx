"use client";
import Link from "next/link";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  CheckCheck,
  CircleDollarSign,
  Clock3,
  Cpu,
  Radar,
  ShieldAlert,
  Workflow,
  Zap,
} from "lucide-react";
import { date, number, useResource } from "@/lib/api";
import type { Incident, Page, Summary } from "@/lib/types";
import type { Scope } from "./console";
import {
  Badge,
  Empty,
  PageHeading,
  Panel,
  Resource,
  Status,
} from "./primitives";

export function Overview({ scope }: { scope: Scope }) {
  const query = `project_id=${scope.project.id}&hours=${scope.hours}`;
  const summary = useResource<Summary>(
    `/metrics/summary?${query}`,
    scope.refresh,
  );
  const incidents = useResource<Page<Incident>>(
    `/incidents?project_id=${scope.project.id}&limit=8&status=active`,
    scope.refresh,
  );
  return (
    <>
      <PageHeading
        title="Command Center"
        description="The operational pulse of your AI systems."
      >
        {["admin", "operator"].includes(scope.identity.role) && (
          <a className="button" href={`/api/v1/exports/summary?${query}`}>
            <ArrowDownToLine size={15} />
            Export snapshot
          </a>
        )}
        <Link className="button primary" href={`${scope.base}/projects`}>
          <Zap size={15} />
          Connect application
        </Link>
      </PageHeading>
      <Resource state={summary}>
        {(data) => (
          <>
            <div className="section-meta">
              <span className="section-label">
                <span className="measured-dot" />
                PERSISTED TELEMETRY
              </span>
              <span>
                {data.executions
                  ? `Calculated ${date(data.calculated_at)}`
                  : "Awaiting your first execution"}{" "}
                · Polls every 30s while visible
              </span>
            </div>
            <div className="metric-grid">
              {[
                {
                  label: "Success rate",
                  value: number(data.success_rate, 2),
                  unit: data.success_rate == null ? "" : "%",
                  caption: `${number(data.eligible_count)} eligible executions`,
                  icon: CheckCheck,
                  tone: "green",
                  href: `${scope.base}/traces?status=ok`,
                },
                {
                  label: "Total executions",
                  value: number(data.executions),
                  unit: "",
                  caption: `Across the last ${scope.hours} hours`,
                  icon: Workflow,
                  tone: "blue",
                  href: `${scope.base}/traces`,
                },
                {
                  label: "P95 latency",
                  value: number(data.p95_ms, 1),
                  unit: data.p95_ms == null ? "" : "ms",
                  caption: "Root wall-clock · nearest-rank",
                  icon: Clock3,
                  tone: "purple",
                  href: `${scope.base}/traces`,
                },
                {
                  label: "Active incidents",
                  value: number(data.active_incidents),
                  unit: "",
                  caption: "Open + acknowledged",
                  icon: ShieldAlert,
                  tone: data.active_incidents ? "amber" : "blue",
                  href: `${scope.base}/incidents`,
                },
                {
                  label: "Token usage",
                  value: number(data.tokens),
                  unit: "",
                  caption: `${data.token_trace_coverage} traces with attributed usage`,
                  icon: Cpu,
                  tone: "cyan",
                  href: `${scope.base}/usage`,
                },
                {
                  label: "Estimated cost",
                  value: "—",
                  unit: "",
                  caption: "Pricing source not configured",
                  icon: CircleDollarSign,
                  tone: "green",
                  href: `${scope.base}/usage`,
                },
              ].map((metric) => (
                <Link
                  href={metric.href}
                  key={metric.label}
                  className="metric-card"
                >
                  <div className="metric-label">
                    <span>{metric.label}</span>
                    <metric.icon size={16} className={`text-${metric.tone}`} />
                  </div>
                  <div className="metric-value">
                    {metric.value}
                    <span>{metric.unit}</span>
                  </div>
                  <div className="metric-caption">
                    {metric.caption}
                    <ArrowUpRight size={13} />
                  </div>
                </Link>
              ))}
            </div>
            <div className="chart-grid">
              <Panel
                title="Execution latency"
                description="Root-span duration · milliseconds (ms)"
                action={<Badge tone="neutral">{scope.hours}h window</Badge>}
              >
                <LatencyChart data={data} />
                <div className="chart-footer">
                  <span>
                    {data.eligible_count} eligible samples · Gaps mean no data
                  </span>
                  <Link href={`${scope.base}/traces`}>
                    Explore traces
                    <ArrowRight size={13} />
                  </Link>
                </div>
              </Panel>
              <Panel
                title="Failure breakdown"
                description="Execution outcomes in this window"
              >
                <FailureChart summary={data} base={scope.base} />
              </Panel>
            </div>
            <Panel
              title="Active incidents"
              description="Prioritize, investigate, and act with evidence."
              action={
                <Link className="text-link" href={`${scope.base}/incidents`}>
                  View all incidents
                  <ArrowRight size={14} />
                </Link>
              }
            >
              <Resource state={incidents}>
                {(items) => {
                  const active = items.items.filter(
                    (i) => i.status !== "RESOLVED",
                  );
                  return active.length ? (
                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Severity</th>
                            <th>Incident</th>
                            <th>Evidence</th>
                            <th>Status</th>
                            <th>Detected</th>
                          </tr>
                        </thead>
                        <tbody>
                          {active.map((i) => (
                            <tr key={i.id}>
                              <td>
                                <Status value={i.severity} />
                              </td>
                              <td>
                                <Link
                                  className="row-link"
                                  href={`${scope.base}/incidents/${i.id}`}
                                >
                                  {i.title}
                                </Link>
                              </td>
                              <td>{i.sample_count} samples</td>
                              <td>
                                <Status value={i.status} />
                              </td>
                              <td className="muted">{date(i.created_at)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <Empty title="No active incidents">
                      {data.executions
                        ? "No active incidents were found. Detection requires an enabled rule with enough samples."
                        : "Connect your application and configure a detection rule to start monitoring."}
                      <Link
                        className="text-link empty-inline"
                        href={`${scope.base}/rules`}
                      >
                        Configure detection
                        <ArrowRight size={13} />
                      </Link>
                    </Empty>
                  );
                }}
              </Resource>
            </Panel>
            <div className="bottom-grid">
              <Panel
                title="Processing pipeline"
                action={<Activity size={16} className="text-blue" />}
              >
                <div className="pipeline-stats">
                  <div>
                    <span className="stat-label">Queued / running</span>
                    <strong>
                      {(data.jobs.QUEUED ?? 0) + (data.jobs.RUNNING ?? 0)}
                    </strong>
                  </div>
                  <div>
                    <span className="stat-label">Completed jobs</span>
                    <strong>{data.jobs.COMPLETED ?? 0}</strong>
                  </div>
                  <div>
                    <span className="stat-label">Dead letter</span>
                    <strong
                      className={
                        (data.jobs.DEAD_LETTER ?? 0) ? "text-amber" : ""
                      }
                    >
                      {data.jobs.DEAD_LETTER ?? 0}
                    </strong>
                  </div>
                </div>
                <p className="panel-note">
                  Durable PostgreSQL jobs · Failed jobs retry up to 5 times.
                </p>
              </Panel>
              <Panel
                title="Changes under control"
                action={<Radar size={16} className="text-blue" />}
              >
                <div className="control-summary">
                  <span className="control-icon">
                    <ShieldAlert size={24} />
                  </span>
                  <div>
                    <strong>Remote execution is disabled</strong>
                    <p>
                      Record proposals and review evidence. An isolated executor
                      is required for validation and approval.
                    </p>
                    <Link
                      className="text-link"
                      href={`${scope.base}/remediations`}
                    >
                      Open Remediation Center
                      <ArrowRight size={13} />
                    </Link>
                  </div>
                </div>
              </Panel>
            </div>
          </>
        )}
      </Resource>
    </>
  );
}
function LatencyChart({ data }: { data: Summary }) {
  const points = data.series;
  const peak = Math.max(1, ...points.map((p) => p.p99 ?? 0));
  const max = Math.ceil(peak / 10) * 10;
  const series = [
    { key: "p50", color: "#60A5FA", name: "P50" },
    { key: "p95", color: "#A78BFA", name: "P95" },
    { key: "p99", color: "#34D399", name: "P99" },
  ] as const;
  const hasData = points.some((p) => p.sample_count > 0);
  return (
    <div className="latency-chart">
      <div className="chart-legend">
        {series.map((s) => (
          <span key={s.key}>
            <i style={{ background: s.color }} />
            {s.name}
          </span>
        ))}
      </div>
      <div className="chart-canvas">
        <div className="chart-y-axis" aria-hidden="true">
          {[4, 3, 2, 1, 0].map((i) => (
            <span key={i}>{hasData ? number((max * i) / 4) : "—"}</span>
          ))}
        </div>
        <div className="chart-x-axis" aria-hidden="true">
          {[0, 6, 12, 18, 23].map((i) => (
            <span key={i}>
              {new Date(points[i].at).toLocaleTimeString(undefined, {
                hour: "2-digit",
                minute: "2-digit",
                hour12: false,
              })}
            </span>
          ))}
        </div>
        <svg
          role="img"
          aria-label={`Latency percentiles in milliseconds. ${data.eligible_count} eligible samples. ${hasData ? "Open chart data for exact values." : "No measured samples in this window."}`}
          viewBox="0 0 720 200"
          preserveAspectRatio="none"
        >
          {[0, 1, 2, 3, 4].map((i) => (
            <g key={i}>
              <line
                x1="52"
                y1={12 + i * 40}
                x2="708"
                y2={12 + i * 40}
                stroke="#293548"
                strokeDasharray="3 5"
              />
              <text
                x="40"
                y={16 + i * 40}
                textAnchor="end"
                fill="#94A3B8"
                fontSize="10"
              >
                {hasData ? number((max * (4 - i)) / 4) : "—"}
              </text>
            </g>
          ))}
          {series.map((s) => {
            let d = "",
              connected = false;
            for (let i = 0; i < points.length; i++) {
              const value = points[i][s.key];
              if (value == null) {
                connected = false;
                continue;
              }
              d += `${connected ? "L" : "M"}${52 + (i * 656) / 23},${172 - (value / max) * 160} `;
              connected = true;
            }
            return (
              <g key={s.key}>
                <path
                  d={d}
                  fill="none"
                  stroke={s.color}
                  strokeWidth="2"
                  vectorEffect="non-scaling-stroke"
                />
                {points.map((p, i) =>
                  p[s.key] == null ? null : (
                    <circle
                      key={i}
                      cx={52 + (i * 656) / 23}
                      cy={172 - (p[s.key]! / max) * 160}
                      r="3"
                      fill={s.color}
                    >
                      <title>
                        {new Date(p.at).toISOString()} · {s.name}:{" "}
                        {number(p[s.key], 2)} ms · {p.sample_count} samples
                      </title>
                    </circle>
                  ),
                )}
              </g>
            );
          })}
          {[0, 6, 12, 18, 23].map((i) => (
            <text
              key={i}
              x={52 + (i * 656) / 23}
              y="195"
              textAnchor={i === 23 ? "end" : "middle"}
              fill="#94A3B8"
              fontSize="10"
            >
              {new Date(points[i].at).toLocaleTimeString(undefined, {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </text>
          ))}
        </svg>
        {!hasData && (
          <div className="chart-no-data">
            <Activity size={22} />
            <strong>Waiting for telemetry</strong>
            <span>
              Latency percentiles will appear after completed traces arrive.
            </span>
          </div>
        )}
      </div>
      <details className="chart-data">
        <summary>
          Inspect chart data ·{" "}
          {Intl.DateTimeFormat().resolvedOptions().timeZone}
        </summary>
        <div className="table-wrap">
          <table>
            <caption className="sr-only">
              Latency percentile values in milliseconds by time bucket
            </caption>
            <thead>
              <tr>
                <th>Bucket start</th>
                <th>Samples</th>
                <th>P50 ms</th>
                <th>P95 ms</th>
                <th>P99 ms</th>
              </tr>
            </thead>
            <tbody>
              {points.map((p) => (
                <tr key={p.at}>
                  <td>{date(p.at)}</td>
                  <td>{p.sample_count}</td>
                  <td>{number(p.p50, 2)}</td>
                  <td>{number(p.p95, 2)}</td>
                  <td>{number(p.p99, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
function FailureChart({ summary, base }: { summary: Summary; base: string }) {
  const errors = summary.failures.reduce((total, f) => total + f.count, 0);
  const rate = summary.executions ? (errors / summary.executions) * 100 : 0;
  return (
    <div className="failure-content">
      <div
        className="donut"
        role="img"
        aria-label={`${errors} failed or incomplete executions out of ${summary.executions}`}
        style={{
          background: `conic-gradient(#EF4444 0% ${rate}%, #243247 ${rate}% 100%)`,
        }}
      >
        <div>
          <strong>{errors}</strong>
          <span>errors & incomplete</span>
        </div>
      </div>
      <div className="failure-legend">
        {summary.failures.map((f, i) => (
          <Link
            key={f.category}
            href={`${base}/traces?status=${i === 0 ? "error" : "incomplete"}`}
          >
            <span>
              <i style={{ background: i === 0 ? "#EF4444" : "#F59E0B" }} />
              {f.category}
            </span>
            <strong>{f.count}</strong>
          </Link>
        ))}
      </div>
      <p className="panel-note">
        {summary.executions
          ? `${summary.executions} measured executions`
          : "No executions received in this window"}
      </p>
    </div>
  );
}
