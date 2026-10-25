"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { BrainCircuit, ArrowRight, ShieldCheck } from "lucide-react";
import { mutation, useResource } from "@/lib/api";
import { ErrorState, Resource } from "@/components/primitives";
export default function Login() {
  const router = useRouter();
  const config = useResource<{
    development_auth: boolean;
    oidc_enabled: boolean;
  }>("/auth/config");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<Error>();
  async function enter() {
    setBusy(true);
    try {
      await mutation("/auth/development");
      router.replace("/app/local/select/overview");
    } catch (e) {
      setError(e as Error);
      setBusy(false);
    }
  }
  return (
    <main className="login-page">
      <div className="login-card">
        <div className="brand">
          <BrainCircuit size={32} />
          <span>
            Neural<span className="blue-text">Ops</span>
          </span>
        </div>
        <span className="eyebrow">THE CONTROL PLANE FOR RELIABLE AI</span>
        <h1>
          Clarity for every
          <br />
          AI execution.
        </h1>
        <p>
          Connect your telemetry. Investigate with evidence.
          <br />
          Make every change accountable.
        </p>
        <Resource state={config}>
          {(data) => (
            <div className="login-actions">
              {data.oidc_enabled && (
                // eslint-disable-next-line @next/next/no-html-link-for-pages -- OIDC requires full HTTP navigation.
                <a className="button primary" href="/api/v1/auth/login">
                  Sign in with your organization
                  <ArrowRight size={16} />
                </a>
              )}
              {data.development_auth && (
                <>
                  <div className="notice">
                    <ShieldCheck size={20} />
                    <p>
                      Isolated development workspace. Local admin access is
                      explicitly enabled; production sign-in uses OIDC.
                    </p>
                  </div>
                  <button
                    className="button primary"
                    disabled={busy}
                    onClick={enter}
                  >
                    {busy ? "Signing in…" : "Enter local workspace"}
                    <ArrowRight size={16} />
                  </button>
                </>
              )}
              {!data.development_auth && !data.oidc_enabled && (
                <p>
                  Identity provider unavailable. Configure OIDC to enable
                  sign-in.
                </p>
              )}
            </div>
          )}
        </Resource>
        {error && <ErrorState error={error} />}
        <div className="login-footer">
          Metadata first. Evidence always. Actions under control.
        </div>
      </div>
    </main>
  );
}
