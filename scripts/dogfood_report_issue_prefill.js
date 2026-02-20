const { chromium } = require("playwright");
const { execSync } = require("child_process");
const path = require("path");

function getDogfoodCookie() {
  const apiDir = path.join(__dirname, "..", "api");
  const stdout = execSync("uv run python ../scripts/dogfood_session.py", {
    cwd: apiDir,
    encoding: "utf-8",
    stdio: ["ignore", "pipe", "pipe"],
  });
  return JSON.parse(stdout.trim());
}

async function decorateAndExtract(page, selector) {
  await page.waitForSelector(selector, { timeout: 10000 });
  await page.evaluate((sel) => {
    const a = document.querySelector(sel);
    if (!a) return;
    const event = new PointerEvent("pointerdown", { bubbles: true });
    a.dispatchEvent(event);
  }, selector);
  await page.waitForTimeout(200);
  return page.getAttribute(selector, "href");
}

function validateIssueUrl(href, expectations) {
  const url = new URL(href);
  const title = url.searchParams.get("title") || "";
  const labels = url.searchParams.get("labels") || "";
  const body = url.searchParams.get("body") || "";

  const checks = [
    ["title present", title.length > 0],
    ["labels present", labels.length > 0],
    ["body present", body.length > 0],
    ["body contains page url", body.includes("**Page:**")],
    ["body contains title", body.includes("**Title:**")],
    ["body contains when", body.includes("**When:**")],
    ["body contains environment", body.includes("## Environment") && body.includes("Browser:")],
    ["title contains expected", expectations.titleContains.some((s) => title.includes(s))],
    ["labels contains expected", expectations.labelsContains.every((s) => labels.includes(s))],
    ["body contains expected", expectations.bodyContains.every((s) => body.includes(s))],
  ];

  const failed = checks.filter(([, ok]) => !ok).map(([name]) => name);
  return { title, labels, body, failed };
}

(async () => {
  const consoleErrors = [];
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1400, height: 900 } });

  try {
    const cookie = getDogfoodCookie();
    await context.addCookies([
      {
        name: cookie.cookie_name,
        value: cookie.cookie_value,
        domain: cookie.domain,
        path: cookie.path,
      },
    ]);

    const page = await context.newPage();
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => consoleErrors.push(err.message));

    // Dashboard
    await page.goto("http://localhost:8000/dashboard", { waitUntil: "domcontentloaded", timeout: 15000 });
    const dashHref = await decorateAndExtract(page, 'a[data-report-issue]');
    const dashResult = validateIssueUrl(dashHref, {
      titleContains: ["Dashboard", "Issue"],
      labelsContains: [], // dashboard uses default labels (if any)
      bodyContains: ["page=dashboard"],
    });

    // Topic page (phase 1 first topic)
    await page.goto("http://localhost:8000/phase/1", { waitUntil: "domcontentloaded", timeout: 15000 });
    const firstTopicPath = await page.getAttribute('a[href^="/phase/1/"]', "href");
    if (!firstTopicPath) throw new Error("No topic links found on /phase/1");
    await page.goto(`http://localhost:8000${firstTopicPath}`, { waitUntil: "domcontentloaded", timeout: 15000 });

    const topicHref = await decorateAndExtract(page, 'a[data-report-issue]');
    const topicResult = validateIssueUrl(topicHref, {
      titleContains: ["Issue with"],
      labelsContains: ["content"],
      bodyContains: ["**Context:** phase=1, topic="],
    });

    const output = {
      ok: dashResult.failed.length === 0 && topicResult.failed.length === 0 && consoleErrors.length === 0,
      consoleErrors,
      dashboard: { href: dashHref, failed: dashResult.failed, title: dashResult.title, labels: dashResult.labels },
      topic: { path: firstTopicPath, href: topicHref, failed: topicResult.failed, title: topicResult.title, labels: topicResult.labels },
    };

    console.log(JSON.stringify(output, null, 2));
    process.exit(output.ok ? 0 : 2);
  } catch (err) {
    console.error("ERROR:", err && err.message ? err.message : err);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
