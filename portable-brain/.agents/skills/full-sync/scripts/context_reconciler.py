#!/usr/bin/env python3
"""
Context Reconciler: Safe Two-Way Context Sync between Project Workspace and Central Brain
Conforms strictly to Central Brain Preservation & Cleanliness Rules.
- Scaffolds complete standard context suite (ideas.md, mistakes.md, constraints.md, resources.md,
  todo.md, file_map.md, user_model.md, AGENTS.md) if missing.
- Hydrates from historical brain/projects/<project>/ backups if available.
- Universal brain memory (mistakes.md, ideas.md) merges and appends.
- Universal constraints (constraints.md) are protected from project-specific contamination.
- Project-specific context files are archived strictly into brain/projects/<project_name>/
  and NEVER written to brain root.
"""

import datetime
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

BRAIN_ROOT = Path(r"./")

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
> **For universal multi-project master credentials, refer to `./resources.md`.**

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

AGENTS_TEMPLATE = """# {project_title} Multi-Agent Operating Rules & Boundaries

> **Source Rules**: `.agents/rules/` & `./.agents/rules/`

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


class ContextReconciler:
    def __init__(self, project_path: Path, brain_path: Path = BRAIN_ROOT):
        self.project_path = project_path.resolve()
        self.brain_path = brain_path.resolve()
        self.project_name = self.project_path.name
        self.project_title = self.project_name.replace("-", " ").replace("_", " ").upper()
        self.brain_project_dir = self.brain_path / "projects" / self.project_name
        self.brain_project_dir.mkdir(parents=True, exist_ok=True)
        self.context_dir = self.project_path / "context"

    def locate_context_dir(self, root: Path) -> Path:
        cand = root / "context"
        cand.mkdir(parents=True, exist_ok=True)
        return cand

    def ensure_all_context_files(self) -> List[str]:
        """
        Guarantees that the complete standard context suite exists for the project:
        ideas.md, mistakes.md, constraints.md, resources.md, todo.md, file_map.md, user_model.md, AGENTS.md.
        If a file is missing in the project:
          1. Hydrate from historical brain/projects/<project>/ backup if available.
          2. Otherwise, scaffold from project-tailored template.
        """
        logs = []
        c_dir = self.locate_context_dir(self.project_path)
        today = datetime.date.today().strftime("%Y-%m-%d")

        template_map = {
            "ideas.md": IDEAS_TEMPLATE.format(project_title=self.project_title, project_name=self.project_name, date=today),
            "mistakes.md": MISTAKES_TEMPLATE.format(project_title=self.project_title, project_name=self.project_name),
            "constraints.md": CONSTRAINTS_TEMPLATE.format(project_title=self.project_title, project_name=self.project_name),
            "resources.md": RESOURCES_TEMPLATE.format(project_title=self.project_title, project_name=self.project_name, project_path=str(self.project_path)),
            "todo.md": TODO_TEMPLATE.format(project_title=self.project_title, project_name=self.project_name),
            "file_map.md": FILE_MAP_TEMPLATE.format(project_title=self.project_title, project_name=self.project_name),
            "user_model.md": USER_MODEL_TEMPLATE,
        }

        for filename, template_content in template_map.items():
            proj_file = c_dir / filename
            alt_proj_file = self.project_path / filename
            brain_backup = self.brain_project_dir / filename

            if not proj_file.exists() and not alt_proj_file.exists():
                if brain_backup.exists():
                    shutil.copy2(brain_backup, proj_file)
                    logs.append(f"Hydrated {filename} from brain/projects/{self.project_name}/ backup.")
                else:
                    proj_file.write_text(template_content.strip() + "\n", encoding="utf-8")
                    logs.append(f"Scaffolded new standard {filename} in {self.project_name}/context/.")

            # Ensure file_map.md is also mirrored at project root for instant access
            if filename == "file_map.md":
                root_map = self.project_path / "file_map.md"
                src_map = proj_file if proj_file.exists() else alt_proj_file
                if src_map.exists() and not root_map.exists():
                    shutil.copy2(src_map, root_map)
                    logs.append(f"Mirrored file_map.md to project root.")

        # Ensure AGENTS.md is present at project root
        root_agents = self.project_path / "AGENTS.md"
        if not root_agents.exists():
            brain_agents = self.brain_project_dir / "AGENTS.md"
            if brain_agents.exists():
                shutil.copy2(brain_agents, root_agents)
                logs.append("Hydrated AGENTS.md from brain/projects/ backup.")
            else:
                agents_content = AGENTS_TEMPLATE.format(project_title=self.project_title, project_name=self.project_name)
                root_agents.write_text(agents_content.strip() + "\n", encoding="utf-8")
                logs.append("Scaffolded new AGENTS.md at project root.")

        return logs

    def reconcile_experiential_file(self, filename: str) -> Tuple[bool, str]:
        """Safely merge project mistakes or ideas into Central Brain permanent memory."""
        c_dir = self.locate_context_dir(self.project_path)
        proj_file = c_dir / filename
        if not proj_file.exists():
            proj_file = self.project_path / filename
        if not proj_file.exists():
            return False, f"{filename} not found in {self.project_name}."

        brain_file = self.brain_path / filename
        if not brain_file.exists():
            return False, f"Universal {filename} not found in brain root."

        proj_content = proj_file.read_text(encoding="utf-8", errors="replace")
        brain_content = brain_file.read_text(encoding="utf-8", errors="replace")

        new_entries = []
        for line in proj_content.splitlines():
            sline = line.strip()
            if sline.startswith("- [") or sline.startswith("- **") or sline.startswith("### "):
                clean_sig = sline[:60]
                if clean_sig not in brain_content and not clean_sig.startswith("- [INIT]"):
                    new_entries.append(line)

        if new_entries:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            merge_block = f"\n\n## [{self.project_name.upper()} Synced: {timestamp}]\n" + "\n".join(new_entries)
            brain_file.write_text(brain_content + merge_block, encoding="utf-8")
            return True, f"Merged {len(new_entries)} new entries from {self.project_name} into Brain {filename}."

        return False, f"{filename} entries already present in Brain."

    def sync_file_map(self) -> Tuple[bool, str]:
        """Ensure file_map.md is present in project and archived in brain/projects/<project>/."""
        proj_map = self.project_path / "file_map.md"
        context_map = self.project_path / "context" / "file_map.md"
        brain_proj_map = self.brain_project_dir / "file_map.md"

        source_map = None
        if proj_map.exists():
            source_map = proj_map
        elif context_map.exists():
            source_map = context_map
        elif brain_proj_map.exists():
            source_map = brain_proj_map

        if not source_map:
            return False, f"No file_map.md found for {self.project_name}."

        shutil.copy2(source_map, brain_proj_map)
        if not proj_map.exists():
            shutil.copy2(source_map, proj_map)
        if (self.project_path / "context").exists() and not context_map.exists():
            shutil.copy2(source_map, context_map)

        return True, f"Synchronized file_map.md for {self.project_name}."

    def archive_project_context_files(self) -> List[str]:
        """
        Archive all project-specific files (todo.md, opencode_instructions.md, etc.)
        strictly into brain/projects/<project_name>/ and NEVER into brain root!
        """
        c_dir = self.locate_context_dir(self.project_path)
        archived = []
        for item in c_dir.iterdir():
            if item.is_file() and item.suffix in (".md", ".json", ".txt"):
                dst = self.brain_project_dir / item.name
                shutil.copy2(item, dst)
                archived.append(item.name)

        root_todo = self.project_path / "todo.md"
        if root_todo.exists():
            shutil.copy2(root_todo, self.brain_project_dir / "todo.md")
            archived.append("todo.md (from root)")

        root_agents = self.project_path / "AGENTS.md"
        if root_agents.exists():
            shutil.copy2(root_agents, self.brain_project_dir / "AGENTS.md")
            archived.append("AGENTS.md (from root)")

        root_map = self.project_path / "file_map.md"
        if root_map.exists():
            shutil.copy2(root_map, self.brain_project_dir / "file_map.md")
            archived.append("file_map.md (from root)")

        return [f"Archived {len(archived)} project files to brain/projects/{self.project_name}/: {', '.join(archived)}"]

    def reconcile_all(self) -> List[str]:
        logs = []

        # 1. Ensure all standard context files exist (or scaffold/hydrate them)
        scaffold_logs = self.ensure_all_context_files()
        for sl in scaffold_logs:
            logs.append(f"[+] {sl}")

        # 2. Sync file_map.md
        status, msg = self.sync_file_map()
        logs.append(f"[+] {msg}" if status else f"[-] {msg}")

        # 3. Merge experiential memory
        for exp_file in ["mistakes.md", "ideas.md"]:
            status, msg = self.reconcile_experiential_file(exp_file)
            logs.append(f"[+] {msg}" if status else f"[-] {msg}")

        # 4. Archive project-specific files to brain/projects/<project>/
        archive_logs = self.archive_project_context_files()
        for al in archive_logs:
            logs.append(f"[+] {al}")

        return logs
