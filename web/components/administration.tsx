"use client";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import {
  ArrowRight,
  Check,
  Copy,
  KeyRound,
  Plus,
  RefreshCw,
} from "lucide-react";
import { date, mutation, useResource } from "@/lib/api";
import type { Audit, Credential, Identity, Page, Services } from "@/lib/types";
import type { Scope } from "./console";
import {
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

export function ProjectsPage({
  identity,
  reload,
  scope,
}: {
  identity: Identity;
  reload: () => void;
  scope?: Scope;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<Error>(),
    [show, setShow] = useState(!scope);
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(undefined);
    try {
      await mutation("/projects", {
        name: form.get("name"),
        slug: form.get("slug"),
        environment: form.get("environment"),
      });
      reload();
      setShow(false);
      scope?.notify("Project created. Select it from the project menu.");
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      {scope && (
        <>
          <Setup scope={scope} />
          {identity.role === "admin" && (
            <button className="button" onClick={() => setShow(!show)}>
              <Plus size={15} />
              {show ? "Close project form" : "Create another project"}
            </button>
          )}
        </>
      )}
      {error && <ErrorState error={error} />}
      {show &&
        (identity.role === "admin" ? (
          <form onSubmit={create} className="form-grid standalone-form">
            <Field label="Project name">
              <input
                name="name"
                required
                minLength={2}
                maxLength={80}
                placeholder="AI support assistant"
              />
            </Field>
            <Field
              label="Project slug"
              hint="Lowercase letters, digits, and hyphens."
            >
              <input
                name="slug"
                required
                minLength={2}
                maxLength={64}
                pattern="[a-z0-9]+(?:-[a-z0-9]+)*"
                placeholder="support-assistant"
              />
            </Field>
            <Field label="Environment">
              <select name="environment">
                <option value="development">Development</option>
                <option value="staging">Staging</option>
                <option value="production">Production</option>
              </select>
            </Field>
            <div className="form-actions">
              <Submit busy={busy}>Create project</Submit>
            </div>
          </form>
        ) : (
          <SafetyNotice>
            Only an administrator can create projects. Ask your administrator to
            grant project access.
          </SafetyNotice>
        ))}
    </>
  );
}
function Setup({ scope }: { scope: Scope }) {
  const state = useResource<Services>(
    `/services?project_id=${scope.project.id}&hours=168`,
    scope.refresh,
  );
  const [copied, setCopied] = useState(false),
    [copyError, setCopyError] = useState<Error>();
  const snippet = `# Keep your ingestion secret in your workload secret store.\n# The API stores only its SHA-256 verifier. Never put it in browser code.\nexport OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4318"\nexport OTEL_EXPORTER_OTLP_PROTOCOL="http/protobuf"\nexport OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer \${NEURALOPS_INGESTION_KEY}"\nexport OTEL_SERVICE_NAME="${scope.project.slug}"\n# Configure your OTel SDK to exclude prompts, bodies and headers.\n# Hosted deployments must use an HTTPS collector endpoint.`;
  async function copy() {
    try {
      await navigator.clipboard.writeText(snippet);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 3000);
    } catch {
      setCopyError(
        new Error(
          "Clipboard unavailable. Select and copy the snippet manually.",
        ),
      );
    }
  }
  return (
    <>
      <div className="setup-steps">
        <span className="active">01 Project scope</span>
        <ArrowRight size={14} />
        <span>02 Scoped credential</span>
        <ArrowRight size={14} />
        <span>03 Instrument & verify</span>
      </div>
      <div className="summary-grid">
        <Panel title="Project">
          <div className="panel-body">
            <strong>{scope.project.name}</strong>
            <p className="mono break-all">{scope.project.id}</p>
          </div>
        </Panel>
        <Panel title="Collection policy">
          <div className="panel-body">
            <strong>Metadata only</strong>
            <p>Prompts, outputs, documents, and headers are discarded.</p>
          </div>
        </Panel>
        <Panel title="Connection state">
          <Resource state={state}>
            {(data) => (
              <div className="panel-body">
                <Status value={data.items.length ? "observed" : "unknown"} />
                <p>
                  {data.items.length
                    ? `${data.items.length} services sent spans in the last 7 days. This is not a live health probe.`
                    : "No spans received in the last 7 days."}
                </p>
              </div>
            )}
          </Resource>
        </Panel>
      </div>
      <Panel
        title="1. Create a scoped ingestion credential"
        description="Credentials are bound to this project and its environment."
      >
        <div className="panel-body">
          {scope.identity.role === "admin" ? (
            <Link className="button primary" href={`${scope.base}/keys`}>
              <KeyRound size={15} />
              Manage ingestion credentials
              <ArrowRight size={14} />
            </Link>
          ) : (
            <p>An administrator must issue your workload credential.</p>
          )}
        </div>
      </Panel>
      <Panel
        title="2. Configure your OpenTelemetry SDK"
        description="The gateway accepts OTLP/HTTP JSON and binary protobuf at /v1/traces."
        action={
          <button className="button small" onClick={copy}>
            {copied ? <Check size={14} /> : <Copy size={14} />}
            {copied ? "Copied" : "Copy configuration"}
          </button>
        }
      >
        <pre className="code-snippet">{snippet}</pre>
        {copyError && <ErrorState error={copyError} />}
      </Panel>
      <Panel
        title="3. Send telemetry and verify receipt"
        description="A connection is observed only after the backend persists actual spans."
      >
        <div className="panel-body">
          <p>
            Use your instrumented application, or run the explicit synthetic
            fixture sender in <code>examples/send_trace.py</code> with a project
            credential. Fixture operations are named{" "}
            <code>synthetic-fixture</code> so they remain identifiable.
          </p>
          <div className="panel-actions">
            <button className="button" onClick={scope.reload}>
              <RefreshCw size={15} />
              Check received spans
            </button>
            <Link className="button" href={`${scope.base}/traces`}>
              Inspect traces
              <ArrowRight size={14} />
            </Link>
          </div>
        </div>
      </Panel>
    </>
  );
}
export function KeysPage({ scope }: { scope: Scope }) {
  const state = useResource<Page<Credential>>(
    `/credentials?project_id=${scope.project.id}`,
    scope.refresh,
  );
  const [secret, setSecret] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<Error>(),
    [revoke, setRevoke] = useState<Credential>();
  async function issue() {
    setBusy(true);
    setError(undefined);
    try {
      const result = await mutation<Credential & { secret: string }>(
        `/credentials?project_id=${scope.project.id}`,
      );
      setSecret(result.secret);
      scope.reload();
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    if (!revoke) return;
    setBusy(true);
    try {
      await mutation(
        `/credentials/${revoke.id}?project_id=${scope.project.id}`,
        undefined,
        "DELETE",
      );
      setRevoke(undefined);
      setSecret("");
      scope.reload();
      scope.notify(
        "Credential revoked. Further ingestion with this credential is rejected.",
      );
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeading
        title="Scoped API Keys"
        description="Issue once, store securely, revoke immediately. Ingestion only; no control API access."
      >
        {scope.identity.role === "admin" && (
          <button
            className="button primary"
            disabled={busy || Boolean(secret)}
            onClick={issue}
          >
            <Plus size={15} />
            Issue ingestion credential
          </button>
        )}
      </PageHeading>
      {error && <ErrorState error={error} />}
      {secret && (
        <Panel
          title="Save your credential now"
          description="This secret is shown once. It cannot be recovered after you dismiss this panel."
        >
          <div className="secret-panel">
            <SafetyNotice>
              Store in your workload secret manager. Do not share, screenshot,
              or put this secret in frontend code.
            </SafetyNotice>
            <label className="field">
              <span>One-time ingestion secret</span>
              <input
                className="mono"
                value={secret}
                readOnly
                autoComplete="off"
                spellCheck={false}
                onFocus={(e) => e.currentTarget.select()}
              />
            </label>
            <button className="button" onClick={() => setSecret("")}>
              I saved it securely · dismiss
            </button>
          </div>
        </Panel>
      )}
      <Panel
        title="Project ingestion credentials"
        description="30-day expiry · metadata-only scopes · at most 10 active credentials"
      >
        <Resource state={state}>
          {(page) =>
            page.items.length ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Identifier / prefix</th>
                      <th>State</th>
                      <th>Expires</th>
                      <th>Created</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {page.items.map((c) => (
                      <tr key={c.id}>
                        <td className="mono">
                          {c.prefix}…<small>{c.id}</small>
                        </td>
                        <td>
                          <Status
                            value={
                              c.revoked
                                ? "REVOKED"
                                : new Date(c.expires_at) < new Date()
                                  ? "EXPIRED"
                                  : "ACTIVE"
                            }
                          />
                        </td>
                        <td>{date(c.expires_at)}</td>
                        <td>{date(c.created_at)}</td>
                        <td>
                          {!c.revoked && scope.identity.role === "admin" && (
                            <button
                              className="button danger small"
                              onClick={() => setRevoke(c)}
                            >
                              Revoke
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty title="No ingestion credentials">
                Issue a project-scoped credential to authenticate your
                OpenTelemetry workload.
              </Empty>
            )
          }
        </Resource>
      </Panel>
      {revoke && (
        <div
          className="confirm-inline"
          role="group"
          aria-label="Confirm credential revocation"
        >
          <h3>Revoke {revoke.prefix}…?</h3>
          <p>
            Workloads using this credential will no longer be able to send
            telemetry.
          </p>
          <button
            className="button"
            autoFocus
            onClick={() => setRevoke(undefined)}
          >
            Cancel
          </button>
          <button className="button danger" disabled={busy} onClick={remove}>
            Confirm revocation
          </button>
        </div>
      )}
    </>
  );
}
export function AuditPage({ scope }: { scope: Scope }) {
  const [cursor, setCursor] = useState(""),
    [filter, setFilter] = useState("");
  const state = useResource<Page<Audit>>(
    `/audit?project_id=${scope.project.id}&limit=50${cursor ? `&cursor=${cursor}` : ""}`,
    scope.refresh,
  );
  return (
    <>
      <PageHeading
        title="Audit Log"
        description="Append-only records of sensitive workspace changes and their actors."
      />
      <Panel
        title="Workspace activity"
        action={
          <label className="inline-field">
            Filter this page
            <input
              aria-label="Filter audit actions"
              value={filter}
              maxLength={100}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Action or actor"
            />
          </label>
        }
      >
        <Resource state={state}>
          {(page) => (
            <>
              {page.items.length ? (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Time</th>
                        <th>Action</th>
                        <th>Actor</th>
                        <th>Target</th>
                        <th>Outcome</th>
                        <th>Request</th>
                      </tr>
                    </thead>
                    <tbody>
                      {page.items
                        .filter((e) =>
                          `${e.action} ${e.actor}`
                            .toLowerCase()
                            .includes(filter.toLowerCase()),
                        )
                        .map((e) => (
                          <tr key={e.id}>
                            <td className="nowrap">{date(e.created_at)}</td>
                            <td>{e.action}</td>
                            <td>{e.actor}</td>
                            <td className="mono">{e.target.slice(0, 16)}…</td>
                            <td>
                              <Status value={e.outcome} />
                            </td>
                            <td className="mono">
                              {e.request_id
                                ? e.request_id.slice(0, 8)
                                : "worker"}
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <Empty title="No audit records" />
              )}
              <div className="pagination">
                <span>Stable ID order · 50 records per page</span>
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
          )}
        </Resource>
      </Panel>
    </>
  );
}

export function SettingsPage({ scope }: { scope: Scope }) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<Error>();
  const [days, setDays] = useState(scope.project.retention_days);
  const [savedDays, setSavedDays] = useState(scope.project.retention_days);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      days < savedDays &&
      !window.confirm(
        `Reduce retention for ${scope.project.name} from ${savedDays} to ${days} days? Older telemetry will be permanently deleted by the worker.`,
      )
    )
      return;
    setBusy(true);
    setError(undefined);
    try {
      await mutation(
        `/projects/${scope.project.id}`,
        { retention_days: days },
        "PATCH",
      );
      setSavedDays(days);
      scope.notify(
        "Retention policy saved. The worker deletes expired traces in bounded batches.",
      );
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeading
        title="Workspace settings"
        description="Identity, isolation, and collection policy for this deployment."
      />
      {error && <ErrorState error={error} />}
      <Panel title="Security posture">
        <dl className="definition-list">
          <dt>Identity</dt>
          <dd>
            {scope.identity.name} · {scope.identity.role}
          </dd>
          <dt>Authentication</dt>
          <dd>
            {scope.identity.development
              ? "Explicit isolated development mode"
              : "OIDC managed session"}
          </dd>
          <dt>Collection</dt>
          <dd>Metadata allowlist only; bodies and headers discarded</dd>
          <dt>Hot-store quota</dt>
          <dd>100,000 spans per project · 2,000 spans per trace</dd>
          <dt>Remote execution</dt>
          <dd>Disabled — isolated executor required</dd>
          <dt>Membership changes</dt>
          <dd>
            Deployment administrator CLI; audited, no self-service escalation
          </dd>
        </dl>
      </Panel>
      <Panel
        title="Telemetry retention"
        description="Expired trace IDs remain as evidence-expired references; raw spans are deleted."
      >
        {scope.identity.role === "admin" ? (
          <form className="form-grid" onSubmit={save}>
            <Field
              label="Retain telemetry (days)"
              hint="1–30 days. The worker drains up to 1,000 expired traces per project each minute. Shortening retention permanently removes older telemetry."
            >
              <input
                type="number"
                min={1}
                max={30}
                required
                value={days}
                onChange={(e) => setDays(Number(e.target.value))}
              />
            </Field>
            <div className="form-actions">
              <Submit busy={busy}>Save retention policy</Submit>
            </div>
          </form>
        ) : (
          <div className="panel-body">
            Current policy: {days} days. An administrator can change this
            policy.
          </div>
        )}
      </Panel>
    </>
  );
}
