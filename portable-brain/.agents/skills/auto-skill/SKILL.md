---
name: auto-skill
description: "Master Skill Lifecycle Engine: Discover, select, author, evaluate, benchmark, and optimize skills across universal and project-scoped registries."
---

# Auto-Skill: Master Skill Lifecycle & Dynamic Orchestrator

> **Step-0 Project Overlay**: Before executing, check if `<active-project>/.agents/skill_overlays/auto-skill.md` exists (via `python .agents/skills/auto-skill/scripts/resolve_skill_overlay.py --project <root> --skill auto-skill`).

> [!IMPORTANT]
> ⛔ **EXECUTION-FIRST MANDATE**: Scripts in `scripts/` are executable software tools, NOT documentation. Never ask the user to run them or read them passively. Execute immediately via shell commands. When invoking Windows binaries from WSL, append `< /dev/null`.

Auto-Skill is the universal capability registry and lifecycle engine across the multi-agent system. It routes user tasks to governing skills on Turn 1, authors and benchmarks new skills, and synchronizes catalogs.

---

## 1. Turn-1 Autonomous Routing Protocol

On Turn 1 of any user request, evaluate the domain and activate the governing skill immediately without waiting for slash commands:

| Domain / Task Type | Governing Universal Skill | Primary Capability |
|:---|:---|:---|
| **UI / Styling / Design Systems** | `ui-design-engine` | Dynamic archetype tokens, 15-point anti-slop verification |
| **Documents / Presentation / OCR** | `document-forge` | `gslides`, `gdocs`, PDF parsing, RapidOCR, spreadsheet formulas |
| **Reasoning / Architecture / RCA** | `deep-thinking` | 5-phase cognitive loop, Rolling-Window AI Pro consultation |
| **Web Search / Deep Research** | `web-search-orchestrator` | Gemini Web 4 Neon Deep Research, parallel search subagents |
| **Browser Automation / Headless** | `browser-operator` | Numeric DOM indexing, real Chrome profiles (max 3/6 tabs) |
| **Reverse Engineering / Binaries** | `rea` | Decompilation, AST recovery, Android/Electron disassembly |
| **Compute / GPUs / Batch Media** | `external-resource` | Google Flow batch studios, Colab, Kaggle, Modal serverless |
| **Multi-Project Sync & Vault** | `full-sync` | Merkle skill sync, context distillation, `<AGENTIC_VAULT>` mirror |
| **Task Offloading & Worker Mesh** | `offload` | Offload V3 multi-agent boards (`main-X`, `worker-X`, `collab-X`) |
| **Memory / User Modeling** | `hermes-agent-core` | SQLite+FTS5 memory search, session distillation, compaction |
| **Internal Tools / MCP / Extensions**| `internal-tools` | FastMCP, Antigravity SDK tools, Manifest V3 extensions |
| **Code Review / System Audits** | `exhaustive-audit-and-repair` | UMACAR squads, RTM extraction, anti-regression scanning |

---

## 2. Core CLI Commands

```bash
# 1. Query selector for best matching universal skill
python .agents/skills/auto-skill/scripts/select_skill.py "<query>" --universal

# 2. Query selector scoped to active project
python .agents/skills/auto-skill/scripts/select_skill.py "<query>" --project <active_project>

# 3. Synchronize registry and regenerate references catalog
python .agents/skills/auto-skill/scripts/sync_catalog.py

# 4. Validate skill structure and metadata
python .agents/skills/auto-skill/scripts/creator/quick_validate.py <path_to_skill>
```

---

## 3. Skill Scope Invariants

- **Universal Skills** reside strictly in `brain/.agents/skills/` (the 13 canonical skills).
- **Project Skills** reside strictly in `<active-project>/.agents/skills/` (archived in `brain/project_skills/<project>/`).
- **Zero Cross-Project Contamination**: Never load or reference Project A skills inside Project B.
- **Progressive Disclosure**: Detailed skill lists, schemas, and authoring guidelines reside in references.

---

## 4. References & Detailed Documentation

- [Complete Skills Catalog](references/catalog.md) — Full generated catalog of all system skills.
- [Project Overlays Specification](references/project_overlays.md) — Schema and contract for project-specific overlays.
- [Overlay Schemas JSON](references/overlay_schemas.json) — Formal JSON schema definitions for overlays.