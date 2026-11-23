---
name: full-sync
description: "Universal multi-agent synchronization & context synthesis engine. Bi-directionally syncs skills between projects and brain, promotes universal context (ideas, mistakes, constraints, resources) via Markdown AST, mirrors to <AGENTIC_VAULT>, and bootstraps workspaces."
---

# Full-Sync 3.0: Universal Master Synchronization Engine

> **Step-0 Project Overlay**: Before executing, check if `<active-project>/.agents/skill_overlays/full-sync.md` exists (via `python .agents/skills/auto-skill/scripts/resolve_skill_overlay.py --project <root> --skill full-sync`).

> [!IMPORTANT]
> ⛔ **EXECUTION-FIRST MANDATE**: Scripts in `scripts/` are executable software tools, NOT documentation. Never ask the user to run them or read them passively. Execute immediately via shell commands. When invoking Windows binaries from WSL, append `< /dev/null`.

---

## 1. The 5 Pillars of Full-Sync

| Pillar | Engine Script | Core Responsibility |
|:---|:---|:---|
| **1. Bi-directional Skill Sync** | `scripts/skill_reconciler.py` | Merkle SHA-256 diffs; backs up project skills to Brain; preserves 13 universal skills |
| **2. Universal Context Synthesis**| `scripts/conversation_distiller.py`<br>`scripts/context_promoter.py` | Watermarked transcript distillation (`--ai-studio` rolling summarizer); AST heuristic promotion |
| **3. Sovereign Vault Mirroring** | `scripts/sync_to_d_agentic.py` | Mirrors skills, context, and project archives to `<AGENTIC_VAULT>`; zero `~/.gemini/` pollution |
| **4. Autonomous Bootstrapper** | `scripts/bootstrap_project.py` | Hydrates new project workspaces with Hermes memory databases and agent rules |
| **5. Offload Message Boards** | `scripts/offload_manager.py` | Maintains project-scoped `offload/` directories and status boards |

---

## 2. Invariants & Boundaries

- **Universal Skill Preservation**: Canonical skills in `brain/.agents/skills/` are strictly limited to the 13 core powerhouses. Non-core universal candidates stage in `project_skills/_universal_candidates/`.
- **Dry-Run Safety**: Always verify planned synchronization actions with `--dry-run` before modifying file trees.
- **Sovereign Backup Invariant**: `<AGENTIC_VAULT>` is the sovereign disaster recovery vault. Vault sync never touches or mutates active workspace sources.

---

## 3. Core CLI Commands

```bash
# 1. Preview full synchronization changes across all pillars
python .agents/skills/full-sync/scripts/full_sync.py --project "<active_project>" --dry-run

# 2. Execute full synchronization across active project and Brain
python .agents/skills/full-sync/scripts/full_sync.py --project "<active_project>"

# 3. Run incremental conversation distillation with AI Studio summarizer
python .agents/skills/full-sync/scripts/conversation_distiller.py --project "<active_project>" --ai-studio

# 4. Mirror all brain skills and context to <AGENTIC_VAULT> vault
python scripts/sync_to_d_agentic.py
```

---

## 4. References & Architectural Guides

- [Sync Architecture & Vault Mirroring Guide](references/sync_architecture_guide.md) — Comprehensive technical reference for Merkle hashing, conversation watermarking, and vault disaster recovery.