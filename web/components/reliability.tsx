"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  GitCommit,
  Plus,
  ShieldAlert,
} from "lucide-react";
import { date, mutation, number, useResource } from "@/lib/api";
import type {
  ChangeEvent,
  Detection,
  Hypothesis,
  Incident,
  IncidentNote,
  Page,
  Rule,
  RulePreview,
  RuleVersion,
  SLO,
} from "@/lib/types";
import type { Scope } from "./console";
import {
  Badge,
  Empty,
  ErrorState,
  Field,
  PageHeading,
  Panel,
  Resource,
  SafetyNotice,
  Status,
  Submit,
} from "./primitives";

function RuleForm({
  scope,
  initial,
  isEdit,
  ruleId,
  onSaved,
  onCancel,
}: {
  scope: Scope;
  initial?: Partial<Rule>;
  isEdit?: boolean;
  ruleId?: string;
  onSaved?: () => void;
  onCancel?: () => void;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error>();
  const [preview, setPreview] = useState<RulePreview>();

  function payload(formElement: HTMLFormElement) {
    const form = new FormData(formElement);
    return {
      name: form.get("name"),
      metric: form.get("metric"),
      detector: form.get("detector"),
      threshold: Number(form.get("threshold")),
      sensitivity: Number(form.get("sensitivity")),
      ewma_alpha: Number(form.get("ewma_alpha")),
      min_samples: Number(form.get("min_samples")),
      window_minutes: Number(form.get("window_minutes")),
      cooldown_minutes: Number(form.get("cooldown_minutes")),
      severity: form.get("severity"),
    };
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      if (isEdit && ruleId) {
        await mutation(
          `/rules/${encodeURIComponent(ruleId)}?project_id=${scope.project.id}`,
          payload(event.currentTarget),
          "PATCH",
        );
        scope.reload();
        scope.notify("Detection rule updated. New version recorded.");
      } else {
        await mutation(
          `/rules?project_id=${scope.project.id}`,
          payload(event.currentTarget),
        );
        scope.reload();
        scope.notify(
          "Detection rule saved. Historical window queued for evaluation.",
        );
      }
      if (onSaved) {
        onSaved();
      } else {
        router.push(`${scope.base}/rules`);
      }
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }

  async function dryRun(form: HTMLFormElement) {
    if (!form.reportValidity()) return;
    setBusy(true);
    setError(undefined);
    try {
      const result = await mutation<RulePreview>(
        `/rules/preview?project_id=${scope.project.id}`,
        payload(form),
      );
      setPreview(result);
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel
      title={isEdit ? "Edit rule configuration" : "Rule builder"}
      description="Threshold, EWMA, and robust MAD detectors evaluate completed eligible traces. Statistical detectors require both the absolute guard and anomaly score."
    >
      {error && <ErrorState error={error} />}
      <form onSubmit={save} className="form-grid">
        <Field label="Rule name">
          <input
            name="name"
            required
            minLength={2}
            maxLength={100}
            placeholder="Execution error rate"
            defaultValue={initial?.name ?? ""}
          />
        </Field>
        <Field label="Metric">
          <select name="metric" defaultValue={initial?.metric ?? "error_rate"}>
            <option value="error_rate">Error rate (%)</option>
            <option value="p95_latency_ms">P95 root latency (ms)</option>
          </select>
        </Field>
        <Field label="Detector">
          <select
            name="detector"
            defaultValue={initial?.detector ?? "threshold"}
          >
            <option value="threshold">Static threshold</option>
            <option value="ewma">EWMA baseline</option>
            <option value="robust_mad">Robust median / MAD</option>
          </select>
        </Field>
        <Field label="Threshold">
          <input
            name="threshold"
            type="number"
            min={0}
            max={3600000}
            step="any"
            required
            defaultValue={initial?.threshold ?? 10}
          />
        </Field>
        <Field label="Anomaly sensitivity (σ)">
          <input
            name="sensitivity"
            type="number"
            min={1}
            max={20}
            step="0.1"
            required
            defaultValue={initial?.sensitivity ?? 3}
          />
        </Field>
        <Field label="EWMA alpha">
          <input
            name="ewma_alpha"
            type="number"
            min="0.01"
            max={1}
            step="0.01"
            required
            defaultValue={initial?.ewma_alpha ?? 0.3}
          />
        </Field>
        <Field label="Minimum samples">
          <input
            name="min_samples"
            type="number"
            min={1}
            max={10000}
            required
            defaultValue={initial?.min_samples ?? 10}
          />
        </Field>
        <Field label="Window (minutes)">
          <input
            name="window_minutes"
            type="number"
            min={1}
            max={1440}
            required
            defaultValue={initial?.window_minutes ?? 15}
          />
        </Field>
        <Field label="Cooldown (minutes)">
          <input
            name="cooldown_minutes"
            type="number"
            min={1}
            max={1440}
            required
            defaultValue={initial?.cooldown_minutes ?? 30}
          />
        </Field>
        <Field label="Severity">
          <select name="severity" defaultValue={initial?.severity ?? "high"}>
            <option value="high">High</option>
            <option value="critical">Critical</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
        </Field>
        <div className="form-actions">
          <button
            className="button"
            type="button"
            disabled={busy}
            onClick={(event) => dryRun(event.currentTarget.form!)}
          >
            Dry-run current window
          </button>
          <button
            className="button"
            type="button"
            onClick={onCancel ?? (() => router.push(`${scope.base}/rules`))}
          >
            Cancel
          </button>
          <Submit busy={busy}>{isEdit ? "Update rule" : "Save rule"}</Submit>
        </div>
      </form>
      {preview && (
        <div className="preview-result" role="status">
          <Status value={preview.state} />
          <span>{preview.sample_count} eligible samples</span>
          <span>Observed {number(preview.observed, 2)}</span>
          <span>Baseline {number(preview.baseline, 2)}</span>
          <span>Score {number(preview.anomaly_score, 2)}</span>
          <strong>
            {preview.would_fire ? "Would fire" : "Would not fire"}
          </strong>
          <small>{preview.limitations}</small>
        </div>
      )}
    </Panel>
  );
}

function RuleEditPage({ scope, ruleId }: { scope: Scope; ruleId: string }) {
  const router = useRouter();
  const ruleState = useResource<Rule>(
    `/rules/${encodeURIComponent(ruleId)}?project_id=${scope.project.id}`,
    scope.refresh,
  );
  const versionsState = useResource<Page<RuleVersion>>(
    `/rules/${encodeURIComponent(ruleId)}/versions?project_id=${scope.project.id}`,
    scope.refresh,
  );

  return (
    <>
      <Link className="back-link" href={`${scope.base}/rules`}>
        <ArrowLeft size={14} />
        Back to Detection Rules
      </Link>
      <Resource state={ruleState}>
        {(rule) => (
          <>
            <PageHeading
              title={`Edit rule: ${rule.name}`}
              description="Modify detection thresholds or detector configuration. Updates record an immutable version."
            >
              <Link className="button" href={`${scope.base}/rules/new`}>
                <Plus size={15} />
                Create new rule
              </Link>
            </PageHeading>
            <RuleForm
              scope={scope}
              initial={rule}
              isEdit={true}
              ruleId={rule.id}
              onSaved={() => router.push(`${scope.base}/rules`)}
              onCancel={() => router.push(`${scope.base}/rules`)}
            />
            <Panel
              title="Immutable version history"
              description="Every configuration transition creates an immutable record."
            >
              <Resource state={versionsState}>
                {(page) =>
                  page.items.length ? (
                    <div className="version-list">
                      {page.items.map((v) => {
                        const manifest = v.manifest as Record<string, unknown>;
                        return (
                          <div key={v.id} className="version-row">
                            <div>
                              <strong>Version {v.version}</strong>
                              <small className="muted-text">
                                {" "}
                                · {date(v.created_at)}
                              </small>
                            </div>
                            <div>
                              <span className="mono">
                                {String(manifest.detector ?? "threshold")} ·{" "}
                                {String(manifest.metric ?? "")} &gt;{" "}
                                {String(manifest.threshold ?? "")}
                              </span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <p className="panel-note">No version history found.</p>
                  )
                }
              </Resource>
            </Panel>
          </>
        )}
      </Resource>
    </>
  );
}

function RuleCreatePage({ scope }: { scope: Scope }) {
  const router = useRouter();
  return (
    <>
      <Link className="back-link" href={`${scope.base}/rules`}>
        <ArrowLeft size={14} />
        Back to Detection Rules
      </Link>
      <PageHeading
        title="Create detection rule"
        description="Configure versioned threshold, EWMA, or robust MAD rules for measured signals."
      />
      <RuleForm
        scope={scope}
        onSaved={() => router.push(`${scope.base}/rules`)}
        onCancel={() => router.push(`${scope.base}/rules`)}
      />
    </>
  );
}

function RuleListPage({ scope }: { scope: Scope }) {
  const state = useResource<Page<Rule>>(
    `/rules?project_id=${scope.project.id}`,
    scope.refresh,
  );
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [duplicateRule, setDuplicateRule] = useState<Rule | null>(null);
  const [ruleToDelete, setRuleToDelete] = useState<Rule | null>(null);
  const [deleteError, setDeleteError] = useState<Error>();
  const detections = useResource<Page<Detection>>(
    `/detections?project_id=${scope.project.id}&limit=50`,
    scope.refresh,
  );
  const canWrite = ["admin", "developer", "operator"].includes(
    scope.identity.role,
  );

  async function toggle(rule: Rule) {
    setBusy(true);
    try {
      await mutation(
        `/rules/${rule.id}?project_id=${scope.project.id}`,
        { enabled: !rule.enabled },
        "PATCH",
      );
      scope.reload();
      scope.notify(`Rule ${rule.enabled ? "disabled" : "enabled"}.`);
    } catch (e) {
      scope.notify((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(rule: Rule) {
    setBusy(true);
    setDeleteError(undefined);
    try {
      await mutation(
        `/rules/${rule.id}?project_id=${scope.project.id}`,
        null,
        "DELETE",
      );
      setRuleToDelete(null);
      scope.reload();
      scope.notify(`Rule "${rule.name}" deleted.`);
    } catch (e) {
      setDeleteError(e as Error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeading
        title="Detection Rules"
        description="Turn measured signals into actionable, evidence-linked incidents."
      >
        {canWrite && (
          <div className="table-actions">
            <Link className="button" href={`${scope.base}/rules/new`}>
              <Plus size={16} />
              New rule page
            </Link>
            <button
              className="button primary"
              onClick={() => {
                setDuplicateRule(null);
                setShow(!show);
              }}
            >
              <Plus size={16} />
              {show ? "Close builder" : "Create rule"}
            </button>
          </div>
        )}
      </PageHeading>
      {show && (
        <RuleForm
          scope={scope}
          initial={duplicateRule ?? undefined}
          onSaved={() => {
            setShow(false);
            setDuplicateRule(null);
          }}
          onCancel={() => {
            setShow(false);
            setDuplicateRule(null);
          }}
        />
      )}
      {ruleToDelete && (
        <div
          className="modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-dialog-title"
        >
          <Panel
            title={`Delete rule: ${ruleToDelete.name}`}
            description="Destructive action. Deleting this rule stops future evaluations."
          >
            <p>
              Are you sure you want to delete{" "}
              <strong>{ruleToDelete.name}</strong>? Rules with linked incidents
              cannot be deleted and must be disabled instead.
            </p>
            {deleteError && <ErrorState error={deleteError} />}
            <div className="form-actions">
              <button
                className="button"
                type="button"
                disabled={busy}
                onClick={() => {
                  setRuleToDelete(null);
                  setDeleteError(undefined);
                }}
              >
                Cancel
              </button>
              <button
                className="button danger"
                type="button"
                disabled={busy}
                onClick={() => handleDelete(ruleToDelete)}
              >
                {busy ? "Deleting…" : "Confirm delete"}
              </button>
            </div>
          </Panel>
        </div>
      )}
      <Panel
        title="Configured rules"
        description="New rules start as insufficient data until the worker evaluates the window."
      >
        <Resource state={state}>
          {(page) =>
            page.items.length ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Detector</th>
                      <th>Condition</th>
                      <th>Window / minimum</th>
                      <th>State</th>
                      <th>Version</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {page.items.map((rule) => (
                      <tr key={rule.id}>
                        <td>
                          <strong>{rule.name}</strong>
                          <small>{rule.severity}</small>
                        </td>
                        <td>
                          {rule.detector.replaceAll("_", " ")}
                          {rule.detector !== "threshold" && (
                            <small>Sensitivity {rule.sensitivity}σ</small>
                          )}
                        </td>
                        <td>
                          {rule.metric} &gt; {rule.threshold}
                          {rule.metric === "error_rate" ? "%" : " ms"}
                        </td>
                        <td>
                          {rule.window_minutes}m / {rule.min_samples} samples
                        </td>
                        <td>
                          <Status value={rule.state} />
                          <small>
                            Observed: {number(rule.last_observed, 2)}
                          </small>
                        </td>
                        <td className="mono">v{rule.version}</td>
                        <td>
                          {canWrite ? (
                            <div className="table-actions">
                              <button
                                className="button small"
                                disabled={busy}
                                onClick={() => toggle(rule)}
                                aria-label={`${rule.enabled ? "Disable" : "Enable"} ${rule.name}`}
                              >
                                {rule.enabled ? "Disable" : "Enable"}
                              </button>
                              <Link
                                className="button small"
                                href={`${scope.base}/rules/${rule.id}/edit`}
                                aria-label={`Edit ${rule.name}`}
                              >
                                Edit
                              </Link>
                              <button
                                className="button small"
                                disabled={busy}
                                onClick={() => {
                                  setDuplicateRule(rule);
                                  setShow(true);
                                }}
                                aria-label={`Duplicate ${rule.name}`}
                              >
                                Duplicate
                              </button>
                              <button
                                className="button small danger"
                                disabled={busy}
                                onClick={() => setRuleToDelete(rule)}
                                aria-label={`Delete ${rule.name}`}
                              >
                                Delete
                              </button>
                            </div>
                          ) : rule.enabled ? (
                            "Yes"
                          ) : (
                            "No"
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty title="No detection rules">
                Create a threshold rule to evaluate real execution health.
                Missing telemetry never counts as success.
              </Empty>
            )
          }
        </Resource>
      </Panel>
      <Panel
        title="Durable detection history"
        description="One idempotent record per rule and evaluation minute; normal and insufficient-data outcomes are retained."
      >
        <Resource state={detections}>
          {(page) =>
            page.items.length ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Evaluated</th>
                      <th>Detector</th>
                      <th>State</th>
                      <th>Observed / baseline</th>
                      <th>Score</th>
                      <th>Samples</th>
                    </tr>
                  </thead>
                  <tbody>
                    {page.items.map((detection) => (
                      <tr key={detection.id}>
                        <td>{date(detection.evaluated_at)}</td>
                        <td>{detection.detector.replaceAll("_", " ")}</td>
                        <td>
                          <Status value={detection.state} />
                        </td>
                        <td>
                          {number(detection.observed, 2)} /{" "}
                          {number(detection.baseline, 2)}
                        </td>
                        <td>{number(detection.anomaly_score, 2)}</td>
                        <td>{detection.sample_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty title="No evaluated detections">
                Detections are written by the background worker when eligible
                telemetry is present.
              </Empty>
            )
          }
        </Resource>
      </Panel>
      <SafetyNotice>
        Active incidents are grouped by rule and project. Cooldown prevents
        repeated incidents after resolution; minimum sample counts protect
        against sparse data. Statistical baselines use only ordered measured
        samples; missing telemetry is reported as insufficient data.
      </SafetyNotice>
    </>
  );
}

export function RulesPage({
  scope,
  id,
  subview,
}: {
  scope: Scope;
  id?: string;
  subview?: string;
}) {
  if (id === "new") {
    return <RuleCreatePage scope={scope} />;
  }
  if (id && (subview === "edit" || !subview)) {
    return <RuleEditPage scope={scope} ruleId={id} />;
  }
  return <RuleListPage scope={scope} />;
}

export function SLOsPage({ scope }: { scope: Scope }) {
  const state = useResource<Page<SLO>>(
    `/slos?project_id=${scope.project.id}`,
    scope.refresh,
  );
  const [show, setShow] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<Error>();
  const canWrite = ["admin", "developer", "operator"].includes(
    scope.identity.role,
  );
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const latency = String(form.get("latency_threshold_ms") ?? "");
    setBusy(true);
    setError(undefined);
    try {
      await mutation(`/slos?project_id=${scope.project.id}`, {
        name: form.get("name"),
        sli: form.get("sli"),
        objective: Number(form.get("objective")),
        latency_threshold_ms: latency ? Number(latency) : null,
        window_minutes: Number(form.get("window_minutes")),
        short_window_minutes: Number(form.get("short_window_minutes")),
        long_window_minutes: Number(form.get("long_window_minutes")),
        min_samples: Number(form.get("min_samples")),
      });
      setShow(false);
      scope.reload();
      scope.notify("SLO saved and queued for calculation.");
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  async function toggle(slo: SLO) {
    setBusy(true);
    setError(undefined);
    try {
      await mutation(
        `/slos/${slo.id}?project_id=${scope.project.id}`,
        { enabled: !slo.enabled },
        "PATCH",
      );
      scope.reload();
      scope.notify(`SLO ${slo.enabled ? "disabled" : "enabled"}.`);
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeading
        title="SLO Management"
        description="Measured service objectives, remaining error budget, and multi-window burn rates."
      >
        {canWrite && (
          <button className="button primary" onClick={() => setShow(!show)}>
            <Plus size={16} />
            {show ? "Close builder" : "Create SLO"}
          </button>
        )}
      </PageHeading>
      {error && <ErrorState error={error} />}
      {show && (
        <Panel
          title="Reliability objective"
          description="Short and long burn windows must fit inside the objective window. Missing or incomplete traces never become successful samples."
        >
          <form className="form-grid" onSubmit={create}>
            <Field label="SLO name">
              <input
                name="name"
                required
                minLength={2}
                maxLength={100}
                placeholder="Production request success"
              />
            </Field>
            <Field label="SLI">
              <select name="sli" defaultValue="success_rate">
                <option value="success_rate">Successful executions</option>
                <option value="latency">
                  Executions within latency threshold
                </option>
              </select>
            </Field>
            <Field label="Objective (%)">
              <input
                name="objective"
                type="number"
                min="0.01"
                max="99.99"
                step="0.01"
                defaultValue="99"
                required
              />
            </Field>
            <Field label="Latency threshold (ms, latency SLI only)">
              <input
                name="latency_threshold_ms"
                type="number"
                min="0.01"
                max="3600000"
                step="0.01"
              />
            </Field>
            <Field label="Objective window (minutes)">
              <input
                name="window_minutes"
                type="number"
                min={5}
                max={10080}
                defaultValue={1440}
                required
              />
            </Field>
            <Field label="Minimum samples">
              <input
                name="min_samples"
                type="number"
                min={1}
                max={10000}
                defaultValue={20}
                required
              />
            </Field>
            <Field label="Short burn window (minutes)">
              <input
                name="short_window_minutes"
                type="number"
                min={1}
                max={1440}
                defaultValue={5}
                required
              />
            </Field>
            <Field label="Long burn window (minutes)">
              <input
                name="long_window_minutes"
                type="number"
                min={5}
                max={10080}
                defaultValue={60}
                required
              />
            </Field>
            <div className="form-actions">
              <button
                className="button"
                type="button"
                onClick={() => setShow(false)}
              >
                Cancel
              </button>
              <Submit busy={busy}>Save SLO</Submit>
            </div>
          </form>
        </Panel>
      )}
      <Resource state={state}>
        {(page) =>
          page.items.length ? (
            <div className="slo-grid">
              {page.items.map((slo) => (
                <Panel
                  key={slo.id}
                  title={slo.name}
                  description={`${slo.sli.replaceAll("_", " ")} · ${slo.objective}% objective · ${slo.window_minutes}m window`}
                  action={<Status value={slo.latest?.status ?? "PENDING"} />}
                >
                  <div className="summary-grid compact">
                    <div>
                      <small>Compliance</small>
                      <strong>
                        {slo.latest?.compliance == null
                          ? "—"
                          : `${number(slo.latest.compliance, 2)}%`}
                      </strong>
                    </div>
                    <div>
                      <small>Error budget left</small>
                      <strong>
                        {slo.latest?.error_budget_remaining == null
                          ? "—"
                          : `${number(slo.latest.error_budget_remaining, 1)}%`}
                      </strong>
                    </div>
                    <div>
                      <small>Short / long burn</small>
                      <strong>
                        {number(slo.latest?.short_burn_rate, 2)}× /{" "}
                        {number(slo.latest?.long_burn_rate, 2)}×
                      </strong>
                    </div>
                  </div>
                  <p className="panel-note">
                    {slo.latest
                      ? `${slo.latest.good_count}/${slo.latest.eligible_count} good eligible executions · calculated ${date(slo.latest.calculated_at)}`
                      : "Awaiting durable worker calculation."}
                  </p>
                  {(slo.trend?.length ?? 0) > 0 && (
                    <div
                      className="slo-trend"
                      aria-label={`${slo.name} compliance trend`}
                    >
                      {(slo.trend ?? []).map((point) => (
                        <span
                          key={point.id}
                          title={`${date(point.calculated_at)} · ${number(point.compliance, 2)}%`}
                          style={{
                            height: `${Math.max(4, Math.min(100, point.compliance ?? 0))}%`,
                          }}
                        />
                      ))}
                    </div>
                  )}
                  {canWrite && (
                    <button
                      className="button small"
                      disabled={busy}
                      onClick={() => toggle(slo)}
                    >
                      {slo.enabled ? "Disable" : "Enable"}
                    </button>
                  )}
                </Panel>
              ))}
            </div>
          ) : (
            <Panel title="Objectives">
              <Empty title="No SLOs configured">
                Create an objective to calculate compliance and error-budget
                burn from measured traces.
              </Empty>
            </Panel>
          )
        }
      </Resource>
      <SafetyNotice>
        Burn rate is measured bad-event rate divided by the allowed error-budget
        rate. Sparse windows remain insufficient data; they are never displayed
        as healthy.
      </SafetyNotice>
    </>
  );
}

export function IncidentsPage({ scope }: { scope: Scope }) {
  const [filter, setFilter] = useState(""),
    [severity, setSeverity] = useState(""),
    [cursor, setCursor] = useState("");
  const state = useResource<Page<Incident>>(
    `/incidents?project_id=${scope.project.id}${cursor ? `&cursor=${cursor}` : ""}${filter ? `&status=${filter}` : ""}${severity ? `&severity=${severity}` : ""}`,
    scope.refresh,
  );
  return (
    <>
      <PageHeading
        title="Incidents"
        description="A shared queue for detection, investigation, and recovery."
      />
      <div className="filter-bar">
        <label className="inline-field">
          Status
          <select
            value={filter}
            onChange={(e) => {
              setFilter(e.target.value);
              setCursor("");
            }}
          >
            <option value="">All statuses</option>
            <option value="OPEN">Open</option>
            <option value="ACKNOWLEDGED">Acknowledged</option>
            <option value="RESOLVED">Resolved</option>
          </select>
        </label>
        <label className="inline-field">
          Severity
          <select
            value={severity}
            onChange={(e) => {
              setSeverity(e.target.value);
              setCursor("");
            }}
          >
            <option value="">All severities</option>
            {["critical", "high", "medium", "low"].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </label>
      </div>
      <Panel title="Incident queue">
        <Resource state={state}>
          {(page) => {
            const items = page.items.filter(
              (i) =>
                (!filter || i.status === filter) &&
                (!severity || i.severity === severity),
            );
            return (
              <>
                {items.length ? (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Severity</th>
                          <th>Incident</th>
                          <th>Observed / threshold</th>
                          <th>Samples</th>
                          <th>Status</th>
                          <th>Detected</th>
                        </tr>
                      </thead>
                      <tbody>
                        {items.map((i) => (
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
                                <small className="mono">
                                  {i.id.slice(0, 8)}
                                </small>
                              </Link>
                            </td>
                            <td>
                              {number(i.observed, 2)} / {i.threshold}
                            </td>
                            <td>{i.sample_count}</td>
                            <td>
                              <Status value={i.status} />
                            </td>
                            <td>{date(i.created_at)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <Empty title="No matching incidents">
                    Incidents appear when enabled rules exceed their thresholds
                    with enough samples.
                  </Empty>
                )}
                <div className="pagination">
                  <span>Filters apply across all incident records</span>
                  <div>
                    {cursor && (
                      <button
                        className="button small"
                        onClick={() => setCursor("")}
                      >
                        First page
                      </button>
                    )}
                    {page.next_cursor && (
                      <button
                        className="button small"
                        onClick={() => setCursor(page.next_cursor!)}
                      >
                        Next page
                      </button>
                    )}
                  </div>
                </div>
              </>
            );
          }}
        </Resource>
      </Panel>
    </>
  );
}
export function IncidentPage({ scope, id }: { scope: Scope; id: string }) {
  const state = useResource<Incident>(
    `/incidents/${encodeURIComponent(id)}?project_id=${scope.project.id}`,
    scope.refresh,
  );
  const hypotheses = useResource<
    Page<Hypothesis> & { state: string; limitations: string }
  >(
    `/incidents/${encodeURIComponent(id)}/hypotheses?project_id=${scope.project.id}`,
    scope.refresh,
  );
  const changes = useResource<Page<ChangeEvent>>(
    `/changes?project_id=${scope.project.id}&limit=20`,
    scope.refresh,
  );
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<Error>(),
    [showChange, setShowChange] = useState(false);
  const canRecordChange = ["admin", "developer", "operator"].includes(
    scope.identity.role,
  );
  async function transition(status: string) {
    setBusy(true);
    try {
      await mutation(
        `/incidents/${id}?project_id=${scope.project.id}`,
        { status },
        "PATCH",
      );
      scope.reload();
      scope.notify(`Incident ${status.toLowerCase()}.`);
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  async function recordChange(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(undefined);
    try {
      await mutation(`/changes?project_id=${scope.project.id}`, {
        kind: form.get("kind"),
        service: form.get("service"),
        version: form.get("version"),
        description: form.get("description"),
        recorded_at: new Date(String(form.get("recorded_at"))).toISOString(),
      });
      setShowChange(false);
      scope.reload();
      scope.notify(
        "Change recorded and relevant incidents queued for re-analysis.",
      );
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Link className="back-link" href={`${scope.base}/incidents`}>
        <ArrowLeft size={14} />
        Incidents
      </Link>
      <Resource state={state}>
        {(i) => (
          <>
            <PageHeading
              title={i.title}
              description={`Incident ${i.id.slice(0, 8)} · Detected ${date(i.created_at)}`}
            >
              <Status value={i.severity} />
              <Status value={i.status} />
              {["admin", "operator"].includes(scope.identity.role) && (
                <>
                  {i.status === "OPEN" && (
                    <button
                      disabled={busy}
                      className="button"
                      onClick={() => transition("ACKNOWLEDGED")}
                    >
                      Acknowledge
                    </button>
                  )}
                  <button
                    disabled={busy}
                    className="button primary"
                    onClick={() =>
                      transition(i.status === "RESOLVED" ? "OPEN" : "RESOLVED")
                    }
                  >
                    {i.status === "RESOLVED" ? "Reopen" : "Resolve incident"}
                  </button>
                </>
              )}
            </PageHeading>
            {error && <ErrorState error={error} />}
            {showChange && (
              <Panel
                title="Record deployment or configuration change"
                description="Use the actual event time. Nearby changes are correlated as evidence, never treated as proof of causality."
              >
                <form className="form-grid" onSubmit={recordChange}>
                  <Field label="Change type">
                    <select name="kind" defaultValue="deployment">
                      <option value="deployment">Deployment</option>
                      <option value="configuration">Configuration</option>
                    </select>
                  </Field>
                  <Field label="Service">
                    <input
                      name="service"
                      minLength={1}
                      maxLength={120}
                      required
                    />
                  </Field>
                  <Field label="Version or revision">
                    <input
                      name="version"
                      minLength={1}
                      maxLength={160}
                      required
                    />
                  </Field>
                  <Field label="Recorded at">
                    <input name="recorded_at" type="datetime-local" required />
                  </Field>
                  <div className="full-width">
                    <Field label="Description">
                      <textarea
                        name="description"
                        minLength={2}
                        maxLength={300}
                        rows={3}
                        required
                      />
                    </Field>
                  </div>
                  <div className="form-actions">
                    <button
                      className="button"
                      type="button"
                      onClick={() => setShowChange(false)}
                    >
                      Cancel
                    </button>
                    <Submit busy={busy}>Record change</Submit>
                  </div>
                </form>
              </Panel>
            )}
            <div className="summary-grid">
              <Panel title="Observed">
                <div className="big-number">{number(i.observed, 2)}</div>
              </Panel>
              <Panel title="Threshold">
                <div className="big-number">{i.threshold}</div>
              </Panel>
              <Panel title="Eligible samples">
                <div className="big-number">{i.sample_count}</div>
              </Panel>
            </div>
            <div className="investigation-grid">
              <Panel
                title="Ranked hypotheses"
                description="Deterministic failure localization · advisory evidence"
              >
                <Resource state={hypotheses}>
                  {(result) => (
                    <>
                      {result.items.length ? (
                        result.items.map((h) => (
                          <article className="hypothesis" key={h.id}>
                            <div className="hypothesis-heading">
                              <span className="rank">{h.rank}</span>
                              <h3>{h.title}</h3>
                              <Badge tone="warning">
                                {h.evidence_class} evidence
                              </Badge>
                            </div>
                            <p>{h.summary}</p>
                            <div className="hypothesis-metadata">
                              <span>
                                Trace coverage{" "}
                                {number(
                                  h.coverage == null ? null : h.coverage * 100,
                                  1,
                                )}
                                %
                              </span>
                              {h.dependency_context.map((dependency) => (
                                <span key={dependency}>{dependency}</span>
                              ))}
                            </div>
                            <h4>Supporting evidence</h4>
                            {h.supporting.map((s) => (
                              <Link
                                className="evidence-link"
                                key={s.span_id}
                                href={`${scope.base}/traces/${s.trace_id}`}
                              >
                                <GitBranchIcon />
                                {s.operation}
                                <span className="mono">
                                  {s.span_id.slice(0, 8)}
                                </span>
                                <ArrowRight size={13} />
                              </Link>
                            ))}
                            <h4>Contradicting evidence</h4>
                            {h.contradicting.length ? (
                              h.contradicting.map((s) => (
                                <Link
                                  className="evidence-link contradicting"
                                  key={`${s.trace_id}-${s.span_id}`}
                                  href={`${scope.base}/traces/${s.trace_id}`}
                                >
                                  <Activity size={14} />
                                  Healthy {s.operation}
                                  <span className="mono">
                                    {s.span_id.slice(0, 8)}
                                  </span>
                                  <ArrowRight size={13} />
                                </Link>
                              ))
                            ) : (
                              <p>No healthy comparison span was observed.</p>
                            )}
                            <p>{h.counterevidence}</p>
                            <h4>Correlated changes</h4>
                            {h.change_evidence.length ? (
                              h.change_evidence.map((change) => (
                                <div
                                  className="change-evidence"
                                  key={change.id}
                                >
                                  <GitCommit size={14} />
                                  <span>
                                    <strong>{change.service}</strong>{" "}
                                    {change.version}
                                    <small>
                                      {change.kind} · {date(change.recorded_at)}
                                    </small>
                                  </span>
                                </div>
                              ))
                            ) : (
                              <p>No temporally relevant recorded changes.</p>
                            )}
                            <h4>Missing measurements</h4>
                            <ul className="muted-list">
                              {h.missing.map((m) => (
                                <li key={m}>{m}</li>
                              ))}
                            </ul>
                          </article>
                        ))
                      ) : (
                        <Empty
                          title={
                            result.state === "processing"
                              ? "Diagnosis is processing"
                              : result.state === "error"
                                ? "Diagnosis could not be completed"
                                : "Insufficient evidence"
                          }
                        >
                          {result.state === "processing"
                            ? "The durable worker is reconstructing linked evidence."
                            : result.state === "error"
                              ? "The worker exhausted bounded retries. Review dead-letter telemetry before retrying."
                              : "No failed spans were found in the linked evidence. A latency threshold breach alone does not identify a cause."}
                        </Empty>
                      )}
                      <p className="panel-note">{result.limitations}</p>
                    </>
                  )}
                </Resource>
              </Panel>
              <div className="stack">
                <Panel title="Linked trace evidence">
                  <div className="evidence-list">
                    {i.evidence.map((trace) => (
                      <Link
                        className="evidence-link"
                        key={trace}
                        href={`${scope.base}/traces/${trace}`}
                      >
                        <ActivityIcon />
                        <span className="mono">{trace.slice(0, 20)}…</span>
                        <ArrowRight size={13} />
                      </Link>
                    ))}
                  </div>
                </Panel>
                <Panel title="Incident timeline">
                  <ol className="timeline">
                    {i.timeline.map((event, index) => (
                      <li key={index}>
                        <strong>{event.action.replaceAll("_", " ")}</strong>
                        <span>{event.actor}</span>
                        <small>{date(event.at)}</small>
                      </li>
                    ))}
                  </ol>
                </Panel>
                <InvestigationNotes scope={scope} incidentId={i.id} />
                <Panel
                  title="Recorded changes"
                  action={
                    canRecordChange ? (
                      <button
                        className="button small"
                        onClick={() => setShowChange(!showChange)}
                      >
                        <Plus size={14} />
                        Record
                      </button>
                    ) : undefined
                  }
                >
                  <Resource state={changes}>
                    {(page) =>
                      page.items.length ? (
                        <div className="change-list">
                          {page.items.map((change) => (
                            <div className="change-evidence" key={change.id}>
                              <GitCommit size={14} />
                              <span>
                                <strong>{change.service}</strong>{" "}
                                {change.version}
                                <small>
                                  {change.kind} · {date(change.recorded_at)}
                                </small>
                              </span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <Empty title="No changes recorded">
                          Deployment and configuration evidence is explicit and
                          tenant-scoped.
                        </Empty>
                      )
                    }
                  </Resource>
                </Panel>
                <Panel title="Next step">
                  <div className="panel-body">
                    <p>
                      Validate a proposed change with a pinned replay dataset,
                      or record a remediation proposal.
                    </p>
                    <Link
                      className="button small"
                      href={`${scope.base}/evaluations`}
                    >
                      Compare in evaluations
                      <ArrowRight size={13} />
                    </Link>
                    <Link
                      className="text-link"
                      href={`${scope.base}/remediations?incident=${i.id}`}
                    >
                      Record recovery proposal
                      <ArrowRight size={13} />
                    </Link>
                  </div>
                </Panel>
              </div>
            </div>
          </>
        )}
      </Resource>
    </>
  );
}
function InvestigationNotes({
  scope,
  incidentId,
}: {
  scope: Scope;
  incidentId: string;
}) {
  const notes = useResource<Page<IncidentNote>>(
    `/incidents/${encodeURIComponent(incidentId)}/notes?project_id=${scope.project.id}`,
    scope.refresh,
  );
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error>();
  const canWrite = ["admin", "developer", "operator"].includes(
    scope.identity.role,
  );

  async function submitNote(e: FormEvent) {
    e.preventDefault();
    if (!content.trim()) return;
    setBusy(true);
    setError(undefined);
    try {
      await mutation(
        `/incidents/${encodeURIComponent(incidentId)}/notes?project_id=${scope.project.id}`,
        { content: content.trim() },
      );
      setContent("");
      scope.reload();
      scope.notify("Investigation note recorded.");
    } catch (err) {
      setError(err as Error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel
      title="Investigation notes"
      description="Authored operator notes preserved with actor identity and timestamps."
    >
      {error && <ErrorState error={error} />}
      <Resource state={notes}>
        {(page) =>
          page.items.length ? (
            <div className="notes-list">
              {page.items.map((n) => (
                <div key={n.id} className="note-card">
                  <div className="note-header">
                    <strong>{n.author_name}</strong>
                    <small>{date(n.created_at)}</small>
                  </div>
                  <p className="note-content">{n.content}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="panel-note">No operator notes recorded yet.</p>
          )
        }
      </Resource>
      {canWrite && (
        <form onSubmit={submitNote} className="note-form">
          <Field label="Add note">
            <textarea
              aria-label="Add note content"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="Record observations, hypotheses, or external factors…"
              rows={3}
              required
              maxLength={4000}
            />
          </Field>
          <Submit busy={busy}>Add note</Submit>
        </form>
      )}
    </Panel>
  );
}

function GitBranchIcon() {
  return <ShieldAlert size={14} />;
}
function ActivityIcon() {
  return <ShieldAlert size={14} />;
}
