"""
Universal Hermes Project Bootstrapper
Configures any project with the Hermes Cognitive Engine:
- Persistent SQLite + FTS5 local/global memory
- Conversational learning loop
- Automated skill synthesis
- ContextEngine compaction & dialectical user model
"""

import argparse
import os
import shutil
import sqlite3
import sys
from pathlib import Path

BRAIN_ROOT = Path("./")
HERMES_CORE_DIR = BRAIN_ROOT / ".agents" / "skills" / "hermes-agent-core"
HERMES_SCRIPTS_DIR = HERMES_CORE_DIR / "scripts"


IDEAS_TEMPLATE = """# {project_title} ARCHITECTURAL IDEAS & FEATURE ROADMAP

> **Source-of-truth for finalized architectural decisions, requirements, and design specifications.**
> **Synchronized with Central Brain permanent experiential memory.**

---

## 1. Project Overview & Scope
- **Project**: `{project_name}`
- **Status**: Active Development
- **Scope**: Refer to `file_map.md` for codebase architecture.

---

## 2. Chronological Requirements & Decisions Ledger
- [INIT] Project initialized and bootstrapped with Hermes Cognitive Engine and Context Suite ({date}).
"""

MISTAKES_TEMPLATE = """# {project_title} MISTAKES & LESSONS LEARNED

> **Forensic failure log, regression tracker, and debugging anti-patterns for {project_name}.**
> **Synchronized with Central Brain permanent experiential memory.**

---

## 1. System Invariants & Anti-Patterns
- **Subagent Routing Invariant**: NEVER invoke `TypeName='DeepCoder'` or `TypeName='DeepInvestigator'` (missing `skill_search` crash). Always use `TypeName='self'`.
- **Zero Mock Data Policy**: Never synthesize fake mock data or placeholder responses when upstream APIs fail.
- **Proof-of-Work Verification**: Run build/type checks before declaring tasks complete.

---

## 2. Forensic Failure & Bug Fix Log
- [INIT] Learning engine activated. Log all future bugs, root causes, and regressions here.
"""

CONSTRAINTS_TEMPLATE = """# {project_title} DYNAMIC ARCHITECTURAL CONSTRAINTS

> **Living single source of truth for active non-negotiable boundaries and invariants for {project_name}.**

---

## 1. Universal Multi-Agent Invariants
- **Subagent Routing**: In Antigravity runtime, NEVER use `TypeName='DeepCoder'` or `TypeName='DeepInvestigator'`. Always use `TypeName='self'` for coding and `TypeName='research'` for exploration.
- **Zero Mock Data**: Authentic upstream error handling and clean empty states only.
- **Cloud Free Tier Guardrails**: 0 Public IPv4 addresses, P6 64GB SSDs, Supabase 500MB DB limit, AWS Lambda compute.
- **Mobile Ergonomics**: Interactive touch targets >= 44px (`min-h-[44px]`), zero horizontal overflow on <= 375px viewports.
- **Proof-of-Work Standard**: Live static analysis and build verification before completion.

---

## 2. Project-Specific Constraints
- Record active project-specific boundaries, API rate limits, and architecture invariants here.
"""

RESOURCES_TEMPLATE = """# {project_title} RESOURCES & CREDENTIALS LEDGER

> **Active cloud resources, endpoints, credentials, VM IPs, and database connections for {project_name}.**
> **For universal multi-project master credentials, refer to `./\resources.md`.**

---

## 1. Active Services & Endpoints
- **Environment**: Local / Staging / Production
- **Local Workspace**: `{project_path}`

---

## 2. Credentials & Keys
- Refer to `.env` or project secret managers. Never commit raw production secrets to public git repositories.
"""

TODO_TEMPLATE = """# {project_title} ACTIVE IMPLEMENTATION TASK QUEUE

> **Living task backlog, milestone progress, and active work items for {project_name}.**

---

## 1. Immediate Action Items
- [ ] Review `file_map.md` and verify initial subsystem architecture.
- [ ] Configure project environment variables and local runtime.

---

## 2. Backlog & Future Milestones
- [ ] Continuous learning loops and feature integration.
"""

FILE_MAP_TEMPLATE = """# {project_title} FILE MAP & SUBSYSTEM INDEX

> **Purpose**: Direct lookup index for components, API routes, hooks, scripts, and context files.  
> **Rule**: Consult this file map first before searching or reading directory trees.

---

## 1. Primary Subsystems & Source Files

| Feature / Subsystem | Primary Source Files | Purpose & Scope |
|---|---|---|
| **Core Architecture** | Root configuration and entrypoints | Project foundation |
| **Context Directory** | `context/*.md` | Experiential memory & constraints |

---

## 2. Context Directory (`context/`)

| File | Purpose |
|---|---|
| [`file_map.md`](file:///./context/file_map.md) | Fast lookup sitemap (Read first!) |
| [`constraints.md`](file:///./context/constraints.md) | Living constraints and active non-negotiables |
| [`ideas.md`](file:///./context/ideas.md) | Chronological requirements and feature specs |
| [`mistakes.md`](file:///./context/mistakes.md) | Failure log and anti-patterns |
| [`resources.md`](file:///./context/resources.md) | Endpoints, credentials, and VM resources |
| [`todo.md`](file:///./context/todo.md) | Active task queue and milestone backlog |
| [`user_model.md`](file:///./context/user_model.md) | Dialectical user preferences |
"""

AGENTS_TEMPLATE = """# {project_title} Multi-Agent Operating Rules & Boundaries

> **Source Rules**: `.agents/rules/` & `./\.agents\\rules/`

---

## 1. Navigation Invariant (File Map First)
- Always open and read `file_map.md` (or `context/file_map.md`) first before exploring code.
- Pinpoint the exact 1-2 source files responsible for the task directly without wandering.

---

## 2. Strict Architectural Invariants
1. **Subagent Invocation Invariant**: In Antigravity runtime, NEVER use `TypeName='DeepCoder'` or `TypeName='DeepInvestigator'`. Always use `TypeName='self'` for coding and `TypeName='research'` for read-only exploration.
2. **Zero Mock Data Policy**: Never synthesize fake mock data or dummy endpoints where real upstream APIs or clean empty states are required.
3. **Cloud Free Tier Guardrails**: 0 Public IPv4 addresses, P6 64GB SSDs, Supabase 500MB DB limit, AWS Lambda compute.
4. **Mobile Ergonomics**: Interactive touch targets >= 44px (`min-h-[44px]`), zero horizontal overflow on <= 375px viewports.
5. **Proof-of-Work Verification**: Verify builds, linting, or typechecks before declaring completion.

---

## 3. Context Files Reference & Update Guide

| Context File | When to Refer (Read) | When to Update (Write) |
|---|---|---|
| **`file_map.md`** | **First on every turn/task**. Direct lookup sitemap. | Whenever new components or scripts are added. |
| **`context/constraints.md`** | **First before designing or executing**. Active rules & invariants. | When a new active requirement or boundary is established. |
| **`context/ideas.md`** | Before designing or modifying features. Chronological requirements. | Whenever a feature, plan, or requirement is finalized. |
| **`context/mistakes.md`** | When debugging or encountering errors. Past failure logs. | Automatically whenever a bug, regression, or root cause is repaired. |
| **`context/resources.md`** | Before connecting to backend services or databases. | Whenever an endpoint, IP, key, or cloud resource is modified. |
| **`context/todo.md`** | Current task queue and milestone backlog. | Whenever tasks are completed or scheduled. |
| **`context/user_model.md`** | User dialectical model and coding habits. | When user expresses new workflow preferences. |
"""

USER_MODEL_TEMPLATE = """# Dialectical User Model & Preferences

> **Living representation of user coding standards, styling choices, and operational requirements.**
> **Synchronized with Hermes Global Memory.**

---

## 1. Architectural & Engineering Standards
- **Authentic Engineering First**: Never synthesize fake mock data or dummy endpoints where real upstream APIs or empty states are needed.
- **Type Safety**: Run `npx tsc --noEmit` (or language-equivalent static analysis) before declaring tasks complete.
- **Cost Consciousness**: Strict adherence to free tier boundaries (0 Public IPv4s on Azure, 500MB DB limit on Supabase, AWS Lambda compute).

## 2. UI & Interaction Philosophy
- **Dark Glassmorphism**: `backdrop-blur-2xl`, `bg-slate-950/70`, specular borders across visual interfaces.
- **Mobile First**: All touch targets >= 44px (`min-h-[44px]`), zero horizontal overflow on <= 375px viewports.
- **Tone**: Authentic, direct, casual, and highly technical. No corporate AI fluff.

## 3. Subagent Execution Invariant
- **Rule**: NEVER invoke `TypeName='DeepCoder'` or `TypeName='DeepInvestigator'` (missing `skill_search` bug).
- **Mandated Routing**: Always use `TypeName='self'` for coding and refactoring; use `TypeName='research'` for read-only exploration.
"""

DECISIONS_TEMPLATE = """# Architectural Decision Ledger (ADR)

> **Chronological record of key technical and architectural decisions made in this project.**

---

## Ledger
| Date | Milestone / Component | Decision | Rationale |
|---|---|---|---|
| {date} | Project Initialization | Hermes Cognitive System Initialized | Autonomous experiential learning, FTS5 memory, and automated skill synthesis enabled. |
"""

LEARNINGS_TEMPLATE = """# Learned Anti-Patterns & Solutions

> **Self-updating log of bugs, edge cases, and mistakes avoided during development.**

---

- **Initialization**: Hermes learning engine activated. All past and future conversation transcripts will be distilled here.
"""

HERMES_RULE_TEMPLATE = """---
description: Hermes Autonomous Learning & Memory Invariants
trigger: always_on
---
# Hermes Autonomous Learning & Context Management Rules

1. **Persistent Memory First**:
   Before planning or designing major components, query Hermes memory to check for past solutions or user decisions:
   ```powershell
   python ./\.agents\\skills\\hermes-agent-core\\scripts\\hermes_memory.py search "<keywords>"
   ```

2. **Continuous Learning Loop**:
   When completing a major milestone or fixing a subtle bug, record the insight into local memory and Central Brain:
   ```powershell
   python ./\.agents\\skills\\hermes-agent-core\\scripts\\hermes_memory.py store --project "{project_name}" --category "architecture" --title "<summary>" --content "<details>"
   ```

3. **Automated Skill Synthesis**:
   When you establish a repeatable multi-step procedure, synthesize it into a reusable skill:
   ```powershell
   python ./\.agents\\skills\\hermes-agent-core\\scripts\\skill_synthesizer.py --name "<skill-name>" --description "<desc>" --instructions "<steps>"
   ```

4. **Context Compaction**:
   Keep project context lean and prevent token bloat:
   ```powershell
   python ./\.agents\\skills\\hermes-agent-core\\scripts\\context_compressor.py
   ```
"""

LOCAL_SKILL_TEMPLATE = """---
name: hermes-agent
description: >-
  Hermes Cognitive Engine: experiential conversational learning, dialectical user modeling,
  FTS5 persistent memory, and automated skill synthesis for {project_name}.
---

# Hermes Agent Local Interface for {project_name}

This skill provides direct access to the Hermes cognitive subsystem, linking this project with Central Brain's global memory graph and providing autonomous learning from conversation turns.

## CLI Commands Available

1. **Search Memory**:
   `python ./\.agents\\skills\\hermes-agent-core\\scripts\\hermes_memory.py search "<query>"`

2. **Save Insight**:
   `python ./\.agents\\skills\\hermes-agent-core\\scripts\\hermes_memory.py store --project "{project_name}" --category "<cat>" --title "<title>" --content "<content>"`

3. **Synthesize Skill**:
   `python ./\.agents\\skills\\hermes-agent-core\\scripts\\skill_synthesizer.py --name "<name>" --description "<desc>" --instructions "<steps>"`

4. **Compact Context**:
   `python ./\.agents\\skills\\hermes-agent-core\\scripts\\context_compressor.py`
"""


def bootstrap_project(target_dir: Path):
    target_dir = target_dir.resolve()
    project_name = target_dir.name
    import datetime
    today = datetime.date.today().strftime("%Y-%m-%d")

    print(f"==================================================")
    print(f"  Bootstrapping Hermes Cognitive Suite for:")
    print(f"  {target_dir}")
    print(f"==================================================")

    # 1. Create directory structure
    (target_dir / ".agents" / "skills" / "hermes-agent").mkdir(parents=True, exist_ok=True)
    (target_dir / ".agents" / "rules").mkdir(parents=True, exist_ok=True)
    (target_dir / "context").mkdir(parents=True, exist_ok=True)
    (target_dir / ".hermes").mkdir(parents=True, exist_ok=True)

    # 2. Initialize project memory database
    local_db = target_dir / ".hermes" / "project_memory.db"
    sys.path.append(str(HERMES_SCRIPTS_DIR))
    try:
        from hermes_memory import init_db, store_memory
        init_db(local_db)
        store_memory(
            project_name=project_name,
            category="milestone",
            title=f"Project {project_name} Hermes initialization",
            content=f"Hermes Agent cognitive architecture bootstrapped in {target_dir}.",
            tags="bootstrap,init",
            db_path=local_db
        )
    except Exception as e:
        print(f"[Warning] Failed to initialize local memory DB: {e}")

    # 3. Create full context suite if not present
    proj_title = project_name.replace("-", " ").replace("_", " ").upper()
    brain_backup_dir = BRAIN_ROOT / "projects" / project_name

    context_map = {
        "ideas.md": IDEAS_TEMPLATE.format(project_title=proj_title, project_name=project_name, date=today),
        "mistakes.md": MISTAKES_TEMPLATE.format(project_title=proj_title, project_name=project_name),
        "constraints.md": CONSTRAINTS_TEMPLATE.format(project_title=proj_title, project_name=project_name),
        "resources.md": RESOURCES_TEMPLATE.format(project_title=proj_title, project_name=project_name, project_path=str(target_dir)),
        "todo.md": TODO_TEMPLATE.format(project_title=proj_title, project_name=project_name),
        "file_map.md": FILE_MAP_TEMPLATE.format(project_title=proj_title, project_name=project_name),
        "user_model.md": USER_MODEL_TEMPLATE,
        "decisions.md": DECISIONS_TEMPLATE.format(date=today),
        "learnings.md": LEARNINGS_TEMPLATE,
    }

    for fname, tmpl in context_map.items():
        c_path = target_dir / "context" / fname
        alt_path = target_dir / fname
        backup_path = brain_backup_dir / fname

        if not c_path.exists() and not alt_path.exists():
            if backup_path.exists():
                shutil.copy2(backup_path, c_path)
                print(f"  [+] Hydrated: {c_path} (from brain/projects/ backup)")
            else:
                c_path.write_text(tmpl.strip() + "\n", encoding="utf-8")
                print(f"  [+] Created: {c_path}")

        if fname == "file_map.md":
            root_map = target_dir / "file_map.md"
            src_map = c_path if c_path.exists() else alt_path
            if src_map.exists() and not root_map.exists():
                shutil.copy2(src_map, root_map)
                print(f"  [+] Mirrored: {root_map}")

    # Ensure AGENTS.md exists at project root
    root_agents = target_dir / "AGENTS.md"
    if not root_agents.exists():
        backup_agents = brain_backup_dir / "AGENTS.md"
        if backup_agents.exists():
            shutil.copy2(backup_agents, root_agents)
            print(f"  [+] Hydrated: {root_agents} (from brain/projects/ backup)")
        else:
            root_agents.write_text(AGENTS_TEMPLATE.format(project_title=proj_title, project_name=project_name).strip() + "\n", encoding="utf-8")
            print(f"  [+] Created: {root_agents}")

    # 4. Create Hermes rule file
    rule_path = target_dir / ".agents" / "rules" / "hermes-context.md"
    rule_path.write_text(HERMES_RULE_TEMPLATE.format(project_name=project_name), encoding="utf-8")
    print(f"  [+] Created: {rule_path}")

    # 5. Create localized Hermes skill
    skill_path = target_dir / ".agents" / "skills" / "hermes-agent" / "SKILL.md"
    skill_path.write_text(LOCAL_SKILL_TEMPLATE.format(project_name=project_name), encoding="utf-8")
    print(f"  [+] Created: {skill_path}")

    # 6. Run initial context compression
    try:
        from context_compressor import compress_context
        compress_context(target_dir / "context", target_dir / "context" / "active_context.md")
    except Exception as e:
        print(f"[Warning] Initial context compression skipped: {e}")

    print(f"--------------------------------------------------")
    print(f"  Hermes Agent successfully configured in:")
    print(f"  {target_dir}")
    print(f"  • Local Memory: .hermes/project_memory.db (FTS5 active)")
    print(f"  • Rules: .agents/rules/hermes-context.md")
    print(f"  • Skill: .agents/skills/hermes-agent/SKILL.md")
    print(f"  • Context: context/user_model.md, decisions.md, learnings.md")
    print(f"==================================================")


def main():
    parser = argparse.ArgumentParser(description="Bootstrap Hermes Agent in any project")
    parser.add_argument("--project-dir", default=".", help="Root directory of target project")

    args = parser.parse_args()
    target_path = Path(args.project_dir).resolve()
    bootstrap_project(target_path)


if __name__ == "__main__":
    main()
