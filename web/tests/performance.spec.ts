import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import type { Identity, Project, TraceDetail } from "../lib/types";

// Explicit synthetic API fixtures isolate rendering from database/network variance.
// Live authenticated integration remains covered by console.spec.ts.
const project: Project = {
  id: "00000000-0000-4000-8000-000000000001",
  name: "Synthetic performance fixture",
  slug: "synthetic-fixture-performance",
  environment: "development",
  retention_days: 7,
  created_at: "2026-10-25T00:00:00Z",
};
const identity: Identity = {
  id: "fixture-user",
  name: "Performance Fixture",
  role: "admin",
  organization: { id: "fixture-org", slug: "local", name: "Synthetic fixture" },
  development: true,
  remote_execution: false,
};
const trace: TraceDetail = {
  id: "fixture",
  trace_id: "fixture",
  operation: "Synthetic root",
  service: "synthetic",
  start_ns: 0,
  duration_ms: 2000,
  status: "ok",
  span_count: 2000,
  tokens: null,
  issues: [],
  critical_path: ["0", "1999"],
  critical_path_duration_ms: 2,
  truncated: false,
  privacy: "Metadata-only synthetic fixture",
  spans: Array.from({ length: 2000 }, (_, i) => ({
    id: String(i),
    span_id: String(i),
    parent_span_id: i ? String(i - 1) : "",
    operation: `Synthetic operation ${i}`,
    service: "synthetic",
    start_ns: i * 1e6,
    end_ns: (i + 1) * 1e6,
    status: "ok",
    attributes: { index: i },
    links: [],
    redacted_count: 0,
  })),
};
const base = `/app/local/${project.slug}`;

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    const body =
      pathname === "/api/v1/me"
        ? identity
        : pathname === "/api/v1/projects"
          ? { items: [project] }
          : pathname === "/api/v1/traces/fixture"
            ? trace
            : { items: [] };
    await route.fulfill({ json: body });
  });
});

test("large waterfall retains exact evidence through keyboard, scroll, polling and inspector tabs", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(`${base}/traces/fixture`);
  const rows = page.locator(".span-row");
  await expect(rows.first()).toContainText("Synthetic operation 0");
  expect(await rows.count()).toBeLessThanOrEqual(16);
  await rows.first().focus();
  await page.keyboard.press("End");
  const last = page.locator('[data-span-index="1999"]');
  await expect(last).toBeFocused();
  await last.click();
  await expect(page.locator(".inspector-body")).toContainText('"index": 1999');
  await expect(last).toHaveAttribute("aria-pressed", "true");
  await expect(last).toContainText("critical path");
  await expect(last).toContainText("1 ms");
  await page.getByRole("button", { name: "Refresh data", exact: true }).click();
  await expect(last).toHaveAttribute("aria-pressed", "true");
  await last.focus();
  await page.keyboard.press("Home");
  await expect(page.locator('[data-span-index="0"]')).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(page.locator('[data-span-index="1"]')).toBeFocused();
  await page.locator(".virtual-span-list").evaluate((element) => {
    element.scrollTop = 60000;
  });
  await expect(page.locator('[data-span-index="1000"]')).toBeVisible();
  expect(await rows.count()).toBeLessThanOrEqual(16);
  await page.getByRole("tab", { name: "attributes", exact: true }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(
    page.getByRole("tab", { name: "links", exact: true }),
  ).toBeFocused();
  await page
    .getByLabel("Search traces", { exact: true })
    .pressSequentially("synthetic search");
  await expect(page.locator(".inspector-body")).toHaveText("[]");
  expect(errors).toEqual([]);
});

for (const width of [375, 768, 1024, 1440, 1920]) {
  test(`waterfall accessibility and responsive layout at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 1050 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto(`${base}/traces/fixture`);
    await expect(page.locator(".span-row").first()).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
    const result = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(result.violations).toEqual([]);
    if (width < 1024) {
      await page.getByRole("button", { name: "Open navigation" }).click();
      await expect(
        page.getByRole("link", { name: "Trace Explorer", exact: true }),
      ).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(
        page.getByRole("button", { name: "Open navigation" }),
      ).toBeFocused();
    }
  });
}

test("evaluation dataset requests only run while setup is visible", async ({
  page,
}) => {
  let requests = 0;
  await page.route("**/api/v1/datasets?*", async (route) => {
    requests++;
    await route.fulfill({ json: { items: [] } });
  });
  await page.goto(`${base}/evaluations`);
  await expect(page.getByText("No evaluations yet")).toBeVisible();
  expect(requests).toBe(0);
  await page.getByRole("button", { name: "Refresh data", exact: true }).click();
  await page
    .getByRole("button", { name: "New replay evaluation", exact: true })
    .click();
  await expect(page.getByText("A published dataset is required")).toBeVisible();
  expect(requests).toBe(1);
  await page.getByRole("button", { name: "Close setup", exact: true }).click();
  await page
    .getByRole("button", { name: "New replay evaluation", exact: true })
    .click();
  await expect(page.getByText("A published dataset is required")).toBeVisible();
  expect(requests).toBe(2); // No completed-response cache on reopening.
});
