import { execFile } from "node:child_process";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../../../..");
const MONITORING_PATH = resolve(REPO_ROOT, "infra/monitoring.tf");

function extractValue(body, key) {
    const match = body.match(new RegExp(`^\\s*${key}\\s*=\\s*("?)([^"\\n]+)\\1`, "m"));
    return match?.[2]?.trim();
}

function extractQuery(body) {
    return body.match(/query\s*=\s*<<-\w+\n([\s\S]*?)\n\s*\w+\n/)?.[1]?.trim() ?? null;
}

function parseBoolean(value) {
    if (value === "true") {
        return true;
    }
    if (value === "false") {
        return false;
    }
    return null;
}

function parseNumber(value) {
    if (value === undefined) {
        return null;
    }
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
}

function resolveName(value, environment) {
    return value?.replaceAll("${var.environment}", environment) ?? null;
}

export function parseDeclaredAlerts(source, environment) {
    const matches = [
        ...source.matchAll(
            /^resource "(azurerm_monitor_(?:metric_alert|scheduled_query_rules_alert_v2))" "([^"]+)" \{/gm,
        ),
    ];

    return matches.map((match, index) => {
        const end = matches[index + 1]?.index ?? source.length;
        const body = source.slice(match.index, end);
        const type = match[1] === "azurerm_monitor_metric_alert" ? "metric" : "scheduled-query";
        const name = resolveName(extractValue(body, "name"), environment);
        const actionAttached =
            body.includes("action_group_id") || body.includes("action_groups");

        return {
            terraformId: match[2],
            type,
            name,
            description: extractValue(body, "description") ?? null,
            severity: parseNumber(extractValue(body, "severity")),
            enabled: parseBoolean(extractValue(body, "enabled")),
            frequency:
                extractValue(body, type === "metric" ? "frequency" : "evaluation_frequency") ??
                null,
            window:
                extractValue(body, type === "metric" ? "window_size" : "window_duration") ??
                null,
            operator: extractValue(body, "operator") ?? null,
            threshold: parseNumber(extractValue(body, "threshold")),
            minimumFailingPeriods: parseNumber(
                extractValue(body, "minimum_failing_periods_to_trigger_alert"),
            ),
            evaluationPeriods: parseNumber(extractValue(body, "number_of_evaluation_periods")),
            actionAttached,
            query: extractQuery(body),
        };
    });
}

async function runAz(args) {
    const { stdout } = await execFileAsync("az", args, {
        timeout: 30_000,
        maxBuffer: 5 * 1024 * 1024,
        env: { ...process.env, AZURE_CORE_ONLY_SHOW_ERRORS: "true" },
    });
    return JSON.parse(stdout);
}

function errorMessage(error) {
    if (!(error instanceof Error)) {
        return String(error);
    }
    const stderr = "stderr" in error && typeof error.stderr === "string" ? error.stderr.trim() : "";
    return stderr || error.message;
}

async function getLiveAzureState(resourceGroup, lookbackHours) {
    const account = await runAz([
        "account",
        "show",
        "--query",
        "{subscriptionId:id,subscriptionName:name,tenantId:tenantId}",
        "--output",
        "json",
    ]);
    const base =
        `https://management.azure.com/subscriptions/${account.subscriptionId}` +
        `/resourceGroups/${encodeURIComponent(resourceGroup)}/providers/Microsoft.Insights`;
    const timeRange = lookbackHours <= 1 ? "1h" : lookbackHours <= 24 ? "1d" : "7d";
    const alertsUrl =
        `https://management.azure.com/subscriptions/${account.subscriptionId}` +
        `/providers/Microsoft.AlertsManagement/alerts?api-version=2019-03-01` +
        `&timeRange=${timeRange}&targetResourceGroup=${encodeURIComponent(resourceGroup)}`;

    const [metricResult, scheduledResult, firedResult] = await Promise.allSettled([
        runAz(["rest", "--method", "get", "--url", `${base}/metricAlerts?api-version=2018-03-01`]),
        runAz([
            "rest",
            "--method",
            "get",
            "--url",
            `${base}/scheduledQueryRules?api-version=2023-12-01`,
        ]),
        runAz(["rest", "--method", "get", "--url", alertsUrl]),
    ]);

    const errors = [];
    const valueOrEmpty = (result, label) => {
        if (result.status === "fulfilled") {
            return result.value.value ?? [];
        }
        errors.push(`${label}: ${errorMessage(result.reason)}`);
        return [];
    };

    return {
        account,
        rules: [
            ...valueOrEmpty(metricResult, "Metric alerts"),
            ...valueOrEmpty(scheduledResult, "Scheduled query rules"),
        ],
        fired: valueOrEmpty(firedResult, "Fired alerts"),
        errors,
    };
}

function normalizedName(value) {
    return value?.toLowerCase() ?? "";
}

function liveRuleEnabled(rule) {
    if (typeof rule.properties?.enabled === "boolean") {
        return rule.properties.enabled;
    }
    return rule.properties?.enabled === "true";
}

function firedRuleName(alert) {
    const essentials = alert.properties?.essentials ?? {};
    return essentials.alertRule ?? essentials.alertRuleName ?? alert.name ?? "";
}

function buildFindings(declared, liveRules, fired, liveErrors) {
    const liveByName = new Map(liveRules.map((rule) => [normalizedName(rule.name), rule]));
    const declaredNames = new Set(declared.map((rule) => normalizedName(rule.name)));
    const firedCounts = new Map();

    for (const alert of fired) {
        const name = normalizedName(firedRuleName(alert));
        firedCounts.set(name, (firedCounts.get(name) ?? 0) + 1);
    }

    const rows = declared.map((rule) => {
        const live = liveByName.get(normalizedName(rule.name));
        const issues = [];
        if (!rule.actionAttached) {
            issues.push("No action group in Terraform");
        }
        if (rule.enabled !== true) {
            issues.push("Disabled in Terraform");
        }
        if (!rule.description) {
            issues.push("Missing description");
        }
        if (!live && liveErrors.length === 0) {
            issues.push("Missing from Azure");
        }
        if (live && !liveRuleEnabled(live)) {
            issues.push("Disabled in Azure");
        }

        return {
            ...rule,
            live: Boolean(live),
            liveEnabled: live ? liveRuleEnabled(live) : null,
            firedCount: firedCounts.get(normalizedName(rule.name)) ?? 0,
            issues,
            status:
                issues.length > 0
                    ? "action-needed"
                    : liveErrors.length > 0
                      ? "unknown"
                      : "healthy",
        };
    });

    const stale = liveRules
        .filter((rule) => !declaredNames.has(normalizedName(rule.name)))
        .map((rule) => ({
            name: rule.name,
            enabled: liveRuleEnabled(rule),
            type: rule.type ?? "Azure Monitor rule",
        }));

    return { rows, stale };
}

function calculateVerdict(rows, stale, errors) {
    if (rows.some((row) => row.status === "action-needed")) {
        return "Action needed";
    }
    if (errors.length > 0) {
        return "Unknown";
    }
    if (stale.length > 0) {
        return "Review";
    }
    return "Healthy";
}

export async function runAlertAudit({ environment, resourceGroup, lookbackHours }) {
    const source = await readFile(MONITORING_PATH, "utf8");
    const declared = parseDeclaredAlerts(source, environment);
    let live = {
        account: null,
        rules: [],
        fired: [],
        errors: [],
    };

    try {
        live = await getLiveAzureState(resourceGroup, lookbackHours);
    } catch (error) {
        live.errors.push(`Azure discovery: ${errorMessage(error)}`);
    }

    const { rows, stale } = buildFindings(declared, live.rules, live.fired, live.errors);
    return {
        status: "complete",
        generatedAt: new Date().toISOString(),
        environment,
        resourceGroup,
        lookbackHours,
        source: "infra/monitoring.tf",
        subscription: live.account?.subscriptionName ?? null,
        verdict: calculateVerdict(rows, stale, live.errors),
        counts: {
            declared: rows.length,
            live: live.rules.length,
            fired: live.fired.length,
            actionNeeded: rows.filter((row) => row.status === "action-needed").length,
            stale: stale.length,
        },
        alerts: rows,
        stale,
        errors: live.errors,
    };
}

export function summarizeAudit(snapshot) {
    return {
        verdict: snapshot.verdict,
        generatedAt: snapshot.generatedAt,
        resourceGroup: snapshot.resourceGroup,
        counts: snapshot.counts,
        actionNeeded: snapshot.alerts
            .filter((alert) => alert.issues.length > 0)
            .map((alert) => ({ name: alert.name, issues: alert.issues })),
        stale: snapshot.stale,
        errors: snapshot.errors,
    };
}
