---
name: internal-tools
description: "Universal Internal Tooling Powerhouse: Build and orchestrate MCP servers (FastMCP/TypeScript), native Antigravity SDK tool schemas and subagent capabilities, Manifest V3 Chrome Extensions, and author standardized skills."
compatibility: Windows 11 PowerShell, Python 3.10+, Node.js 20+
metadata:
  version: "1.0.0"
  type: "universal-skill"
  scope: "Universal"
---

# Universal Internal Tooling & Extension Architecture Suite

> [!IMPORTANT]
> ⛔ **EXECUTION-FIRST MANDATE (ZERO-PASSIVE-READING)**:
> Bundled scripts in `scripts/` are **executable software tools**, NOT reading material.
> When this skill is triggered, **EXECUTE the relevant script immediately** via `run_command`.
> Universal scripts can and must be executed from **ANY project workspace** by calling their absolute path:
> `python <BRAIN_ROOT>\.agents\skills\internal-tools\scripts\<script_name> ...`

The unified authority for authoring, evaluating, and operating all agent-internal extensibility:
1. **MCP Engineering & Multi-Cloud Orchestration** (Python FastMCP, TypeScript MCP SDK, stdio/SSE/Streamable HTTP, Cloudflare, Appwrite, AWS, Azure, GitHub).
2. **Antigravity SDK Tool Engineering** (Native IDE tool schemas, component registry compatibility, `define_subagent` tool delegation).
3. **Chrome Manifest V3 Extensions** (Background service workers, offscreen documents, content script bridges, trusted CDP hardware automation, anti-throttling).
4. **Skill Authoring Standard** (Branching-Hub architecture, token-budget guardrails, Universal vs Project-Scoped isolation invariant).

---

## 1. Domain Decision Router (Progressive Disclosure)

When activating `internal-tools`, identify the target pillar and lazily read **only** the corresponding playbook:

| Pillar / Objective | Target Domain Playbook | Key Responsibilities |
|---|---|---|
| **Pillar 1: MCP Server Engineering & Cloud Orchestration** | [`playbooks/01-mcp-engineering.md`](playbooks/01-mcp-engineering.md) | • Build custom FastMCP (Python) or MCP SDK (TypeScript) servers.<br>• Manage `.mcp.json` / `mcp_config.json` endpoints.<br>• Query configured cloud MCPs (Cloudflare, Appwrite, AWS, Azure, GitHub, Chrome DevTools). |
| **Pillar 2: Antigravity SDK Tool Creation** | [`playbooks/02-antigravity-sdk-tools.md`](playbooks/02-antigravity-sdk-tools.md) | • Author native Antigravity tool definitions with strict JSON schemas.<br>• Implement CLI/RPC deterministic execution handlers.<br>• Guard against missing components in `language_server.exe`. |
| **Pillar 3: Chrome Manifest V3 Extension & Bridge Engineering** | [`playbooks/03-chrome-extension-mv3.md`](playbooks/03-chrome-extension-mv3.md) | • Build MV3 extensions with persistent service workers & offscreen workers.<br>• Build WebSocket / Native Messaging bridges to local agent daemons.<br>• Avoid Chrome background timer throttling (`Page.bringToFront`). |
| **Pillar 4: Custom Skill Authoring Standard** | [`playbooks/04-skill-authoring-standard.md`](playbooks/04-skill-authoring-standard.md) | • Author clean, token-efficient `SKILL.md` packages.<br>• Enforce Universal (`brain/.agents/skills/`) vs Project-Specific (`<project>/.agents/skills/`) separation.<br>• Prevent nested `SKILL.md` discovery bloat. |

---

## 2. CLI Scaffolding & Validation Suite

Use the bundled generator to scaffold production-ready templates in seconds:

```powershell
# 1. Scaffold a new FastMCP server (Python)
python <BRAIN_ROOT>\.agents\skills\internal-tools\scripts\scaffold_tool.py --type mcp --name my-custom-mcp --out src/mcp_server

# 2. Scaffold a new Antigravity SDK tool definition
python <BRAIN_ROOT>\.agents\skills\internal-tools\scripts\scaffold_tool.py --type sdk --name custom_evaluator --out tools/

# 3. Scaffold a Chrome MV3 Extension with agent WebSocket bridge
python <BRAIN_ROOT>\.agents\skills\internal-tools\scripts\scaffold_tool.py --type chrome --name agent-tab-bridge --out extensions/

# 4. Scaffold a new project-scoped skill
python <BRAIN_ROOT>\.agents\skills\internal-tools\scripts\scaffold_tool.py --type skill --name my-project-skill --project project-web

# 5. Lint and validate an internal tool, extension manifest, or skill
python <BRAIN_ROOT>\.agents\skills\internal-tools\scripts\validate_internal_tool.py path/to/tool_or_skill
```

---

## 3. Tool Boundaries & Separation of Concerns

- **`internal-tools` vs `auto-skill`**: `internal-tools` owns authoring, templating, and linting of new tools and skills. `auto-skill` owns runtime discovery (`select_skill.py`) and catalog synchronization (`sync_catalog.py`).
- **`internal-tools` vs `browser-operator`**: `internal-tools` builds the extension manifests, service workers, and bridge architecture. `browser-operator` drives live DOM automation using numeric indexing and Bézier mouse curves.
- **`internal-tools` vs `ui-design-engine`**: `internal-tools` wires extension messaging and chrome storage. `ui-design-engine` designs user-facing UI, popup styling, and dark glassmorphic components.
- **`internal-tools` vs Runtime MCP Calls**: `internal-tools` manages server creation and endpoint configurations. Direct calls to pre-configured MCP tools (e.g. `d1_query`, `call_aws`) occur natively during task execution.
