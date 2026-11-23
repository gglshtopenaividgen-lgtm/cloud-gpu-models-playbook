---
name: hermes-agent-core
description: "Hermes autonomous agent architecture: SQLite+FTS5 persistent memory, user modeling, skill synthesis, and context compaction. Use for memory recall."
---

# Hermes Agent Core: Persistent Memory & Cognitive Architecture

> **Step-0 Project Overlay**: Before executing, check if `<active-project>/.agents/skill_overlays/hermes-agent-core.md` exists (via `python .agents/skills/auto-skill/scripts/resolve_skill_overlay.py --project <root> --skill hermes-agent-core`).

> [!IMPORTANT]
> ⛔ **EXECUTION-FIRST MANDATE**: Scripts in `scripts/` are executable software tools, NOT documentation. Never ask the user to run them or read them passively. Execute immediately via shell commands. When invoking Windows binaries from WSL, append `< /dev/null`.

---

## 1. Core Architectural Pillars

| Component | Responsibility & Engine | Storage Location |
|:---|:---|:---|
| **Persistent MemoryEngine** | SQLite + FTS5 full-text search with BM25 ranking across past solutions and milestones | `<project>/.hermes/project_memory.db`<br>`~/.gemini/antigravity/hermes_global_memory.db` |
| **Dialectical User Modeling** | Continuously tracks user preferences, coding patterns, and UI themes | `user_profiles` table & `context/user_model.md` |
| **Conversational Learner** | Analyzes transcripts to extract corrections, anti-patterns, and breakthrough insights | `scripts/session_learner.py` |
| **ContextEngine Compactor** | Maintains dense, high-signal project context summaries to prevent context bloat | `scripts/context_compressor.py` |
| **Project Bootstrapper** | Scaffolds Hermes memory tables and agent rules into any project workspace | `scripts/bootstrap_project.py` |

---

## 2. Memory Read/Write Decisions

- **Turn-1 Memory Recall**: When a task involves previous architecture decisions or recurring bugs, execute `memory_search.py` before formulating a plan.
- **Milestone Compaction**: Flush durable decisions and failure lessons to `context/decisions.md` and `context/learnings.md` at major milestones.
- **Zero External Dependencies**: Built strictly using the Python 3.14 standard library (`sqlite3`, `re`, `json`).

---

## 3. Core CLI Commands

```bash
# 1. Search global and project memory for past solutions
python .agents/skills/hermes-agent-core/scripts/memory_search.py "<query>"

# 2. Extract durable learnings from recent session transcript
python .agents/skills/hermes-agent-core/scripts/session_learner.py --transcript transcript.jsonl

# 3. Compress project context to eliminate bloat
python .agents/skills/hermes-agent-core/scripts/context_compressor.py --project "<active_project>"

# 4. Bootstrap Hermes memory engine into project
python .agents/skills/hermes-agent-core/scripts/bootstrap_project.py --project-dir "<active_project>"
```

---

## 4. References & Guides

- [Persistent Memory & Compaction Guide](references/memory_and_compaction_guide.md) — Schema specifications, BM25 ranking parameters, and compaction algorithms.