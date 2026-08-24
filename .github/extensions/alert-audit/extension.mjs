import { createServer } from "node:http";

import { createCanvas, joinSession } from "@github/copilot-sdk/extension";

import { runAlertAudit, summarizeAudit } from "./lib/audit.mjs";
import { renderHtml } from "./lib/renderer.mjs";

const servers = new Map();

function normalizeOptions(input = {}) {
    return {
        environment: input.environment ?? "dev",
        resourceGroup: input.resourceGroup ?? "rg-ltc-dev",
        lookbackHours: input.lookbackHours ?? 24,
    };
}

function sendJson(res, status, value) {
    res.writeHead(status, {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
    });
    res.end(JSON.stringify(value));
}

async function refresh(entry) {
    if (entry.refreshPromise) {
        return entry.refreshPromise;
    }

    entry.refreshPromise = runAlertAudit(entry.options)
        .then((snapshot) => {
            entry.snapshot = snapshot;
            return snapshot;
        })
        .finally(() => {
            entry.refreshPromise = undefined;
        });
    return entry.refreshPromise;
}

async function startServer(options) {
    const entry = {
        options,
        snapshot: undefined,
        refreshPromise: undefined,
        server: undefined,
        url: undefined,
    };

    const server = createServer(async (req, res) => {
        const url = new URL(req.url ?? "/", "http://127.0.0.1");

        if (req.method === "GET" && url.pathname === "/") {
            res.writeHead(200, {
                "Content-Type": "text/html; charset=utf-8",
                "Cache-Control": "no-store",
                "Content-Security-Policy":
                    "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'",
            });
            res.end(renderHtml(options));
            return;
        }

        if (req.method === "GET" && url.pathname === "/api/snapshot") {
            sendJson(res, 200, entry.snapshot ?? { status: "not-run" });
            return;
        }

        if (req.method === "POST" && url.pathname === "/api/audit") {
            try {
                sendJson(res, 200, await refresh(entry));
            } catch (error) {
                sendJson(res, 500, {
                    status: "error",
                    error: error instanceof Error ? error.message : String(error),
                });
            }
            return;
        }

        sendJson(res, 404, { error: "Not found" });
    });

    await new Promise((resolve, reject) => {
        server.once("error", reject);
        server.listen(0, "127.0.0.1", resolve);
    });
    const address = server.address();
    const port = typeof address === "object" && address ? address.port : 0;
    entry.server = server;
    entry.url = `http://127.0.0.1:${port}/`;
    return entry;
}

const session = await joinSession({
    canvases: [
        createCanvas({
            id: "alert-audit",
            displayName: "Alert audit",
            description:
                "Compare Terraform-managed Azure Monitor alerts with live rules and recent firings.",
            inputSchema: {
                type: "object",
                additionalProperties: false,
                properties: {
                    environment: {
                        type: "string",
                        minLength: 1,
                        description: "Terraform environment name used in alert resource names.",
                    },
                    resourceGroup: {
                        type: "string",
                        minLength: 1,
                        description: "Azure resource group containing the alert rules.",
                    },
                    lookbackHours: {
                        type: "integer",
                        minimum: 1,
                        maximum: 168,
                        description: "Recent fired-alert lookback window.",
                    },
                },
            },
            actions: [
                {
                    name: "refresh",
                    description: "Refresh the Terraform and live Azure alert audit.",
                    handler: async (ctx) => {
                        const entry = servers.get(ctx.instanceId);
                        if (!entry) {
                            throw new Error(`Canvas instance ${ctx.instanceId} is not open`);
                        }
                        return summarizeAudit(await refresh(entry));
                    },
                },
                {
                    name: "get_summary",
                    description: "Return a compact summary of the latest alert audit.",
                    handler: async (ctx) => {
                        const entry = servers.get(ctx.instanceId);
                        if (!entry) {
                            throw new Error(`Canvas instance ${ctx.instanceId} is not open`);
                        }
                        return summarizeAudit(entry.snapshot ?? (await refresh(entry)));
                    },
                },
            ],
            open: async (ctx) => {
                let entry = servers.get(ctx.instanceId);
                if (!entry) {
                    entry = await startServer(normalizeOptions(ctx.input));
                    servers.set(ctx.instanceId, entry);
                }
                return {
                    title: `Alert audit · ${entry.options.environment}`,
                    status: entry.snapshot ? entry.snapshot.verdict : "Ready to audit",
                    url: entry.url,
                };
            },
            onClose: async (ctx) => {
                const entry = servers.get(ctx.instanceId);
                if (!entry) {
                    return;
                }
                servers.delete(ctx.instanceId);
                await new Promise((resolve) => entry.server.close(resolve));
            },
        }),
    ],
});

void session;
