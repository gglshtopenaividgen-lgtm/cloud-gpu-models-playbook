# Hermes Agent Core: Persistent Memory & Context Compaction Guide

Technical reference for SQLite+FTS5 memory retrieval, user modeling, and token compaction.

---

## 1. SQLite + FTS5 Full-Text Search Architecture

- **Schema**: Stores indexed conversation turns, architectural decisions, and error resolutions.
- **Hybrid Search**: Combines BM25 term weighting with recency biasing.
- **Database Locations**:
  - Global memory: `~/.gemini/antigravity/hermes_global_memory.db`
  - Project memory: `<project>/.hermes/project_memory.db`

---

## 2. CLI Utilities

```bash
# Search memory for past solutions
python .agents/skills/hermes-agent-core/scripts/memory_search.py "database migration failure"

# Extract insights from recent conversation
python .agents/skills/hermes-agent-core/scripts/session_learner.py --transcript transcript.jsonl

# Compress project context to eliminate bloat
python .agents/skills/hermes-agent-core/scripts/context_compressor.py --project "<project_path>"

# Bootstrap Hermes into a new project
python .agents/skills/hermes-agent-core/scripts/bootstrap_project.py --project-dir "<project_path>"
```
