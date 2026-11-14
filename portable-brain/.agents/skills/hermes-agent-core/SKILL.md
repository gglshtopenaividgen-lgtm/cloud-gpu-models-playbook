---
name: hermes-agent-core
description: 'Hermes autonomous agent architecture: SQLite+FTS5 persistent memory, user modeling, skill synthesis, and context compaction. Use for memory recall.'
---
# Hermes Agent Cognitive Architecture & Universal Memory Engine

> [!IMPORTANT]
> ⛔ **EXECUTION-FIRST MANDATE (ZERO-PASSIVE-READING)**:
> Bundled scripts in `scripts/` are **executable software tools**, NOT reading material.
> When this skill is triggered, **EXECUTE the relevant script immediately** via `run_command`.
> **STRICT PROHIBITION**: NEVER call `view_file` on scripts in `scripts/` or explain their source code to the user unless explicitly ordered to edit or debug the script itself.
> Universal scripts can and must be executed from **ANY project workspace** by calling their absolute path:
> `python <BRAIN_ROOT>\.agents\skills\hermes-agent-core\scripts\<script_name> ...`


> **Master Guide for Experiential Learning, Dialectical User Modeling & Automated Skill Synthesis**  
> **Inspired by Nous Research Hermes Agent & OpenHermes Ecosystem**

---

## 1. Core Architectural Pillars

| Component | Purpose & Implementation | Storage Location |
|---|---|---|
| **Persistent MemoryEngine** | SQLite + FTS5 full-text search with BM25 ranking across all past conversations, architectural milestones, and debugging solutions. | `~/.gemini/antigravity/hermes_global_memory.db` & `<project>/.hermes/project_memory.db` |
| **Dialectical User Modeling** | Continuously tracks user preferences, coding habits, UI themes, and non-negotiables without re-prompting. | `user_profiles` table & `context/user_model.md` |
| **Conversational Learner** | Analyzes session transcripts (`transcript.jsonl`) to extract corrections, anti-patterns, and breakthrough insights. | `scripts/session_learner.py` |
| **Automated Skill Synthesizer** | Transforms completed multi-step solutions into standard Antigravity/Hermes skills (`SKILL.md`). | `scripts/skill_synthesizer.py` |
| **ContextEngine Compactor** | Maintains dense, high-signal project context summaries to prevent context window bloat during long sessions. | `scripts/context_compressor.py` |
| **Universal Project Bootstrapper** | 1-Click setup that scaffolds Hermes into any current or future project workspace. | `scripts/bootstrap_project.py` |

---

## 2. 1-Prompt Project Bootstrapping (Universal Setup)

Whenever the user is working in **ANY project** and says:
> *"configure the hermes skill from brain"* (or any variation like *"set up hermes in this project"*)

You MUST execute the bootstrapper command immediately:

```powershell
python <BRAIN_ROOT>\.agents\skills\hermes-agent-core\scripts\bootstrap_project.py --project-dir .
```

This automatically:
1. Scaffolds `.agents/skills/hermes-agent/SKILL.md` in the active project.
2. Creates `.agents/rules/hermes-context.md` with active memory search rules.
3. Initializes `context/user_model.md`, `context/decisions.md`, and `context/learnings.md`.
4. Initializes `.hermes/project_memory.db` with SQLite + FTS5 full-text indexing.
5. Runs an initial context compression to generate `context/active_context.md`.

---

## 3. CLI Command Reference

All scripts require **zero third-party dependencies** (built with Python 3.14 standard library).

### 1. Rapid Turn-1 Memory Recall CLI (Dual-Signal Hybrid Search)
Query past lessons, bug fixes, user profiles, or recent memories on Turn 1 via zero-cost hybrid search (SQLite FTS5 BM25 + subword character n-gram TF-IDF cosine similarity fused via Reciprocal Rank Fusion, $k=60$):
```powershell
# Dual-signal hybrid search (default: lexical + semantic with zero external API fees)
python <BRAIN_ROOT>\.agents\skills\hermes-agent-core\scripts\hermes_recall.py search "<keywords_or_phrase>"

# Force classic exact FTS5 match only:
python <BRAIN_ROOT>\.agents\skills\hermes-agent-core\scripts\hermes_recall.py search "<keywords>" --fts-only

# Standalone hybrid memory engine CLI:
python <BRAIN_ROOT>\.agents\skills\hermes-agent-core\scripts\hybrid_memory_engine.py

# Inspect user dialectical profile & preferences
python <BRAIN_ROOT>\.agents\skills\hermes-agent-core\scripts\hermes_recall.py profile

# View recent episodic memories
python <BRAIN_ROOT>\.agents\skills\hermes-agent-core\scripts\hermes_recall.py recent --limit 5
```

### 2. Pre-Compaction Session Memory Flush Protocol
Inspired by Nous Research Hermes Agent: Before long conversation contexts degrade or at the conclusion of major tasks, flush decisions and lessons to persistent disk:
```powershell
python <BRAIN_ROOT>\.agents\skills\hermes-agent-core\scripts\session_flush.py \
  --project "<project-name>" \
  --title "<milestone-title>" \
  --summary "<summary-of-accomplishments>" \
  --decision "<architectural-decision-for-ideas-md>" \
  --rationale "<impact-and-rationale>" \
  --mistake "<bug-or-anti-pattern-for-mistakes-md>" \
  --prevention "<rule-to-prevent-recurrence>" \
  --tags "architecture,api,milestone"
```

### 3. Memory Search & Low-Level Query
Low-level direct SQLite interface:
```powershell
python <BRAIN_ROOT>\.agents\skills\hermes-agent-core\scripts\hermes_memory.py search "<keywords>"
```

### 2. Store Learned Insight or Decision
Save an important milestone or architectural choice into memory:
```powershell
python <BRAIN_ROOT>\.agents\skills\hermes-agent-core\scripts\hermes_memory.py store --project "<project-name>" --category "<category>" --title "<title>" --content "<details>" --tags "<tag1,tag2>"
```
*Categories: `architecture`, `bug_fix`, `decision`, `preference`, `milestone`.*

### 3. Dialectical User Profile Inspection & Update
Read or record user preferences:
```powershell
# View profile
python <BRAIN_ROOT>\.agents\skills\hermes-agent-core\scripts\hermes_memory.py profile --get

# Set preference
python <BRAIN_ROOT>\.agents\skills\hermes-agent-core\scripts\hermes_memory.py profile --set-key "code_style" --set-val "Always use Tailwind glassmorphism and TypeScript strict"
```

### 4. Automated Skill Synthesis
Convert a freshly solved workflow into a permanent reusable skill:
```powershell
python <BRAIN_ROOT>\.agents\skills\hermes-agent-core\scripts\skill_synthesizer.py --name "<skill-slug>" --description "<description>" --instructions "<step-by-step procedures>" --triggers "<comma,separated,triggers>"
```

### 5. ContextEngine Compaction
Compress long project context files into a high-density summary:
```powershell
python <BRAIN_ROOT>\.agents\skills\hermes-agent-core\scripts\context_compressor.py --context-dir context --output context/active_context.md
```

### 6. Session Learning Extraction
Extract insights from conversation logs:
```powershell
python <BRAIN_ROOT>\.agents\skills\hermes-agent-core\scripts\session_learner.py --transcript "<path_to_transcript.jsonl>" --project "<project-name>"
```

---

## 4. Invariants & Boundaries

1. **Persistent Memory First**: Before proposing speculative solutions or asking questions about user habits, search memory first.
2. **Central Brain Safety**: The global memory database (`~/.gemini/antigravity/hermes_global_memory.db`) is cumulative and must never be wiped or deleted.
3. **Subagent Execution Invariant**: All synthesized subagent scripts or automated procedures must route to `TypeName='self'`, never `DeepCoder` or `DeepInvestigator`.
4. **Zero-Mock Data Rule**: Skills and memory entries must prioritize genuine upstream APIs and honest empty states over fake synthetic data.