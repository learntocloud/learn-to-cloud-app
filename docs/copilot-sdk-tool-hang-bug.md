# Copilot CLI hangs after tool execution with Azure BYOK

> For [github/copilot-sdk#239](https://github.com/github/copilot-sdk/issues/239)

CLI `@github/copilot@0.0.406`, Python SDK `0.1.0`, Azure BYOK (`type: "azure"`, `wire_api: "completions"`).

**Without tools** — works fine (1s response).
**With tools** — hangs indefinitely after the tool returns. The first turn completes (tool called + executed), but the second turn (processing tool results) never finishes. Last event received is `session.usage_info`, then silence.

```
assistant.turn_start        # Turn 1
assistant.message           # LLM calls tool
tool.execution_start
tool.execution_complete     # Tool returns OK
assistant.turn_end
assistant.turn_start        # Turn 2
session.usage_info          # ← hangs here forever
```

Same credentials work fine calling Azure OpenAI directly via `httpx`. Tested with both `gpt-4o-mini` and `gpt-5-mini`. 100% reproducible locally in Docker and in Azure Container Apps.

**Workaround:** Bypass SDK/CLI, call Chat Completions API directly with manual tool-calling loop.
