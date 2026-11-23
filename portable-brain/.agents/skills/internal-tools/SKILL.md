---
name: internal-tools
description: "Universal Internal Tooling Powerhouse: Build and orchestrate MCP servers (FastMCP/TypeScript), native Antigravity SDK tool schemas and subagent capabilities, Manifest V3 Chrome Extensions, and author standardized skills."
---

# Universal Internal Tooling & Extension Architecture Suite

> **Step-0 Project Overlay**: Before executing, check if `<active-project>/.agents/skill_overlays/internal-tools.md` exists (via `python .agents/skills/auto-skill/scripts/resolve_skill_overlay.py --project <root> --skill internal-tools`).

> [!IMPORTANT]
> ⛔ **EXECUTION-FIRST MANDATE**: Scripts in `scripts/` are executable software tools, NOT documentation. Never ask the user to run them or read them passively. Execute immediately via shell commands. When invoking Windows binaries from WSL, append `< /dev/null`.

The unified authority for authoring, evaluating, and operating all agent-internal extensibility: MCP servers, native Antigravity SDK tools, Chrome MV3 extensions, and standardized skills.

---

## 1. Domain Decision Router

When activating `internal-tools`, identify the target pillar and consult the corresponding playbook:

| Pillar / Objective | Target Domain Playbook | Key Responsibilities |
|:---|:---|:---|
| **Pillar 1: MCP Server Engineering** | [`playbooks/01-mcp-engineering.md`](playbooks/01-mcp-engineering.md) | FastMCP (Python) or TypeScript MCP SDK; `.mcp.json` management |
| **Pillar 2: Antigravity SDK Tools** | [`playbooks/02-antigravity-sdk-tools.md`](playbooks/02-antigravity-sdk-tools.md) | Native Antigravity tool schemas; deterministic CLI/RPC handlers |
| **Pillar 3: Chrome MV3 Extensions** | [`playbooks/03-chrome-extension-mv3.md`](playbooks/03-chrome-extension-mv3.md) | Persistent background service workers, WebSocket bridge, CDP automation |
| **Pillar 4: Custom Skill Authoring** | [`playbooks/04-skill-authoring-standard.md`](playbooks/04-skill-authoring-standard.md) | Token-efficient `SKILL.md` packages, Universal vs Project-Scoped isolation |

---

## 2. Core Scaffolding Commands

```bash
# 1. Scaffold a new FastMCP server (Python)
python .agents/skills/internal-tools/scripts/scaffold_tool.py --type mcp --name my-custom-mcp --out src/mcp_server

# 2. Scaffold a new Antigravity SDK tool definition
python .agents/skills/internal-tools/scripts/scaffold_tool.py --type sdk --name custom_evaluator --out tools/

# 3. Scaffold a Chrome MV3 Extension with agent WebSocket bridge
python .agents/skills/internal-tools/scripts/scaffold_tool.py --type chrome --name agent-tab-bridge --out extensions/

# 4. Scaffold a new project-scoped skill
python .agents/skills/internal-tools/scripts/scaffold_tool.py --type skill --name my-skill --project <active_project>

# 5. Lint and validate an internal tool or skill
python .agents/skills/internal-tools/scripts/scaffold_tool.py --lint <path_to_tool>
```

---

## 3. References & Playbooks

- [Playbook 1: MCP Engineering](playbooks/01-mcp-engineering.md)
- [Playbook 2: Antigravity SDK Tools](playbooks/02-antigravity-sdk-tools.md)
- [Playbook 3: Chrome MV3 Extensions](playbooks/03-chrome-extension-mv3.md)
- [Playbook 4: Skill Authoring Standard](playbooks/04-skill-authoring-standard.md)
- [Cloud MCP Servers Reference](references/cloud_mcp_servers.md)
- [MCP Best Practices](references/mcp_best_practices.md)
- [Evaluation Criteria](references/evaluation.md)