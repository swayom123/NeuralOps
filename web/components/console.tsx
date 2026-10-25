"use client";
import Link from "next/link";
import dynamic from "next/dynamic";
import {
  useParams,
  usePathname,
  useRouter,
  useSearchParams,
} from "next/navigation";
import { useEffect, useState } from "react";
import {
  Activity,
  ArrowUpRight,
  Boxes,
  BrainCircuit,
  ChartNoAxesCombined,
  ChevronRight,
  ClipboardCheck,
  Clock3,
  Code2,
  Database,
  FileClock,
  FlaskConical,
  GitBranch,
  KeyRound,
  Layers3,
  LayoutDashboard,
  LogOut,
  Menu,
  Network,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  ShieldEllipsis,
  SlidersHorizontal,
  Terminal,
  Workflow,
  X,
  type LucideIcon,
} from "lucide-react";
import { mutation, useResource } from "@/lib/api";
import type { Identity, Page, Project } from "@/lib/types";
import {
  Badge,
  ErrorState,
  Loading,
  PageHeading,
  Panel,
  SafetyNotice,
} from "./primitives";
const Overview = dynamic(() => import("./overview").then((m) => m.Overview), {
  loading: Loading,
});
const TracePage = dynamic(
  () => import("./observability").then((m) => m.TracePage),
  { loading: Loading },
);
const TraceDetailPage = dynamic(
  () => import("./observability").then((m) => m.TraceDetailPage),
  { loading: Loading },
);
const ServicesPage = dynamic(
  () => import("./observability").then((m) => m.ServicesPage),
  { loading: Loading },
);
const AnalyticsPage = dynamic(
  () => import("./observability").then((m) => m.AnalyticsPage),
  { loading: Loading },
);
const RulesPage = dynamic(
  () => import("./reliability").then((m) => m.RulesPage),
  { loading: Loading },
);
const IncidentsPage = dynamic(
  () => import("./reliability").then((m) => m.IncidentsPage),
  { loading: Loading },
);
const IncidentPage = dynamic(
  () => import("./reliability").then((m) => m.IncidentPage),
  { loading: Loading },
);
const SLOsPage = dynamic(
  () => import("./reliability").then((m) => m.SLOsPage),
  { loading: Loading },
);
const DatasetsPage = dynamic(
  () => import("./workflows").then((m) => m.DatasetsPage),
  { loading: Loading },
);
const EvaluationsPage = dynamic(
  () => import("./workflows").then((m) => m.EvaluationsPage),
  { loading: Loading },
);
const EvaluationPage = dynamic(
  () => import("./workflows").then((m) => m.EvaluationPage),
  { loading: Loading },
);
const RemediationsPage = dynamic(
  () => import("./workflows").then((m) => m.RemediationsPage),
  { loading: Loading },
);
const RemediationPage = dynamic(
  () => import("./workflows").then((m) => m.RemediationPage),
  { loading: Loading },
);
const ProjectsPage = dynamic(
  () => import("./administration").then((m) => m.ProjectsPage),
  { loading: Loading },
);
const KeysPage = dynamic(
  () => import("./administration").then((m) => m.KeysPage),
  { loading: Loading },
);
const AuditPage = dynamic(
  () => import("./administration").then((m) => m.AuditPage),
  { loading: Loading },
);
const SettingsPage = dynamic(
  () => import("./administration").then((m) => m.SettingsPage),
  { loading: Loading },
);

const groups: { title: string; items: [string, string, LucideIcon][] }[] = [
  {
    title: "OVERVIEW",
    items: [
      ["overview", "Command Center", LayoutDashboard],
      ["health", "System Health", Activity],
      ["service-map", "Service Map", Network],
    ],
  },
  {
    title: "OBSERVABILITY",
    items: [
      ["traces", "Trace Explorer", Workflow],
      ["models", "Model Performance", BrainCircuit],
      ["tools", "Tool Analytics", Boxes],
      ["usage", "Token & Cost", ChartNoAxesCombined],
    ],
  },
  {
    title: "RELIABILITY",
    items: [
      ["rules", "Detection Rules", SlidersHorizontal],
      ["slos", "SLO Management", ShieldCheck],
      ["incidents", "Incidents", ShieldEllipsis],
    ],
  },
  {
    title: "EVALUATION",
    items: [
      ["evaluations", "Evaluation Runs", FlaskConical],
      ["datasets", "Datasets", Database],
    ],
  },
  {
    title: "REMEDIATION",
    items: [["remediations", "Remediation Center", ShieldCheck]],
  },
  {
    title: "ADMINISTRATION",
    items: [
      ["projects", "Integrations", Code2],
      ["keys", "API Keys", KeyRound],
      ["audit", "Audit Log", FileClock],
      ["settings", "Settings", Settings2],
    ],
  },
];
export type Scope = {
  project: Project;
  identity: Identity;
  base: string;
  hours: number;
  refresh: number;
  notify: (message: string) => void;
  reload: () => void;
};

export function Console() {
  const me = useResource<Identity>("/me");
  if (me.loading)
    return (
      <main className="loading-page">
        <Loading />
      </main>
    );
  if (me.error)
    return (
      <main className="loading-page">
        <ErrorState error={me.error} />
        <Link href="/login" className="button">
          Sign in
        </Link>
      </main>
    );
  return me.data ? <Authenticated identity={me.data} /> : null;
}
function Authenticated({ identity }: { identity: Identity }) {
  const params = useParams<{ org: string; project: string }>();
  const [revision, setRevision] = useState(0);
  const projects = useResource<Page<Project>>("/projects", revision);
  const router = useRouter();
  const selected = projects.data?.items.find((p) => p.slug === params.project);
  useEffect(() => {
    if (
      projects.data &&
      (!selected || params.org !== identity.organization.slug) &&
      projects.data.items.length
    ) {
      router.replace(
        `/app/${identity.organization.slug}/${projects.data.items[0].slug}/overview`,
      );
    }
  }, [projects.data, selected, params.org, identity.organization.slug, router]);
  if (projects.error)
    return (
      <main className="loading-page">
        <ErrorState
          error={projects.error}
          retry={() => setRevision((v) => v + 1)}
        />
      </main>
    );
  if (projects.loading || !projects.data)
    return (
      <main className="loading-page">
        <Loading />
      </main>
    );
  if (!projects.data.items.length)
    return (
      <Onboarding
        identity={identity}
        reload={() => setRevision((v) => v + 1)}
      />
    );
  if (!selected) return <Loading />;
  return (
    <Workspace
      key={selected.id}
      identity={identity}
      project={selected}
      projects={projects.data.items}
      projectsReload={() => setRevision((v) => v + 1)}
    />
  );
}
function Onboarding({
  identity,
  reload,
}: {
  identity: Identity;
  reload: () => void;
}) {
  return (
    <main className="onboarding">
      <div className="brand">
        <BrainCircuit />
        <span>
          Neural<span className="blue-text">Ops</span>
        </span>
      </div>
      <PageHeading
        title="Your reliability workspace starts here."
        description="Connect an AI application to turn telemetry into operational evidence."
      />
      <div className="onboarding-grid">
        <Panel
          title="01 / Create your first project"
          description="Each project has isolated telemetry and ingestion credentials."
        >
          <ProjectsPage identity={identity} reload={reload} />
        </Panel>
        <div className="onboarding-guide">
          <span className="feature-icon">
            <Network />
          </span>
          <h2>Observe → Investigate → Improve</h2>
          <p>
            Send OpenTelemetry spans to the authenticated gateway. Track
            execution health, surface incidents, and compare changes using
            evidence.
          </p>
          <SafetyNotice>
            No sample telemetry is seeded. Your workspace shows only the data
            you send.
          </SafetyNotice>
          <div className="guide-step">
            <ShieldCheck size={18} />
            Metadata-only collection by default
          </div>
          <div className="guide-step">
            <GitBranch size={18} />
            Trace and incident evidence stay linked
          </div>
          <div className="guide-step">
            <ClipboardCheck size={18} />
            Remote actions are disabled
          </div>
        </div>
      </div>
    </main>
  );
}
function Workspace({
  identity,
  project,
  projects,
  projectsReload,
}: {
  identity: Identity;
  project: Project;
  projects: Project[];
  projectsReload: () => void;
}) {
  const pathname = usePathname(),
    searchParams = useSearchParams(),
    router = useRouter();
  const base = `/app/${identity.organization.slug}/${project.slug}`;
  const view = pathname
    .slice(base.length + 1)
    .split("/")
    .filter(Boolean);
  const section = view[0] ?? "overview";
  const [mobile, setMobile] = useState(false),
    [refresh, setRefresh] = useState(0),
    [toast, setToast] = useState("");
  const rawHours = Number(searchParams.get("hours") ?? 24);
  const hours = [1, 6, 24, 168].includes(rawHours) ? rawHours : 24;
  const scope: Scope = {
    project,
    identity,
    base,
    hours,
    refresh,
    notify: setToast,
    reload: () => setRefresh((v) => v + 1),
  };
  useEffect(() => {
    const interval = window.setInterval(() => {
      if (!document.hidden) setRefresh((v) => v + 1);
    }, 30000);
    return () => window.clearInterval(interval);
  }, []);
  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(""), 6000);
    return () => window.clearTimeout(timer);
  }, [toast]);
  useEffect(() => {
    if (!mobile) return;
    const opener = document.activeElement as HTMLElement | null;
    const sidebar = document.querySelector<HTMLElement>(".sidebar");
    const focusable = () =>
      sidebar?.querySelectorAll<HTMLElement>(
        "a[href], button:not([disabled])",
      ) ?? [];
    focusable()[0]?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMobile(false);
        return;
      }
      if (e.key === "Tab") {
        const items = focusable(),
          first = items[0],
          last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", handler);
    return () => {
      document.removeEventListener("keydown", handler);
      document.body.style.overflow = previousOverflow;
      opener?.focus();
    };
  }, [mobile]);
  const title =
    groups.flatMap((g) => g.items).find((i) => i[0] === section)?.[1] ??
    "Workspace";
  async function logout() {
    try {
      await mutation("/auth/logout");
      router.replace("/login");
    } catch (e) {
      setToast((e as Error).message);
    }
  }
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      {mobile && (
        <button
          className="sidebar-backdrop"
          aria-label="Close navigation"
          onClick={() => setMobile(false)}
        />
      )}
      <aside
        className={`sidebar ${mobile ? "open" : ""}`}
        aria-label="Workspace navigation"
      >
        <Link className="brand" href={`${base}/overview`}>
          <span className="brand-icon">
            <BrainCircuit size={24} />
          </span>
          <span>
            Neural<span className="blue-text">Ops</span>
          </span>
          <span className="version-tag">BETA</span>
        </Link>
        <div className="workspace-name">
          <span className="workspace-avatar">
            {identity.organization.name[0]}
          </span>
          <span>
            <strong>{identity.organization.name}</strong>
            <small>
              {identity.development
                ? "Isolated development"
                : "Organization workspace"}
            </small>
          </span>
          <Layers3 size={15} />
        </div>
        <nav>
          {groups.map((group) => (
            <div className="nav-group" key={group.title}>
              <div className="nav-label">{group.title}</div>
              {group.items
                .filter(
                  (item) => item[0] !== "keys" || identity.role === "admin",
                )
                .filter(
                  (item) =>
                    item[0] !== "audit" ||
                    ["admin", "operator", "approver"].includes(identity.role),
                )
                .map(([route, label, Icon]) => (
                  <Link
                    key={route}
                    className={`nav-item ${section === route ? "active" : ""}`}
                    href={`${base}/${route}`}
                    aria-current={section === route ? "page" : undefined}
                    onClick={() => setMobile(false)}
                  >
                    <Icon size={17} />
                    <span>{label}</span>
                    {section === route && <span className="nav-active-dot" />}
                  </Link>
                ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <Link href={`${base}/projects`} className="instrumentation-link">
            <Terminal size={17} />
            <span>Connect your application</span>
            <ArrowUpRight size={14} />
          </Link>
          <div className="user-row">
            <span className="user-avatar">
              {identity.name
                .split(" ")
                .map((n) => n[0])
                .join("")
                .slice(0, 2)}
            </span>
            <span>
              <strong>{identity.name}</strong>
              <small>{identity.role}</small>
            </span>
            <button
              className="icon-button"
              aria-label="Sign out"
              onClick={logout}
            >
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell" inert={mobile}>
        <header className="topbar">
          <button
            className="icon-button mobile-menu"
            aria-label="Open navigation"
            aria-expanded={mobile}
            onClick={() => setMobile(!mobile)}
          >
            {mobile ? <X size={20} /> : <Menu size={20} />}
          </button>
          <div className="breadcrumbs">
            <span>{project.name}</span>
            <ChevronRight size={14} />
            <strong>{title}</strong>
          </div>
          <div className="topbar-right">
            <GlobalSearch base={base} />
            <span className="topbar-divider" />
            <span className="connection-label">
              <ShieldCheck size={15} />
              {identity.development ? "Local workspace" : "Authenticated"}
            </span>
          </div>
        </header>
        <main id="main" className="content" tabIndex={-1}>
          <div className="context-bar">
            <div className="context-left">
              <span className="project-symbol">
                <Layers3 size={15} />
              </span>
              <label className="sr-only" htmlFor="project">
                Project
              </label>
              <select
                id="project"
                value={project.slug}
                onChange={(e) =>
                  router.push(
                    `/app/${identity.organization.slug}/${e.target.value}/overview`,
                  )
                }
              >
                {projects.map((p) => (
                  <option key={p.id} value={p.slug}>
                    {p.name}
                  </option>
                ))}
              </select>
              <span className="context-slash">/</span>
              <Badge tone="neutral">{project.environment}</Badge>
            </div>
            <div className="context-right">
              <Clock3 size={14} />
              <label className="sr-only" htmlFor="time-range">
                Time range
              </label>
              <select
                id="time-range"
                value={hours}
                onChange={(e) => {
                  const next = new URLSearchParams(searchParams);
                  next.set("hours", e.target.value);
                  router.push(`${pathname}?${next}`);
                }}
              >
                <option value={1}>Last hour</option>
                <option value={6}>Last 6 hours</option>
                <option value={24}>Last 24 hours</option>
                <option value={168}>Last 7 days</option>
              </select>
              <button
                className="icon-button"
                aria-label="Refresh data"
                onClick={scope.reload}
              >
                <RefreshCw size={15} />
              </button>
            </div>
          </div>
          <>
            {project.slug.startsWith("synthetic-fixture") && (
              <div className="demo-banner">
                <strong>DEMO</strong>
                <span>
                  Synthetic fixture project · Measurements come from explicitly
                  generated test traffic.
                </span>
              </div>
            )}
          </>
          <WorkspaceView
            section={section}
            id={view[1]}
            subview={view[2]}
            scope={scope}
            projectsReload={projectsReload}
          />
          <footer className="page-footer">
            <span>
              <ShieldCheck size={13} />
              Metadata-only telemetry · Remote actions disabled
            </span>
            <span>NeuralOps / v0.1</span>
          </footer>
        </main>
      </div>
      {toast && (
        <div className="toast" role="status">
          {toast}
          <button
            className="icon-button"
            aria-label="Dismiss notification"
            onClick={() => setToast("")}
          >
            <X size={14} />
          </button>
        </div>
      )}
    </div>
  );
}
function WorkspaceView({
  section,
  id,
  subview,
  scope,
  projectsReload,
}: {
  section: string;
  id?: string;
  subview?: string;
  scope: Scope;
  projectsReload: () => void;
}) {
  switch (section) {
    case "overview":
      return <Overview scope={scope} />;
    case "traces":
      return id ? (
        <TraceDetailPage scope={scope} id={id} />
      ) : (
        <TracePage scope={scope} />
      );
    case "service-map":
    case "health":
      return <ServicesPage scope={scope} graph={section === "service-map"} />;
    case "models":
    case "tools":
    case "usage":
      return <AnalyticsPage scope={scope} mode={section} />;
    case "rules":
      return <RulesPage scope={scope} id={id} subview={subview} />;
    case "slos":
      return <SLOsPage scope={scope} />;
    case "incidents":
      return id ? (
        <IncidentPage scope={scope} id={id} />
      ) : (
        <IncidentsPage scope={scope} />
      );
    case "datasets":
      return <DatasetsPage scope={scope} />;
    case "evaluations":
      return id && id !== "new" ? (
        <EvaluationPage scope={scope} id={id} />
      ) : (
        <EvaluationsPage scope={scope} />
      );
    case "remediations":
      return id && id !== "history" ? (
        <RemediationPage scope={scope} id={id} />
      ) : (
        <RemediationsPage scope={scope} />
      );
    case "projects":
      return (
        <>
          <PageHeading
            title="Instrumentation & integrations"
            description="Connect real telemetry with project-scoped, revocable credentials."
          />
          <ProjectsPage
            identity={scope.identity}
            reload={projectsReload}
            scope={scope}
          />
        </>
      );
    case "keys":
      return <KeysPage scope={scope} />;
    case "audit":
      return <AuditPage scope={scope} />;
    case "settings":
    case "team":
      return <SettingsPage scope={scope} />;
    default:
      return (
        <>
          <PageHeading
            title="Capability unavailable"
            description="This part of the specification has not been implemented in this release."
          />
          <Link className="button" href={`${scope.base}/overview`}>
            Return to Command Center
          </Link>
        </>
      );
  }
}

// Keep keystrokes local: telemetry pages and the navigation shell do not own this draft.
function GlobalSearch({ base }: { base: string }) {
  const router = useRouter();
  const [search, setSearch] = useState("");
  return (
    <form
      className="global-search"
      role="search"
      onSubmit={(event) => {
        event.preventDefault();
        router.push(`${base}/traces?search=${encodeURIComponent(search)}`);
      }}
    >
      <Search size={15} />
      <input
        aria-label="Search traces"
        placeholder="Search traces…"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />
      <kbd>↵</kbd>
    </form>
  );
}
