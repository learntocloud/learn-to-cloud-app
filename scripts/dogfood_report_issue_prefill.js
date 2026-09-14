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
  const template = url.searchParams.get("template") || "";
  const location = url.searchParams.get("location") || "";
  const pageUrl = url.searchParams.get("page-url") || "";
  const diagnostics = url.searchParams.get("diagnostics") || "";
  const automaticFields = ["template", "title", "location", "page-url", "diagnostics"];

  const checks = [
    ["correct repository", url.origin === "https://github.com" && url.pathname === "/learntocloud/learn-to-cloud-app/issues/new"],
    ["title present", title.length > 0],
    ["correct issue form", template === expectations.template],
    ["only context is prefilled", [...url.searchParams.keys()].every((key) => automaticFields.includes(key))],
    ["page url contains only route", pageUrl === expectations.pageUrl],
    ["report time present", /Reported at: \d{4}-\d{2}-\d{2}T/.test(diagnostics)],
    ["browser present", /Browser: \S/.test(diagnostics)],
    ["title contains expected", expectations.titleContains.some((s) => title.includes(s))],
    ["location contains expected", expectations.locationContains.every((s) => location.includes(s))],
  ];

  const failed = checks.filter(([, ok]) => !ok).map(([name]) => name);
  return { title, template, location, pageUrl, diagnostics, failed };
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
      template: "app_problem.yml",
      pageUrl: "http://localhost:8000/dashboard",
      locationContains: ["page=dashboard"],
    });

    // Topic page (phase 1 first topic)
    await page.goto("http://localhost:8000/phase/1", { waitUntil: "domcontentloaded", timeout: 15000 });
    const firstTopicPath = await page.getAttribute('a[href^="/phase/1/"]', "href");
    if (!firstTopicPath) throw new Error("No topic links found on /phase/1");
    await page.goto(`http://localhost:8000${firstTopicPath}`, { waitUntil: "domcontentloaded", timeout: 15000 });

    const topicHref = await decorateAndExtract(page, 'a[data-report-issue]');
    const topicResult = validateIssueUrl(topicHref, {
      titleContains: ["Issue with"],
      template: "content_problem.yml",
      pageUrl: `http://localhost:8000${firstTopicPath}`,
      locationContains: ["phase=1, topic="],
    });

    const output = {
      ok: dashResult.failed.length === 0 && topicResult.failed.length === 0 && consoleErrors.length === 0,
      consoleErrors,
      dashboard: { href: dashHref, failed: dashResult.failed, title: dashResult.title, template: dashResult.template },
      topic: { path: firstTopicPath, href: topicHref, failed: topicResult.failed, title: topicResult.title, template: topicResult.template },
    };

    console.log(JSON.stringify(output, null, 2));
    process.exitCode = output.ok ? 0 : 2;
  } catch (err) {
    console.error("ERROR:", err && err.message ? err.message : err);
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
