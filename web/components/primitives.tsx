"use client";
import Link from "next/link";
import {
  Activity,
  AlertCircle,
  ArrowRight,
  Database,
  LoaderCircle,
  ShieldCheck,
} from "lucide-react";
import type { ReactNode } from "react";
import { ApiError } from "@/lib/api";

export function Badge({
  children,
  tone = "",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return (
    <span className={`badge ${tone}`}>
      <span aria-hidden="true" className="badge-dot" />
      {children}
    </span>
  );
}
export function Status({ value }: { value: string }) {
  const tone = ["ok", "observed", "COMPLETED", "PASS", "RESOLVED"].includes(
    value,
  )
    ? "success"
    : ["error", "critical", "FAIL", "FAILED"].includes(value)
      ? "critical"
      : ["OPEN", "high", "firing", "degraded"].includes(value)
        ? "warning"
        : "neutral";
  return <Badge tone={tone}>{value.replaceAll("_", " ")}</Badge>;
}
export function Panel({
  title,
  description,
  action,
  children,
  className = "",
}: {
  title?: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      {title && (
        <div className="panel-header">
          <div>
            <h2>{title}</h2>
            {description && <p>{description}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}
export function Empty({
  title = "No data yet",
  children,
  href,
  action,
}: {
  title?: string;
  children?: ReactNode;
  href?: string;
  action?: string;
}) {
  return (
    <div className="empty">
      <span className="empty-icon">
        <Database size={22} />
      </span>
      <h3>{title}</h3>
      <p>
        {children ??
          "Data will appear here after your application sends telemetry."}
      </p>
      {href && (
        <Link className="button small" href={href}>
          {action ?? "Set up instrumentation"}
          <ArrowRight size={14} />
        </Link>
      )}
    </div>
  );
}
export function Loading() {
  return (
    <div role="status" className="loading">
      <LoaderCircle size={19} className="spin" />
      Loading measured data…
    </div>
  );
}
export function ErrorState({
  error,
  retry,
}: {
  error: Error;
  retry?: () => void;
}) {
  return (
    <div role="alert" className="error-state">
      <AlertCircle size={20} />
      <div>
        <strong>{error.message}</strong>
        {error instanceof ApiError && error.requestId && (
          <p>Request {error.requestId}</p>
        )}
        {retry && (
          <button onClick={retry} className="button small">
            Retry
          </button>
        )}
      </div>
    </div>
  );
}
export function Resource<T>({
  state,
  children,
}: {
  state: { loading: boolean; error?: Error; data?: T };
  children: (data: T) => ReactNode;
}) {
  if (state.loading) return <Loading />;
  if (state.error && state.data === undefined)
    return <ErrorState error={state.error} />;
  return state.data === undefined ? null : (
    <>
      {state.error && (
        <div className="stale-banner" role="status">
          Refresh failed — displayed data is stale. {state.error.message}
        </div>
      )}
      {children(state.data)}
    </>
  );
}
export function SafetyNotice({ children }: { children: ReactNode }) {
  return (
    <div className="notice">
      <ShieldCheck size={18} />
      <p>{children}</p>
    </div>
  );
}
export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}
export function Submit({
  busy,
  children,
}: {
  busy: boolean;
  children: ReactNode;
}) {
  return (
    <button type="submit" disabled={busy} className="button primary">
      {busy ? (
        <LoaderCircle className="spin" size={16} />
      ) : (
        <Activity size={16} />
      )}
      {children}
    </button>
  );
}
export function Json({ value }: { value: unknown }) {
  return <pre className="json">{JSON.stringify(value, null, 2)}</pre>;
}
export function PageHeading({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">AI RELIABILITY ENGINEERING</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <div className="heading-actions">{children}</div>
    </div>
  );
}
