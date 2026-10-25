"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { ArrowLeft, ArrowRight, FlaskConical, Plus } from "lucide-react";
import { date, mutation, number, useResource } from "@/lib/api";
import type {
  Dataset,
  Evaluation,
  Incident,
  Page,
  Remediation,
} from "@/lib/types";
import type { Scope } from "./console";
import {
  Empty,
  ErrorState,
  Field,
  Json,
  PageHeading,
  Panel,
  Resource,
  SafetyNotice,
  Status,
  Submit,
} from "./primitives";

export function DatasetsPage({ scope }: { scope: Scope }) {
  const state = useResource<Page<Dataset>>(
    `/datasets?project_id=${scope.project.id}`,
    scope.refresh,
  );
  const [show, setShow] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<Error>(),
    [selected, setSelected] = useState<Dataset>();
  async function publish(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(undefined);
    try {
      const cases: unknown = JSON.parse(String(form.get("cases")));
      await mutation(`/datasets?project_id=${scope.project.id}`, {
        name: form.get("name"),
        cases,
      });
      setShow(false);
      scope.reload();
      scope.notify("Immutable dataset version published.");
    } catch (e) {
      setError(
        e instanceof SyntaxError
          ? new Error("Cases must be valid JSON.")
          : (e as Error),
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeading
        title="Dataset Library"
        description="Immutable, content-addressed fixtures for paired replay grading."
      >
        {["admin", "developer"].includes(scope.identity.role) && (
          <button className="button primary" onClick={() => setShow(!show)}>
            <Plus size={16} />
            {show ? "Close publisher" : "Publish dataset"}
          </button>
        )}
      </PageHeading>
      <SafetyNotice>
        Provide authorized evaluation data only. Expected, baseline, and
        candidate strings are stored as immutable fixtures. Live model execution
        is not part of replay grading.
      </SafetyNotice>
      {error && <ErrorState error={error} />}
      {show && (
        <Panel
          title="Publish immutable version"
          description="Each publication creates a new version-1 dataset with a SHA-256 manifest. Existing fixtures cannot be edited."
        >
          <form onSubmit={publish} className="form-grid">
            <Field label="Dataset name">
              <input
                name="name"
                minLength={2}
                maxLength={100}
                required
                placeholder="Retrieval correctness · candidate v2"
              />
            </Field>
            <div className="full-width">
              <Field
                label="Paired cases (JSON array)"
                hint="1–500 cases. Each case: unique id, expected, baseline_output, candidate_output. Output strings: at most 256 characters."
              >
                <textarea
                  name="cases"
                  required
                  rows={10}
                  maxLength={500000}
                  spellCheck={false}
                  placeholder={
                    '[\n  { "id": "case-1", "expected": "your expected answer",\n    "baseline_output": "observed baseline", "candidate_output": "observed candidate" }\n]'
                  }
                />
              </Field>
            </div>
            <div className="form-actions">
              <button
                type="button"
                className="button"
                onClick={() => setShow(false)}
              >
                Cancel
              </button>
              <Submit busy={busy}>Publish immutable dataset</Submit>
            </div>
          </form>
        </Panel>
      )}
      <Panel title="Published datasets">
        <Resource state={state}>
          {(page) =>
            page.items.length ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Version</th>
                      <th>Cases</th>
                      <th>Content hash</th>
                      <th>Published</th>
                    </tr>
                  </thead>
                  <tbody>
                    {page.items.map((d) => (
                      <tr key={d.id}>
                        <td>
                          <button
                            className="link-button"
                            onClick={() => setSelected(d)}
                          >
                            {d.name}
                          </button>
                        </td>
                        <td>v{d.version}</td>
                        <td>{d.case_count}</td>
                        <td className="mono">
                          {d.manifest_hash.slice(0, 16)}…
                        </td>
                        <td>{date(d.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty title="No published datasets">
                Publish authorized paired fixtures to make comparisons
                reproducible.
              </Empty>
            )
          }
        </Resource>
      </Panel>
      {selected && (
        <Panel
          title={selected.name}
          action={
            <button
              className="button small"
              onClick={() => setSelected(undefined)}
            >
              Close inspector
            </button>
          }
        >
          <Json value={selected} />
        </Panel>
      )}
    </>
  );
}
export function EvaluationsPage({ scope }: { scope: Scope }) {
  const state = useResource<Page<Evaluation>>(
    `/evaluations?project_id=${scope.project.id}`,
    scope.refresh,
  );
  const [show, setShow] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<Error>();
  const datasets = useResource<Page<Dataset>>(
    show ? `/datasets?project_id=${scope.project.id}` : null,
    scope.refresh,
  );
  async function launch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(undefined);
    try {
      const run = await mutation<Evaluation>(
        `/evaluations?project_id=${scope.project.id}`,
        {
          dataset_id: form.get("dataset_id"),
          baseline: form.get("baseline"),
          candidate: form.get("candidate"),
        },
        "POST",
        true,
      );
      setShow(false);
      scope.reload();
      scope.notify(`Replay evaluation ${run.id.slice(0, 8)} queued.`);
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeading
        title="Evaluation Runs"
        description="Compare changes against a pinned, reproducible evidence set."
      >
        {["admin", "developer"].includes(scope.identity.role) && (
          <button className="button primary" onClick={() => setShow(!show)}>
            <FlaskConical size={16} />
            {show ? "Close setup" : "New replay evaluation"}
          </button>
        )}
      </PageHeading>
      <SafetyNotice>
        Offline paired replay · Exact-match grader v1 · No remote model calls.
        Decisions use a paired 95% Hoeffding interval and require at least 30
        cases; uncertain results are INCONCLUSIVE.
      </SafetyNotice>
      {error && <ErrorState error={error} />}
      {show && (
        <Panel title="Configure replay evaluation">
          <Resource state={datasets}>
            {(page) =>
              page.items.length ? (
                <form onSubmit={launch} className="form-grid">
                  <Field label="Immutable dataset version">
                    <select required name="dataset_id">
                      {page.items.map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.name} / v{d.version} / {d.case_count} cases
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Baseline manifest label">
                    <input
                      name="baseline"
                      required
                      maxLength={100}
                      placeholder="baseline-config-v1"
                    />
                  </Field>
                  <Field label="Candidate manifest label">
                    <input
                      name="candidate"
                      required
                      maxLength={100}
                      placeholder="candidate-config-v2"
                    />
                  </Field>
                  <div className="full-width">
                    <p className="panel-note">
                      Labels identify the outputs you supplied in the dataset.
                      They do not fetch or execute configurations. Dataset hash
                      and grader version are pinned in the run manifest.
                    </p>
                  </div>
                  <div className="form-actions">
                    <button
                      type="button"
                      className="button"
                      onClick={() => setShow(false)}
                    >
                      Cancel
                    </button>
                    <Submit busy={busy}>Queue replay evaluation</Submit>
                  </div>
                </form>
              ) : (
                <Empty
                  title="A published dataset is required"
                  href={`${scope.base}/datasets`}
                  action="Publish dataset"
                />
              )
            }
          </Resource>
        </Panel>
      )}
      <Panel title="Run history">
        <Resource state={state}>
          {(page) =>
            page.items.length ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Run</th>
                      <th>Baseline → candidate</th>
                      <th>State</th>
                      <th>Decision</th>
                      <th>Created</th>
                    </tr>
                  </thead>
                  <tbody>
                    {page.items.map((run) => (
                      <tr key={run.id}>
                        <td>
                          <Link
                            className="row-link mono"
                            href={`${scope.base}/evaluations/${run.id}`}
                          >
                            {run.id.slice(0, 8)}
                          </Link>
                        </td>
                        <td>
                          {run.baseline}
                          <ArrowRight className="inline-icon" size={12} />
                          {run.candidate}
                        </td>
                        <td>
                          <Status value={run.status} />
                        </td>
                        <td>
                          <Status value={run.decision ?? "PENDING"} />
                        </td>
                        <td>{date(run.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty title="No evaluations yet">
                Pin a dataset and compare your recorded baseline and candidate
                outputs.
              </Empty>
            )
          }
        </Resource>
      </Panel>
    </>
  );
}
export function EvaluationPage({ scope, id }: { scope: Scope; id: string }) {
  const state = useResource<Evaluation>(
    `/evaluations/${encodeURIComponent(id)}?project_id=${scope.project.id}`,
    scope.refresh,
  );
  const [filter, setFilter] = useState("all");
  return (
    <>
      <Link className="back-link" href={`${scope.base}/evaluations`}>
        <ArrowLeft size={14} />
        Evaluation runs
      </Link>
      <PageHeading title="Replay comparison" description={`Run ${id}`} />
      <Resource state={state}>
        {(run) => (
          <>
            <div className="detail-status">
              <Status value={run.status} />
              <Status value={run.decision ?? "PENDING"} />
              <span>
                {run.baseline} → {run.candidate}
              </span>
            </div>
            <div className="summary-grid">
              <Panel title="Baseline correctness">
                <div className="big-number">
                  {run.results.baseline_score == null
                    ? "—"
                    : `${number(run.results.baseline_score * 100, 1)}%`}
                </div>
              </Panel>
              <Panel title="Candidate correctness">
                <div className="big-number">
                  {run.results.candidate_score == null
                    ? "—"
                    : `${number(run.results.candidate_score * 100, 1)}%`}
                </div>
              </Panel>
              <Panel title="Paired 95% interval">
                <div className="interval-number">
                  {run.results.interval_95
                    ?.map((v) => `${number(v * 100, 1)}pp`)
                    .join(" to ") ??
                    (run.status === "COMPLETED"
                      ? "Insufficient measurements"
                      : "Awaiting worker")}
                </div>
                <p className="panel-note">
                  {run.results.sample_count ?? 0} cases ·{" "}
                  {run.results.method ?? "paired-hoeffding-v1"}
                </p>
              </Panel>
            </div>
            {run.results.limitations && (
              <SafetyNotice>{run.results.limitations}</SafetyNotice>
            )}
            <Panel
              title="Case-level results"
              action={
                <label className="inline-field">
                  Show
                  <select
                    value={filter}
                    onChange={(e) => setFilter(e.target.value)}
                  >
                    <option value="all">All cases</option>
                    <option value="regressions">Regressions</option>
                    <option value="improvements">Improvements</option>
                  </select>
                </label>
              }
            >
              {run.results.cases ? (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Case</th>
                        <th>Baseline</th>
                        <th>Candidate</th>
                        <th>Change</th>
                      </tr>
                    </thead>
                    <tbody>
                      {run.results.cases
                        .filter(
                          (c) =>
                            filter === "all" ||
                            (filter === "regressions"
                              ? c.baseline_pass === true &&
                                c.candidate_pass === false
                              : c.baseline_pass === false &&
                                c.candidate_pass === true),
                        )
                        .map((c) => (
                          <tr key={c.id}>
                            <td className="mono">{c.id}</td>
                            <td>
                              <Status
                                value={
                                  c.baseline_pass == null
                                    ? "INSUFFICIENT_DATA"
                                    : c.baseline_pass
                                      ? "PASS"
                                      : "FAIL"
                                }
                              />
                            </td>
                            <td>
                              <Status
                                value={
                                  c.candidate_pass == null
                                    ? "INSUFFICIENT_DATA"
                                    : c.candidate_pass
                                      ? "PASS"
                                      : "FAIL"
                                }
                              />
                            </td>
                            <td>
                              {c.baseline_pass == null ||
                              c.candidate_pass == null
                                ? "Insufficient measurements"
                                : c.baseline_pass === c.candidate_pass
                                  ? "Unchanged"
                                  : c.candidate_pass
                                    ? "Improvement"
                                    : "Regression"}
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <Empty
                  title={
                    run.status === "FAILED"
                      ? "Evaluation failed"
                      : "Awaiting durable worker"
                  }
                >
                  Results appear only after the worker persists completed case
                  grading.
                </Empty>
              )}
            </Panel>
            <Panel title="Pinned run manifest">
              <Json value={run.manifest} />
            </Panel>
          </>
        )}
      </Resource>
    </>
  );
}
export function RemediationsPage({ scope }: { scope: Scope }) {
  const state = useResource<
    Page<Remediation> & { execution_enabled: boolean; disabled_reason: string }
  >(`/remediations?project_id=${scope.project.id}`, scope.refresh);
  const incidents = useResource<Page<Incident>>(
    `/incidents?project_id=${scope.project.id}`,
    scope.refresh,
  );
  const params = useSearchParams();
  const [show, setShow] = useState(Boolean(params.get("incident"))),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<Error>();
  async function propose(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(undefined);
    try {
      await mutation(
        `/remediations?project_id=${scope.project.id}`,
        {
          incident_id: form.get("incident_id"),
          action: form.get("action"),
          target: form.get("target"),
          rollback_plan: form.get("rollback_plan"),
          expires_minutes: Number(form.get("expires_minutes")),
        },
        "POST",
        true,
      );
      setShow(false);
      scope.reload();
      scope.notify("Proposal recorded. Execution remains disabled.");
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeading
        title="Remediation Center"
        description="Recovery proposals grounded in evidence, governed by policy."
      >
        {["admin", "operator"].includes(scope.identity.role) && (
          <button className="button primary" onClick={() => setShow(!show)}>
            <Plus size={16} />
            {show ? "Close proposal" : "Record proposal"}
          </button>
        )}
      </PageHeading>
      <SafetyNotice>
        Remote actions are OFF. Proposals can be recorded and rejected.
        Validation, approval and execution are blocked until an isolated
        executor, target preconditions, post-checks, and rollback adapter are
        available.
      </SafetyNotice>
      {error && <ErrorState error={error} />}
      {show && (
        <Panel title="Immutable recovery proposal">
          <Resource state={incidents}>
            {(page) =>
              page.items.length ? (
                <form onSubmit={propose} className="form-grid">
                  <Field label="Source incident">
                    <select
                      name="incident_id"
                      required
                      defaultValue={params.get("incident") ?? undefined}
                    >
                      {page.items.map((i) => (
                        <option key={i.id} value={i.id}>
                          {i.title}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Proposed action">
                    <select name="action">
                      <option value="restart_service">Restart service</option>
                      <option value="rollback_deployment">
                        Rollback deployment
                      </option>
                    </select>
                  </Field>
                  <Field label="Target identifier">
                    <input
                      name="target"
                      required
                      maxLength={100}
                      pattern="[a-zA-Z0-9_.:/\-]+"
                      placeholder="staging/retrieval-service"
                    />
                  </Field>
                  <Field label="Expires in (minutes)">
                    <input
                      name="expires_minutes"
                      type="number"
                      min={5}
                      max={120}
                      defaultValue={30}
                      required
                    />
                  </Field>
                  <div className="full-width">
                    <Field label="Rollback plan">
                      <textarea
                        name="rollback_plan"
                        minLength={10}
                        maxLength={500}
                        required
                        rows={3}
                        placeholder="Record the intended recovery and rollback conditions."
                      />
                    </Field>
                  </div>
                  <div className="form-actions">
                    <button
                      type="button"
                      className="button"
                      onClick={() => setShow(false)}
                    >
                      Cancel
                    </button>
                    <Submit busy={busy}>Record proposal</Submit>
                  </div>
                </form>
              ) : (
                <Empty title="An incident is required">
                  Proposals must reference an authorized incident and its
                  evidence.
                </Empty>
              )
            }
          </Resource>
        </Panel>
      )}
      <Panel title="Proposal queue">
        <Resource state={state}>
          {(page) =>
            page.items.length ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Action</th>
                      <th>Target</th>
                      <th>State</th>
                      <th>Manifest</th>
                      <th>Expires</th>
                    </tr>
                  </thead>
                  <tbody>
                    {page.items.map((p) => (
                      <tr key={p.id}>
                        <td>
                          <Link
                            className="row-link"
                            href={`${scope.base}/remediations/${p.id}`}
                          >
                            {String(p.manifest.action).replaceAll("_", " ")}
                          </Link>
                        </td>
                        <td>{String(p.manifest.target)}</td>
                        <td>
                          <Status value={p.state} />
                        </td>
                        <td className="mono">
                          {p.manifest_hash.slice(0, 12)}…
                        </td>
                        <td>{date(p.expires_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty title="No recovery proposals">
                Start with an incident, inspect its evidence, and record a
                scoped recovery proposal.
              </Empty>
            )
          }
        </Resource>
      </Panel>
    </>
  );
}
export function RemediationPage({ scope, id }: { scope: Scope; id: string }) {
  const state = useResource<Remediation & { disabled_reason: string }>(
    `/remediations/${encodeURIComponent(id)}?project_id=${scope.project.id}`,
    scope.refresh,
  );
  const [confirm, setConfirm] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<Error>();
  async function reject() {
    setBusy(true);
    try {
      await mutation(
        `/remediations/${id}/reject?project_id=${scope.project.id}`,
      );
      setConfirm(false);
      scope.reload();
      scope.notify("Proposal rejected. No target action was executed.");
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Link className="back-link" href={`${scope.base}/remediations`}>
        <ArrowLeft size={14} />
        Remediation Center
      </Link>
      <PageHeading
        title="Recovery proposal"
        description={`Manifest-bound proposal ${id.slice(0, 8)}`}
      />
      <Resource state={state}>
        {(p) => (
          <>
            <div className="detail-status">
              <Status value={p.state} />
              <span>Expires {date(p.expires_at)}</span>
            </div>
            <SafetyNotice>{p.disabled_reason}</SafetyNotice>
            {error && <ErrorState error={error} />}
            <Panel
              title="Action manifest"
              description="Exact SHA-256 hash; modifying any field requires a new proposal."
            >
              <div className="manifest-hash mono">{p.manifest_hash}</div>
              <Json value={p.manifest} />
            </Panel>
            <Panel title="Policy & authorization">
              <dl className="definition-list">
                <dt>Validation</dt>
                <dd>BLOCKED — target adapter unavailable</dd>
                <dt>Approval</dt>
                <dd>
                  Independent authorized identity; exact hash; valid TTL;
                  successful validation required
                </dd>
                <dt>Execution</dt>
                <dd>Disabled server-side for all identities</dd>
                <dt>Post-check / rollback</dt>
                <dd>Unavailable; proposal cannot become VERIFIED</dd>
              </dl>
              <div className="panel-actions">
                <button
                  className="button"
                  disabled
                  title="An isolated executor must validate the target first."
                >
                  Approve — blocked
                </button>
                <button
                  className="button"
                  disabled
                  title="Remote executor is not configured."
                >
                  Execute — disabled
                </button>
                {p.state !== "REJECTED" &&
                  ["admin", "operator", "approver"].includes(
                    scope.identity.role,
                  ) && (
                    <button
                      className="button danger"
                      onClick={() => setConfirm(true)}
                    >
                      Reject proposal
                    </button>
                  )}
              </div>
              {confirm && (
                <div
                  className="confirm-inline"
                  role="group"
                  aria-label="Confirm proposal rejection"
                >
                  <p>
                    Reject proposal {p.id.slice(0, 8)}? It will no longer be
                    eligible for approval.
                  </p>
                  <button
                    className="button"
                    autoFocus
                    onClick={() => setConfirm(false)}
                  >
                    Cancel
                  </button>
                  <button
                    className="button danger"
                    disabled={busy}
                    onClick={reject}
                  >
                    Confirm rejection
                  </button>
                </div>
              )}
            </Panel>
          </>
        )}
      </Resource>
    </>
  );
}
