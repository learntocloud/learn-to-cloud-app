---
applyTo: '**/*'
---

# Copilot Terminology

## "Skill" Definition

When the user asks to "create a skill", they mean a **VS Code Agent Skill** - NOT a bash script.

Agent Skills are stored in `.github/skills/<skill-name>/SKILL.md` and follow this format:

```markdown
---
name: skill-name
description: Description of what the skill does and when to use it (max 1024 chars)
---

# Skill Instructions

Detailed instructions, guidelines, commands, and examples...
```

### Key Points:
- Skills are loaded automatically by Copilot when relevant to the user's request
- Store in `.github/skills/<skill-name>/SKILL.md`
- Can include additional scripts, examples, or other resources in the skill directory
- Reference scripts in SKILL.md using relative paths like `[script](./script.sh)`
- The `description` field helps Copilot decide when to load the skill
- The `name` field **must match the parent directory name** (e.g., `debug-deploy/SKILL.md` needs `name: debug-deploy`)

### When to Create a Skill:
- User asks to "create a skill for X"
- User wants to teach Copilot a reusable workflow
- User wants automated debugging/testing/deployment procedures

### Skill vs Custom Instructions:
- **Skills** = Task-specific capabilities, loaded on-demand, can include scripts
- **Instructions** = Coding standards/guidelines, always applied or via glob patterns

Reference: https://code.visualstudio.com/docs/copilot/customization/agent-skills
