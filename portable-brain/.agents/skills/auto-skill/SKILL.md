---
name: auto-skill
description: "Master Skill Lifecycle Engine: Discover, select, author, evaluate, benchmark, and optimize skills across universal and project-scoped registries."
compatibility: Windows 11 PowerShell, Python 3.14+
metadata:
  version: 2.0.0
  type: orchestrator
---
# Auto-Skill: Master Skill Lifecycle & Dynamic Orchestrator

> [!IMPORTANT]
> ⛔ **EXECUTION-FIRST MANDATE (ZERO-PASSIVE-READING)**:
> Bundled scripts in `scripts/` are **executable software tools**, NOT reading material.
> When this skill is triggered, **EXECUTE the relevant script immediately** via `run_command`.
> **STRICT PROHIBITION**: NEVER call `view_file` on scripts in `scripts/` or explain their source code to the user unless explicitly ordered to edit or debug the script itself.
> Universal scripts can and must be executed from **ANY project workspace** by calling their absolute path:
> `python <BRAIN_ROOT>\.agents\skills\auto-skill\scripts\<script_name> ...`


A universal control center, dynamic registry, and creation lifecycle engine for all skills across the multi-agent system. Auto-Skill provides a categorized directory of all available capabilities, lets the user or agent select the exact skill needed for a task, authors and benchmarks new skills, and automatically synchronizes catalogs.

---

## 1. Turn-1 Autonomous Dispatch Protocol (Zero-Slash-Command Standard)

Auto-Skill operates as the implicit background router across ALL projects on Turn 1 of every user request:

1. **Autonomous Domain Evaluation**:
   The agent MUST evaluate the user prompt on Turn 1 and match the governing skill without waiting for explicit slash commands:
   * **UI / Styling / Design Systems**: Activate `ui-design-engine`.
   * **Documents / PDF / PPTX / XLSX / OCR**: Activate `document-forge`.
   * **Reasoning / Architecture / Trade-offs / RCA**: Activate `deep-thinking`.
   * **Web Search / Scraping / Documentation**: Activate `web-search-orchestrator`.
   * **Reverse Engineering / Binaries / AST**: Activate `rea`.
   * **Cloud GPUs / Modal / Colab / Video / Benchmarks**: Activate `external-resource`.
   * **Browser Automation / Headless DOM**: Activate `browser-operator`.
   * **Active Project Domains**: Activate that project's dedicated skills (e.g. `srm-*` in `project-web`, `audiophile-*` in `project-audio`, `living-npc-*` in `sample-project`, `cloud-gpu-*` in `hi`).

2. **Querying via CLI Selector**:
   If the matching skill is uncertain, execute the selector CLI with scope filtering:
   ```powershell
   # Match universal skills (safe for any project)
   python <BRAIN_ROOT>\.agents\skills\auto-skill\scripts\select_skill.py "<query>" --universal

   # Match skills scoped to the active project
   python <BRAIN_ROOT>\.agents\skills\auto-skill\scripts\select_skill.py "<query>" --project <active_project>
   ```

3. **Strict Zero-Jumble Project Scope Segregation & Subagent Injection**:
   * **Universal Skills** in `brain/.agents/skills/` are 100% permitted across all projects.
   * **Project-Specific Skills** are authorized ONLY in their own workspace (`<project>/.agents/skills/`).
   * **CRITICAL HARD BLOCK**: An agent working in Project A must NEVER load, reference, or invoke skills from Project B. Cross-project skill contamination is strictly prohibited.
   * **Subagent Skill Stripping**: Subagent invocations strip the parent's `<skills>` XML block, so parent prompts MUST explicitly pass target skill paths and CLI commands (`Model='inherit'`, `TypeName='self'`/`'research'`).
   * **No Duplicate Universal Clones in Project Folders**: Legacy universal copies in project skill folders (e.g. `hi`'s older `pdf`/`docx`/`pptx`/`xlsx`/`frontend-design` clones) are superseded by the 12 Central Brain universal skills and should be pruned/reconciled via `full-sync`.
   * Code deliverables belong strictly in `<active-project>/temp_read/`. Never drop files into `brain/` root or foreign projects.


---

## 2. Skill Authoring, Evaluation & Optimization Lifecycle

When creating, refining, or tuning skills:

### A. Intent Capture & Structure Design
1. **Define Scope**: Is this skill **Universal** (100% project-agnostic, belongs in `brain/.agents/skills/`) or **Project-Scoped** (belongs in `<project>/.agents/skills/` and archived in `brain/project_skills/<project>/`)?
   *Never place project-specific skills in Central Brain universal skills.*
2. **Standard Directory Layout**:
   - `SKILL.md`: Frontmatter (`name`, `description: "..."`), execution-first mandate, clear step-by-step instructions.
   - `references/`: Detailed guides, cheat sheets, API specifications, and architectural rules.
   - `scripts/`: Executable automation tools.

### B. Evaluation & Optimization
* Run the skill evaluation and validation suite:
  ```powershell
  python <BRAIN_ROOT>\.agents\skills\auto-skill\scripts\creator\quick_validate.py <path-to-skill>
  python <BRAIN_ROOT>\.agents\skills\auto-skill\scripts\creator\run_eval.py --help
  python <BRAIN_ROOT>\.agents\skills\auto-skill\scripts\creator\generate_report.py --help
  ```
* Test and tune trigger phrasing: Ensure descriptions avoid unquoted colons and highlight concrete user trigger phrases.

### C. Catalog Synchronization
Whenever a skill is added or modified, execute the catalog generator to register it across the system:
```powershell
python <BRAIN_ROOT>\.agents\skills\auto-skill\scripts\sync_catalog.py
```

---

## 2. Dynamic Skills Catalog

All skills currently registered and active in the system:

<!-- SKILLS-CATALOG:START -->
- **auto-skill** (`.agents/skills/auto-skill/SKILL.md`): Master Skill Lifecycle Engine: Discover, select, author, evaluate, benchmark, and optimize skills across universal and project-scoped registries.
- **browser-operator** (`.agents/skills/browser-operator/SKILL.md`): Generalized Full Browser Operation & Multi-Profile Stealth Automation Suite. Unifies Mode A (headless Playwright numeric DOM indexing), Mode B (authentic multi-profile Chrome CDP + "Browser operator" MV3 extension daemon for ANY website), and Mode C (specialized Argon/AI Studio bridges) with trusted hardware events (isTrusted:true), Shadow DOM/iframe traversal, virtualized scroll scanning, 3-tier file uploads, and 2FA/CAPTCHA circuit breaking.
- **deep-thinking** (`.agents/skills/deep-thinking/SKILL.md`): Multi-perspective deep reasoning, hypothesis branching, architectural ideation, Spark/Gemini research prompt synthesis, and cloud storage blueprinting.
- **document-forge** (`.agents/skills/document-forge/SKILL.md`): Universal document engineering powerhouse: convert, parse, edit, fill forms, calculate formulas, redline, and OCR across PDF, DOCX, PPTX, XLSX, and images. Automatically orchestrates Google Slides (gslides) for decks/PPTs and Google Docs (gdocs) for documents/PDFs.
- **exhaustive-audit-and-repair** (`.agents/skills/exhaustive-audit-and-repair/SKILL.md`): Universal Multi-Agent Code Audit & Architectural Repair System (UMACAR). Orchestrates specialized subagent squads, Requirement Traceability Matrix (RTM), git diff hunk chunking, anti-regression scanning against mistakes.md, live type/compiler verification, mobile ergonomics (under 375px), bounded arbitration, and memory synchronization.
- **external-resource** (`.agents/skills/external-resource/SKILL.md`): Orchestrate external compute, frontier AI, and model testing: Google Flow batch asset generation, Gemini Deep Research, Cloud GPU/TPU pipelines, and multi-provider model benchmarks across 55+ models.
- **full-sync** (`.agents/skills/full-sync/SKILL.md`): Universal multi-agent synchronization & context synthesis engine. Bi-directionally syncs skills between projects and brain, promotes universal context (ideas, mistakes, constraints, resources) via Markdown AST, mirrors to <VAULT_BACKUP_DIR>, and bootstraps workspaces.
- **hermes-agent-core** (`.agents/skills/hermes-agent-core/SKILL.md`): Hermes autonomous agent architecture: SQLite+FTS5 persistent memory, user modeling, skill synthesis, and context compaction. Use for memory recall.
- **internal-tools** (`.agents/skills/internal-tools/SKILL.md`): Universal Internal Tooling Powerhouse: Build and orchestrate MCP servers (FastMCP/TypeScript), native Antigravity SDK tool schemas and subagent capabilities, Manifest V3 Chrome Extensions, and author standardized skills.
- **rea** (`.agents/skills/rea/SKILL.md`): Reverse Engineer Anything (REA): Deep binary disassembly, decompilation, Electron/JS deobfuscation, Android APKs, .NET assemblies, WASM, and live runtime observation using the REA engine.
- **ui-design-engine** (`.agents/skills/ui-design-engine/SKILL.md`): Universal frontend design engine & quality orchestrator: dynamic archetype router, 15-point anti-slop verification, dark glassmorphism tokens, and component scaffolders.
- **web-search-orchestrator** (`.agents/skills/web-search-orchestrator/SKILL.md`): Multi-tier web search, scraping, and deep research engine integrating TinyFish, Tavily, Firecrawl, subagent isolation, and Gemini Deep Research. Use whenever live web search, documentation fetching, or deep research is required.
<!-- SKILLS-CATALOG:END -->

---

## 3. Automated Registration of New Skills (Zero-Maintenance Invariant)

Whenever an agent or user creates a new skill (via `/skill-creator`, `skill_distillation_engine.py`, or manual creation):

1. **Determine Skill Scope & Target Path**:
   - **🌐 Universal Skill** (100% project-agnostic, usable anywhere):
     Place the new skill in `<BRAIN_ROOT>\.agents\skills/<new-skill-name>/` with a valid `SKILL.md`.
   - **🔒 Project-Specific Skill** (tied to a specific project, API, or domain):
     - **Primary Location**: Place directly in the project's own workspace: `<project-root>\.agents\skills\<new-skill-name>/`.
     - **Mandatory Archival Backup**: Copy the entire skill directory to `<BRAIN_ROOT>\project_skills\<project-name>\<new-skill-name>/`.
     - **STRICT PROHIBITION**: NEVER place project-specific skills in `<BRAIN_ROOT>\.agents\skills/`. Doing so causes runtime prompt bloat across all active projects.

2. **Execute the Auto-Skill Synchronizer**:
   ```powershell
   python <BRAIN_ROOT>\.agents\skills\auto-skill\scripts\sync_catalog.py
   ```

3. **What happens automatically**:
   - `sync_catalog.py` extracts YAML frontmatter (`name`, `description`, `category`).
   - Tags each skill with its scope badge (`🌐 Universal` vs `🔒 Project: <name>`).
   - Updates `references/skill_registry.json` and `references/catalog.md`.
   - Patches the `SKILLS-CATALOG` table in this `SKILL.md`.
   - Mirrors universal skills to `<VAULT_BACKUP_DIR>\skills\` and project skills to `<VAULT_BACKUP_DIR>\project_skills\<project-name>\`.

No manual catalog editing is ever required.


---

## 4. Bundled Utilities

| Script | Purpose | Command |
|---|---|---|
| **`select_skill.py`** | Interactive CLI search & selector | `python .../select_skill.py [query]` |
| **`sync_catalog.py`** | Scans, indexes, and regenerates registry & mirrors | `python .../sync_catalog.py` |
| **`skill_registry.json`** | Machine-readable JSON index of all skills | Located in `references/skill_registry.json` |
| **`catalog.md`** | Clean standalone markdown reference table | Located in `references/catalog.md` |