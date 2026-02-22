---
name: token-usage
description: Report token usage for the current or most recent Copilot chat session. Use when user says "token usage", "how much context", "context usage", "token count", "how many tokens", or "check tokens".
---

# Token Usage Report

Run `scripts/parse_copilot_tokens.py` to parse Copilot chat session logs and report token usage.

```bash
python3 scripts/parse_copilot_tokens.py
```

Present the output as-is. Highlight if peak utilization exceeds 50%.
