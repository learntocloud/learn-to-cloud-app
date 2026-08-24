function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

export function renderHtml(options) {
    const environment = escapeHtml(options.environment);
    const resourceGroup = escapeHtml(options.resourceGroup);
    const lookbackHours = escapeHtml(options.lookbackHours);

    return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Alert audit</title>
  <style>
    :root { color-scheme: light dark; }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--background-color-default, #fff);
      color: var(--text-color-default, #1f2328);
      font-family: var(--font-sans, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif);
      font-size: var(--text-body-medium, 14px);
      line-height: var(--leading-body-medium, 20px);
    }
    main { max-width: 1180px; margin: 0 auto; padding: 24px; }
    header { display: flex; gap: 20px; justify-content: space-between; align-items: flex-start; }
    h1 {
      margin: 0 0 6px;
      font-size: var(--text-title-large, 26px);
      line-height: var(--leading-title-large, 32px);
    }
    h2 { margin: 28px 0 12px; font-size: var(--text-title-medium, 18px); }
    p { margin: 0; color: var(--text-color-muted, #59636e); }
    button {
      border: 1px solid var(--border-color-default, #d1d9e0);
      border-radius: 6px;
      padding: 7px 14px;
      background: var(--true-color-blue, #0969da);
      color: var(--color-white, #fff);
      font: inherit;
      font-weight: var(--font-weight-semibold, 600);
      cursor: pointer;
    }
    button:disabled { opacity: .55; cursor: wait; }
    .meta { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
    .chip, .badge {
      display: inline-flex;
      align-items: center;
      border: 1px solid var(--border-color-default, #d1d9e0);
      border-radius: 999px;
      padding: 2px 8px;
      font-size: var(--text-body-small, 12px);
      white-space: nowrap;
    }
    .summary {
      display: grid;
      grid-template-columns: repeat(5, minmax(100px, 1fr));
      gap: 10px;
      margin-top: 22px;
    }
    .stat, .panel {
      border: 1px solid var(--border-color-default, #d1d9e0);
      border-radius: 8px;
      background: var(--background-color-muted, rgba(127,127,127,.04));
    }
    .stat { padding: 14px; }
    .stat strong { display: block; font-size: 22px; line-height: 28px; }
    .stat span { color: var(--text-color-muted, #59636e); }
    .panel { overflow: hidden; }
    table { width: 100%; border-collapse: collapse; }
    th, td {
      padding: 11px 12px;
      text-align: left;
      vertical-align: top;
      border-bottom: 1px solid var(--border-color-default, #d1d9e0);
    }
    th { color: var(--text-color-muted, #59636e); font-size: 12px; font-weight: 600; }
    tr:last-child td { border-bottom: 0; }
    code {
      font-family: var(--font-mono, "SFMono-Regular", Consolas, monospace);
      font-size: var(--text-code-inline, 12px);
    }
    .healthy { color: var(--true-color-green, #1a7f37); }
    .review, .unknown { color: var(--true-color-yellow, #9a6700); }
    .action-needed, .error { color: var(--true-color-red, #cf222e); }
    .issues { margin: 4px 0 0; padding-left: 18px; color: var(--true-color-red, #cf222e); }
    .empty, .loading { padding: 28px; text-align: center; color: var(--text-color-muted, #59636e); }
    .errors {
      padding: 12px 16px;
      border: 1px solid var(--true-color-red-muted, #ff818266);
      border-radius: 8px;
      background: color-mix(in srgb, var(--true-color-red, #cf222e) 8%, transparent);
    }
    .errors ul { margin: 6px 0 0; padding-left: 20px; }
    @media (max-width: 760px) {
      header { display: block; }
      button { margin-top: 16px; }
      .summary { grid-template-columns: repeat(2, 1fr); }
      .panel { overflow-x: auto; }
      table { min-width: 820px; }
    }
  </style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>Alert audit</h1>
      <p>Terraform intent compared with live Azure Monitor rules and recent firings.</p>
      <div class="meta">
        <span class="chip">Environment: <strong>&nbsp;${environment}</strong></span>
        <span class="chip">Resource group: <strong>&nbsp;${resourceGroup}</strong></span>
        <span class="chip">Lookback: <strong>&nbsp;${lookbackHours}h</strong></span>
      </div>
    </div>
    <button id="refresh" type="button">Refresh audit</button>
  </header>

  <section id="content" aria-live="polite">
    <div class="panel loading">Reading Terraform and Azure Monitor…</div>
  </section>
</main>
<script>
  const content = document.querySelector("#content");
  const refreshButton = document.querySelector("#refresh");

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function statusClass(value) {
    return String(value).toLowerCase().replaceAll(" ", "-");
  }

  function render(snapshot) {
    const errors = snapshot.errors?.length
      ? \`<div class="errors"><strong>Live Azure data is incomplete.</strong><ul>\${snapshot.errors
          .map((error) => \`<li>\${escapeHtml(error)}</li>\`).join("")}</ul></div>\`
      : "";
    const rows = snapshot.alerts.map((alert) => {
      const issues = alert.issues.length
        ? \`<ul class="issues">\${alert.issues.map((issue) => \`<li>\${escapeHtml(issue)}</li>\`).join("")}</ul>\`
        : "";
      const live = snapshot.errors.length
        ? "Unknown"
        : alert.live
          ? alert.liveEnabled ? "Enabled" : "Disabled"
          : "Missing";
      return \`<tr>
        <td><strong>\${escapeHtml(alert.name)}</strong><br><code>\${escapeHtml(alert.terraformId)}</code>\${issues}</td>
        <td><span class="badge \${statusClass(alert.status)}">\${escapeHtml(alert.status)}</span></td>
        <td>\${escapeHtml(live)}</td>
        <td>Sev \${escapeHtml(alert.severity)}</td>
        <td>\${escapeHtml(alert.frequency)} / \${escapeHtml(alert.window)}</td>
        <td>\${escapeHtml(alert.operator)} \${escapeHtml(alert.threshold)}</td>
        <td>\${escapeHtml(alert.firedCount)}</td>
      </tr>\`;
    }).join("");
    const stale = snapshot.stale.length
      ? \`<h2>Live rules not declared here</h2><div class="panel"><table>
          <thead><tr><th>Name</th><th>State</th><th>Azure type</th></tr></thead>
          <tbody>\${snapshot.stale.map((rule) => \`<tr><td>\${escapeHtml(rule.name)}</td>
            <td>\${rule.enabled ? "Enabled" : "Disabled"}</td><td><code>\${escapeHtml(rule.type)}</code></td></tr>\`).join("")}</tbody>
        </table></div>\`
      : "";

    content.innerHTML = \`
      <div class="summary">
        <div class="stat"><strong class="\${statusClass(snapshot.verdict)}">\${escapeHtml(snapshot.verdict)}</strong><span>Verdict</span></div>
        <div class="stat"><strong>\${snapshot.counts.declared}</strong><span>Declared</span></div>
        <div class="stat"><strong>\${snapshot.counts.live}</strong><span>Live</span></div>
        <div class="stat"><strong>\${snapshot.counts.fired}</strong><span>Fired in \${snapshot.lookbackHours}h</span></div>
        <div class="stat"><strong>\${snapshot.counts.actionNeeded + snapshot.counts.stale}</strong><span>Needs review</span></div>
      </div>
      <h2>Managed alerts</h2>
      \${errors}
      <div class="panel" style="margin-top: \${errors ? "12px" : "0"}">
        <table>
          <thead><tr><th>Alert</th><th>Audit</th><th>Azure</th><th>Severity</th><th>Frequency / window</th><th>Trigger</th><th>Firings</th></tr></thead>
          <tbody>\${rows}</tbody>
        </table>
      </div>
      \${stale}
      <p style="margin-top:12px">Source: <code>\${escapeHtml(snapshot.source)}</code> · Updated \${new Date(snapshot.generatedAt).toLocaleString()}</p>\`;
  }

  async function refresh() {
    refreshButton.disabled = true;
    refreshButton.textContent = "Refreshing…";
    try {
      const response = await fetch("/api/audit", { method: "POST" });
      const snapshot = await response.json();
      if (!response.ok) {
        throw new Error(snapshot.error ?? "Audit failed");
      }
      render(snapshot);
    } catch (error) {
      content.innerHTML = \`<div class="errors"><strong>Audit failed.</strong><div>\${escapeHtml(error.message)}</div></div>\`;
    } finally {
      refreshButton.disabled = false;
      refreshButton.textContent = "Refresh audit";
    }
  }

  refreshButton.addEventListener("click", refresh);
  refresh();
</script>
</body>
</html>`;
}
