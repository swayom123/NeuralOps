import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.describe.configure({ mode: "serial" });
const slug = `synthetic-fixture-browser-${Date.now()}`;
let projectId = "",
  incidentId = "";
async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByRole("button", { name: "Enter local workspace" }).click();
  await expect(page).toHaveURL(/\/app\//);
  await expect(page.locator(".onboarding, .app-shell")).toBeVisible();
}
const base = () => `/app/local/${slug}`;

test("browser → authenticated API → PostgreSQL → worker → incident and replay evaluation", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await signIn(page);
  if (
    await page
      .getByRole("heading", { name: "Your reliability workspace starts here." })
      .isVisible()
  ) {
    await page
      .getByLabel("Project name", { exact: true })
      .fill("Synthetic fixture · browser QA".replace(" · ", " - "));
  } else {
    await page.getByRole("link", { name: "Integrations", exact: true }).click();
    await page.getByRole("button", { name: "Create another project" }).click();
    await page
      .getByLabel("Project name", { exact: true })
      .fill("Synthetic fixture - browser QA");
  }
  await page.getByLabel("Project slug", { exact: false }).fill(slug);
  await page
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await page.goto(`${base()}/overview`);
  await expect(
    page.getByRole("heading", { name: "Command Center", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Waiting for telemetry", { exact: true }),
  ).toBeVisible();
  const projects = await (await page.request.get("/api/v1/projects")).json();
  projectId = projects.items.find((p: { slug: string }) => p.slug === slug).id;
  await page.goto(`${base()}/keys`);
  await page
    .getByRole("button", { name: "Issue ingestion credential" })
    .click();
  const key = await page.getByLabel("One-time ingestion secret").inputValue();
  expect(key).toMatch(/^nop_/);
  await page
    .getByRole("button", { name: "I saved it securely · dismiss" })
    .click();
  await expect(page.getByLabel("One-time ingestion secret")).toHaveCount(0);
  await page.goto(`${base()}/rules`);
  await page.getByRole("button", { name: "Create rule", exact: true }).click();
  await page
    .getByLabel("Rule name")
    .fill("Synthetic fixture retrieval failure");
  await page.getByLabel("Minimum samples").fill("2");
  await page
    .getByRole("button", { name: "Dry-run current window", exact: true })
    .click();
  await expect(
    page.getByText("INSUFFICIENT DATA", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Save rule", exact: true }).click();
  await expect(
    page.getByText("Synthetic fixture retrieval failure", { exact: true }),
  ).toBeVisible();
  await page.goto(`${base()}/slos`);
  await page.getByRole("button", { name: "Create SLO", exact: true }).click();
  await page.getByLabel("SLO name").fill("Browser success objective");
  await page.getByLabel("Objective (%)").fill("60");
  await page.getByLabel("Objective window (minutes)").fill("60");
  await page.getByLabel("Minimum samples").fill("3");
  await page.getByLabel("Long burn window (minutes)").fill("15");
  await page.getByRole("button", { name: "Save SLO", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Browser success objective" }),
  ).toBeVisible();
  for (let i = 0; i < 3; i++) {
    const traceId = crypto.randomUUID().replaceAll("-", "");
    const start = BigInt(Date.now()) * 1000000n;
    await new Promise((r) => setTimeout(r, 18));
    const end = BigInt(Date.now()) * 1000000n;
    const response = await page.request.post(
      "http://127.0.0.1:4318/v1/traces",
      {
        headers: {
          Authorization: `Bearer ${key}`,
          "Content-Type": "application/json",
        },
        data: {
          resourceSpans: [
            {
              resource: {
                attributes: [
                  {
                    key: "service.name",
                    value: { stringValue: "synthetic-fixture-browser" },
                  },
                ],
              },
              scopeSpans: [
                {
                  spans: [
                    {
                      traceId,
                      spanId: "a".repeat(16),
                      name: "synthetic-fixture/controlled-retrieval-timeout",
                      startTimeUnixNano: String(start),
                      endTimeUnixNano: String(end),
                      status: { code: i === 0 ? 1 : 2 },
                      attributes: [
                        {
                          key: "error.type",
                          value: { stringValue: "SyntheticTimeoutError" },
                        },
                      ],
                    },
                  ],
                },
              ],
            },
          ],
        },
      },
    );
    expect(response.ok()).toBeTruthy();
  }
  await expect
    .poll(
      async () =>
        (
          await (
            await page.request.get(
              `/api/v1/metrics/summary?project_id=${projectId}`,
            )
          ).json()
        ).executions,
    )
    .toBe(3);
  await expect
    .poll(
      async () =>
        (
          await (
            await page.request.get(`/api/v1/incidents?project_id=${projectId}`)
          ).json()
        ).items.length,
    )
    .toBe(1);
  await expect
    .poll(async () => {
      const response = await page.request.get(
        `/api/v1/slos?project_id=${projectId}`,
      );
      return (await response.json()).items[0]?.latest?.eligible_count;
    })
    .toBe(3);
  const incidents = await (
    await page.request.get(`/api/v1/incidents?project_id=${projectId}`)
  ).json();
  incidentId = incidents.items[0].id;
  await page.goto(`${base()}/overview`);
  await expect(
    page.getByText("Waiting for telemetry", { exact: true }),
  ).toHaveCount(0);
  await page.screenshot({
    path: "../artifacts/overview-1440.png",
    fullPage: true,
  });
  await page
    .getByRole("link", {
      name: "Synthetic fixture retrieval failure",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("heading", { name: "Ranked hypotheses", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Record", exact: true }).click();
  await page.getByLabel("Service").fill("synthetic-fixture-browser");
  await page.getByLabel("Version or revision").fill("browser-v2");
  await page
    .getByLabel("Recorded at")
    .fill(new Date().toISOString().slice(0, 16));
  await page
    .getByLabel("Description")
    .fill("Synthetic deployment correlated by event time");
  await page
    .getByRole("button", { name: "Record change", exact: true })
    .click();
  await expect(page.getByText("browser-v2", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Acknowledge", exact: true }).click();
  await expect(page.locator(".detail-status")).toHaveCount(0);
  await expect(page.getByText("ACKNOWLEDGED", { exact: true })).toBeVisible();
  const traceLink = page.locator(".evidence-link").first();
  await traceLink.click();
  await expect(
    page.getByRole("heading", { name: "Execution waterfall", exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/critical path/i).first()).toBeVisible();
  await expect(
    page.getByRole("tab", { name: "attributes", exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "attributes" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab", { name: "links" })).toBeFocused();
  await page.goto(`${base()}/datasets`);
  await page
    .getByRole("button", { name: "Publish dataset", exact: true })
    .click();
  await page
    .getByLabel("Dataset name", { exact: true })
    .fill("Synthetic paired replay fixture");
  await page.getByLabel("Paired cases (JSON array)").fill(
    JSON.stringify(
      Array.from({ length: 40 }, (_, i) => ({
        id: `fixture-${i}`,
        expected: "accepted",
        baseline_output: "rejected",
        candidate_output: "accepted",
      })),
    ),
  );
  await page
    .getByRole("button", { name: "Publish immutable dataset", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Synthetic paired replay fixture" }),
  ).toBeVisible();
  await page.goto(`${base()}/evaluations`);
  await page
    .getByRole("button", { name: "New replay evaluation", exact: true })
    .click();
  await page
    .getByLabel("Baseline manifest label")
    .fill("synthetic-baseline-v1");
  await page
    .getByLabel("Candidate manifest label")
    .fill("synthetic-candidate-v2");
  await page
    .getByRole("button", { name: "Queue replay evaluation", exact: true })
    .click();
  await expect
    .poll(
      async () =>
        (
          await (
            await page.request.get(
              `/api/v1/evaluations?project_id=${projectId}`,
            )
          ).json()
        ).items[0]?.status,
    )
    .toBe("COMPLETED");
  await page.getByRole("button", { name: "Refresh data", exact: true }).click();
  await page.locator("tbody .row-link").first().click();
  await expect(
    page.getByRole("heading", { name: "Case-level results", exact: true }),
  ).toBeVisible();
  await expect(page.locator("tbody tr")).toHaveCount(40);
  await page.goto(`${base()}/remediations?incident=${incidentId}`);
  await page.getByLabel("Target identifier").fill("staging/synthetic-fixture");
  await page
    .getByLabel("Rollback plan")
    .fill(
      "Restore the prior test deployment after failed health verification.",
    );
  await page
    .getByRole("button", { name: "Record proposal", exact: true })
    .last()
    .click();
  await page.locator("tbody .row-link").first().click();
  await expect(
    page.getByRole("button", { name: "Execute — disabled" }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Reject proposal", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Confirm rejection", exact: true })
    .click();
  await expect(page.getByText("REJECTED", { exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});

test("all implemented routes render, responsive widths do not overflow, and critical pages pass axe", async ({
  page,
}) => {
  test.setTimeout(180000);
  await signIn(page);
  for (const route of [
    "overview",
    "health",
    "service-map",
    "traces",
    "models",
    "tools",
    "usage",
    "rules",
    "slos",
    "incidents",
    "evaluations",
    "datasets",
    "remediations",
    "projects",
    "keys",
    "audit",
    "settings",
  ]) {
    await page.goto(`${base()}/${route}`);
    await expect(page.locator("h1")).toBeVisible();
    await expect(page.getByText("Loading measured data…")).toHaveCount(0);
    const result = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(
      result.violations,
      `Accessibility ${route}: ${JSON.stringify(result.violations.map((v) => ({ id: v.id, targets: v.nodes.map((n) => n.target) })))}`,
    ).toEqual([]);
  }
  for (const width of [375, 430, 768, 1024, 1440, 1920]) {
    await page.setViewportSize({ width, height: 1050 });
    for (const route of ["overview", "traces", "rules", "slos", "projects"]) {
      await page.goto(`${base()}/${route}`);
      await expect(page.locator("h1")).toBeVisible();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
        `Overflow ${width} ${route}`,
      ).toBeTruthy();
    }
    await page.goto(`${base()}/overview`);
    await expect(page.getByText("Loading measured data…")).toHaveCount(0);
    await page.screenshot({
      path: `../artifacts/overview-${width}.png`,
      fullPage: true,
    });
  }
  await page.setViewportSize({ width: 375, height: 850 });
  await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(
    page.getByRole("link", { name: "Trace Explorer", exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("link", { name: "Trace Explorer", exact: true }),
  ).toBeHidden();
  const mobileAxe = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(mobileAxe.violations).toEqual([]);
});

test("stale refresh, project cache isolation, and retention confirmation", async ({
  page,
}) => {
  await signIn(page);
  await page.goto(`${base()}/overview`);
  await expect(
    page
      .locator(".metric-card")
      .filter({ hasText: "Total executions" })
      .locator(".metric-value"),
  ).toHaveText("3");
  await page.route("**/api/v1/metrics/summary?*", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        code: "UPSTREAM_UNAVAILABLE",
        message: "Synthetic network fault",
        request_id: "fixture-network-fault",
      }),
    }),
  );
  await page.getByRole("button", { name: "Refresh data", exact: true }).click();
  await expect(page.locator(".stale-banner")).toContainText(
    "displayed data is stale",
  );
  await expect(
    page
      .locator(".metric-card")
      .filter({ hasText: "Total executions" })
      .locator(".metric-value"),
  ).toHaveText("3");
  await page.unroute("**/api/v1/metrics/summary?*");
  await page.getByRole("button", { name: "Refresh data", exact: true }).click();
  await expect(page.locator(".stale-banner")).toHaveCount(0);
  await page.goto(`${base()}/settings`);
  await page.getByLabel("Retain telemetry (days)", { exact: false }).fill("6");
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("button", { name: "Save retention policy" }).click();
  const projects = await (await page.request.get("/api/v1/projects")).json();
  expect(
    projects.items.find((p: { id: string }) => p.id === projectId)
      .retention_days,
  ).toBe(7);
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Save retention policy" }).click();
  await expect(page.getByRole("status")).toContainText(
    "Retention policy saved",
  );
  await page.getByLabel("Retain telemetry (days)", { exact: false }).fill("7");
  await page.getByRole("button", { name: "Save retention policy" }).click();
  const cookies = await page.context().cookies();
  const emptySlug = `${slug}-empty`;
  const created = await page.request.post("/api/v1/projects", {
    headers: {
      Origin: "http://localhost:3000",
      "X-CSRF-Token": cookies.find((c) => c.name === "neuralops_csrf")!.value,
    },
    data: {
      name: "Synthetic fixture - empty scope",
      slug: emptySlug,
      environment: "development",
    },
  });
  expect(created.status()).toBe(201);
  await page.goto(`${base()}/overview`);
  await page.getByLabel("Project", { exact: true }).selectOption(emptySlug);
  await expect(page).toHaveURL(new RegExp(`${emptySlug}/overview`));
  await expect(
    page.getByText("Waiting for telemetry", { exact: true }),
  ).toBeVisible();
  await expect(
    page
      .locator(".metric-card")
      .filter({ hasText: "Total executions" })
      .locator(".metric-value"),
  ).toHaveText("0");
  await expect(
    page.getByRole("link", {
      name: "Synthetic fixture retrieval failure",
      exact: true,
    }),
  ).toHaveCount(0);
});

test("missing replay guardrail measurements render as unknown", async ({
  page,
}) => {
  await signIn(page);
  const csrf = (await page.context().cookies()).find(
    (cookie) => cookie.name === "neuralops_csrf",
  )!.value;
  const headers = { Origin: "http://localhost:3000", "X-CSRF-Token": csrf };
  const fixtureSlug = `synthetic-guardrail-${Date.now()}`;
  const projectResponse = await page.request.post("/api/v1/projects", {
    headers,
    data: {
      name: "Synthetic guardrail fixture",
      slug: fixtureSlug,
      environment: "development",
    },
  });
  expect(projectResponse.status()).toBe(201);
  const project = await projectResponse.json();
  const datasetResponse = await page.request.post(
    `/api/v1/datasets?project_id=${project.id}`,
    {
      headers,
      data: {
        name: "Missing measurements fixture",
        cases: Array.from({ length: 35 }, (_, i) => ({
          id: `case-${i}`,
          expected: "yes",
          baseline_output: "no",
          candidate_output: "yes",
        })),
      },
    },
  );
  expect(datasetResponse.status()).toBe(201);
  const dataset = await datasetResponse.json();
  const runResponse = await page.request.post(
    `/api/v1/evaluations?project_id=${project.id}`,
    {
      headers: { ...headers, "Idempotency-Key": crypto.randomUUID() },
      data: {
        dataset_id: dataset.id,
        baseline: "v1",
        candidate: "v2",
        latency_budget_ms: 50,
      },
    },
  );
  expect(runResponse.status()).toBe(202);
  const run = await runResponse.json();
  await expect
    .poll(
      async () =>
        (
          await (
            await page.request.get(
              `/api/v1/evaluations/${run.id}?project_id=${project.id}`,
            )
          ).json()
        ).status,
    )
    .toBe("COMPLETED");
  await page.goto(`/app/local/${fixtureSlug}/evaluations/${run.id}`);
  await expect(page.locator(".detail-status")).toContainText("INCONCLUSIVE");
  await expect(
    page.getByText("Insufficient measurements", { exact: true }).first(),
  ).toBeVisible();
  await expect(page.locator("tbody tr")).toHaveCount(35);
  await expect(page.locator("tbody tr").first()).toContainText(
    "INSUFFICIENT DATA",
  );
  await page.getByRole("combobox").last().selectOption("regressions");
  await expect(page.locator("tbody tr")).toHaveCount(0);
});
