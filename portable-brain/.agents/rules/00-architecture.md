---
description: >-
  Universal multi-agent architecture, operating invariants, and project routing constraints across all workspaces.
  Read this before designing, executing, or navigating any project codebase.
trigger: always_on
---
# UNIVERSAL MULTI-AGENT ARCHITECTURE & SYSTEM INVARIANTS

## 1. Project Routing & File Map First Standard
- **Master Routing Directory (`brain/project_map.md`)**: On every session or task, always consult `<BRAIN_ROOT>\project_map.md` first to determine which project workspace is targeted.
- **Strict Project Independence (Zero Wandering)**: Each project (`project-web`, `PJCT/hi`, `PJCT/sample-project`, `appwrite/project-audio`, `PJCT/sample-project`) is self-contained. **NEVER inspect or read `project-web/context/` when working on another project.**
- **Project File Map First**: Always open and read that project's own `file_map.md` to locate the exact 1-2 source files needed. Never wander or blindly list whole directories.
- **Dedicated Project Context**: Project-specific architecture plans, opencode instructions, todo lists, and logs live strictly within that project's `context/` directory (and are mirrored to `brain/projects/<project>/`).

## 2. Central Brain Cleanliness & Anti-Wipe Standard
- `<BRAIN_ROOT>` is the permanent multi-project intelligence core.
- **Zero Project Files in Brain Root**: NEVER place single-project files (e.g. `todo.md`, `opencode_instructions.md`, `architecture_plan.md`, `cloud-infrastructure-log.md`) into `brain/` root. Brain root contains ONLY universal multi-project files (`AGENTS.md`, `project_map.md`, `file_map.md`, `constraints.md`, `ideas.md`, `mistakes.md`, `resources.md`, `projects.md`, `slop.md`, `model_benchmarks.md`).
- **Strict Anti-Wipe Rule**: Never overwrite or delete files in `brain/` with single-project data. When adding cross-project insights, always read first, merge, and append with project-scoped headers. All modifications must be tracked in Git.

## 3. Universal vs Project-Specific Skills Segregation
- **Universal Skills Only in Brain Root**: `<BRAIN_ROOT>\.agents\skills/` is strictly reserved for 100% project-agnostic skills (`auto-skill`, `browser-operator`, `deep-thinking`, `document-forge`, `exhaustive-audit-and-repair`, `external-resource`, `full-sync`, `hermes-agent-core`, `internal-tools`, `rea`, `ui-design-engine`, `web-search-orchestrator`). Exactly 12 consolidated powerhouses.
- **Strict Prohibition on Project Skills in General Skills**: NEVER add project-specific skills (e.g., `srm-*`, `audiophile-*`, `appwrite-*`, `living-npc-*`, `cloud-gpu-*`) to `brain/.agents/skills/`. Because `brain` is an active workspace root, putting them here causes them to leak into all agent prompts across every project.
- **Local Project Placement**: Project-specific skills must be created and stored directly in the target project's own `.agents/skills/<skill-name>/` directory (e.g., `project-web/.agents/skills/`, `PJCT/sample-project/.agents/skills/`).
- **Central Brain Backup (`project_skills/<project>/`)**: A backup copy of every project-specific skill must be preserved in `<BRAIN_ROOT>\project_skills/<project-name>/<skill-name>/`.

## 4. Subagent Architecture & Mandatory Delegation Mandate
- **Defective Subagents (1s Crash Root Cause)**: In Antigravity's runtime (`language_server.exe`), built-in subagents `DeepCoder` and `DeepInvestigator` fail initialization immediately due to missing tool `skill_search` (`failed to construct executor: unknown component: tool "skill_search" not found in registry`) and terminate after 1 second ("Worked for 1s").
- **Strict Invariant**: NEVER invoke `TypeName='DeepCoder'` or `TypeName='DeepInvestigator'`, regardless of slash commands (`/boost`, `/goal`).
- **MANDATORY SUBAGENT UTILIZATION (ZERO SUBAGENT AVOIDANCE)**:
  - Do NOT avoid subagents! Subagents are 100% operational and critical for avoiding single-session context degradation.
  - **`TypeName='self'`**: For coding, refactoring, bug fixes, cognitive reasoning, and multi-step engineering. Inherits all tools (file write, replace, bash/PowerShell, MCP) and model context without the broken `skill_search` bug.
  - **`TypeName='research'`**: For read-only exploration, repository analysis, and web lookup.
  - **Dynamic Subagents**: Custom defined subagents via `define_subagent` (with `enable_write_tools=true` and `enable_mcp_tools=true`).
  - Solo routine is restricted strictly to simple 1-line queries. All complex, multi-part, or exploratory tasks MUST be delegated to subagents.

## 5. Cloud Cost & 100% Free-Tier Guardrails
- **Azure PostgreSQL Flexible Server**: Hosts relational data and vector stores (100% Free Tier: `Standard_B1ms` + 32GB free storage).
- **Azure VMs**: Operate with **0 Public IPv4 addresses** via persistent Cloudflare Tunnels (Zero Public IP charges). Disks must use P6 64GB SSDs or lower.
- **Supabase**: Restricted strictly to User Auth and lightweight preferences (500MB DB Limit). Never store rich-text ASTs or binaries in Supabase.
- **Cloudflare R2**: Primary object storage for bulk documents, media, audio, and backups (10 GB Free Tier, $0 Egress).
- **AWS Compute**: Restricted strictly to **AWS Lambda** (1,000,000 requests/mo free). No paid EC2/RDS in primary AWS account.
- **GPU Credit Zero-Waste Rule**: Cloud GPU notebooks (Modal, Colab, Kaggle) must NEVER be launched until all caller scripts and generation targets are 100% written, syntax-checked, and pre-verified.

## 6. Zero-Mock & Honest Data Policy
- Never synthesize fake mock data, mock API responses, or placeholder profiles when upstream services encounter errors.
- Always implement authentic upstream error handling, actionable user feedback, and graceful empty states.

## 7. Mobile Ergonomics & Dark Glassmorphism Standard
- Interactive touch targets must evaluate to >= 44px (`min-h-[44px]`).
- Zero horizontal overflow on mobile viewports (<= 375px).
- Premium dark glassmorphism (`backdrop-blur-2xl`, specular borders, subtle radial glows) across all projects.
- Authentic, conversational user tone (zero AI slop, zero robotic marketing fluff).

## 8. Proof-of-Work Verification Standard
- NEVER proclaim a task complete without executing live verification:
  - Run type checks (`npx tsc --noEmit` or `tsc -b`).
  - Run syntax validation (`python -m py_compile`, `node --check`).
  - Verify server listening ports, health endpoints, and build validity.
  - Confirm actual CI/CD or runtime status before informing the user.

## 9. Subagent Search & Multi-Tier Research Invariant
- **Zero Search Neglect**: Never guess or speculate on external APIs, SDK methods, breaking changes, or documentation.
- **Zero Native Search Defaulting on Deep Queries**: When the user requests a **"deep search"**, **"deep research"**, **"comprehensive comparison"**, or **"exhaustive dossier"**, agents **MUST NEVER** default to the native `search_web` tool. Native `search_web` is permitted strictly for 1-hop trivial fact checks.
- **Search Escalation & Autonomous Routing Protocol**:
  - **Class A: Frontier Deep Research**: Triggered by *"deep search"*, *"deep research"*, *"argon research"*, *"exhaustive comparison"*, or complex multi-source landscape. MUST execute **Argon Deep Research** via `python <BRAIN_ROOT>\.agents\skills\web-search-orchestrator\scripts\search_engine.py deep-search "<topic>" -o temp_read/<name>.md`. Dynamically auto-negotiates the optimal IDLE profile from the 6 shared Google One AI Premium accounts, auto-confirms research plan, harvests structured Markdown + citations, and purges sidebar chats.
  - **Class B: Multi-Engine Technical Search**: Triggered by documentation lookups, bug searches, library APIs, and framework migrations. MUST spawn a dedicated search subagent (`TypeName='self'`) that executes `python <BRAIN_ROOT>\.agents\skills\web-search-orchestrator\scripts\search_engine.py search "<query>" --engine parallel` (Tavily AI + Firecrawl JS + TinyFish concurrently) and fetches pages via `search_engine.py fetch`. Subagent returns ONLY a concise, high-density 1-page technical briefing to the parent chat.
  - **Class C: Trivial 1-Hop Fact Check**: Single factual verification (<10 words, single factual number). Native `search_web` is permitted (1 call max; never loop).
- **Subagent Search Isolation**: Multi-query searches, documentation crawls, and raw web fetches MUST NEVER be dumped into the parent chat. All deep research dossiers belong strictly in `<active-project>/temp_read/`.

## 10. Hermes Cognitive Context & Pre-Compaction Memory Flush
- **Two-Phase Compaction Protocol**: Unbounded conversation history causes token degradation. Before context pruning or when concluding major architectural milestones, execute `session_flush.py` to flush decisions into `ideas.md`, anti-patterns into `mistakes.md`, and structured records into `~/.gemini/antigravity/hermes_global_memory.db`.
- **Turn-1 Rapid Memory Recall**: On complex tasks, query past episodic memories via SQLite FTS5 BM25 search (`hermes_recall.py search "<query>"`) before guessing or re-asking known user preferences.

## 11. Bounded Multi-Agent Arbitration & Zero-Vision Browser Operations
- **Turn Arbitration Caps**: When orchestrating subagent squads, enforce a hard limit of **3 serial deliberation rounds** and a maximum of **10 messages per turn** to strictly prevent runaway conversation loops.
- **Sub-Second Browser Operations (`browser-operator`)**: For web automation and scraping, subagents must use numeric DOM indexing (`[id] role: label`) rather than passing raw multi-modal screenshots, achieving sub-second execution with zero vision token waste.

## 12. Code Output & Project Delivery Invariant (temp_read Delivery Standard)
- **Zero Raw Code Clogging in Chat**: NEVER dump large multi-file code blocks or extensive scripts directly in conversational text responses. Dumping full files clogs the conversation context, wastes visual space, and accelerates token limits.
- **Mandatory `temp_read/` in the ACTIVE Workspace**: Whenever generating or delivering code files, runnable scripts, or notebooks, ALWAYS place them directly into the **active workspace's** `<active-project-root>/temp_read/` subfolder (e.g. `brain/temp_read/` when working in central brain, `project-web/temp_read/` when working in project-web).
- **Referenced Workspaces are 100% Read-Only**: When asked to "refer to" another project (e.g. `PJCT/hi`), that project is strictly read-only. **NEVER write or drop ANY files into the referenced project's directory** (not even in a `temp_read/` inside the referenced project). All generated output belongs exclusively in the *current active project's* `temp_read/`.
- **Concise Chat Response**: In the conversational response, provide only a high-level summary, the exact file paths within `/temp_read/`, and concise instructions or execution commands, keeping the chat clean and readable.

## 13. Skill Menu Bloat & Plugin Lifecycle Architecture
- **Multi-Root Skill Discovery**: Antigravity registers skills across 4 discovery layers: builtin skills, installed marketplace plugins (`~/.gemini/config/plugins/`), global config skills (`~/.gemini/config/skills/`), and active workspace skills (`.agents/skills/`).
- **The Plugin Bloat Pattern**: Installing plugins like `data-agent-kit-plugin` injects 37+ specialized skills into the system prompt, causing prompt pollution during non-GCP workflows.
- **Branching Hub Architecture (Progressive Disclosure)**: Consolidate scattered capabilities into unified universal powerhouses (`document-forge`, `ui-design-engine`, `deep-thinking`, `auto-skill`) rather than sprawling arrays of micro-skills.
- **Dynamic Plugin Lifecycle Control**: Non-essential plugins can be toggled via Language Server RPC:
  `source /tmp/lsrpc.sh && lsrpc JetboxWriteState '{"userConfig":{"plugins":{"<dir>":{"enabled":false}}}}'`
  or in `~/.gemini/config/config.json`. Disabling `data-agent-kit-plugin` instantly clears 37 skills from the menu and prompt context while keeping scripts readily callable.

## 14. Autonomous Turn-1 Auto-Skill Routing & Zero-Jumble Project Isolation Standard
- **The Turn-1 Mandate**: On EVERY user prompt or task across ALL projects, the agent must autonomously evaluate which skill governs the task domain BEFORE proposing plans, writing code, or running tools. Never wait for the user to type `/auto-skill` or slash commands.
- **Autonomous Domain Dispatch Matrix**:
  - **UI / Frontend / Styling / CSS / Glassmorphism**: Activate `ui-design-engine`.
  - **Documents / PDF / PPTX / Word / Excel / OCR**: Activate `document-forge`.
  - **Reasoning / Architecture / Trade-offs / Planning / RCA**: Activate `deep-thinking`.
  - **Web Search / Scraping / Documentation Discovery**: Activate `web-search-orchestrator`.
  - **Binary Analysis / Disassembly / AST Deobfuscation / RE**: Activate `rea`.
  - **Cloud GPUs / Modal / Colab / Video Gen / Benchmarks**: Activate `external-resource`.
  - **Browser Automation / Headless Navigation**: Activate `browser-operator`.
  - **Active Project Domain Tasks**: Activate that project's dedicated skills (e.g. University-Portal portals $\rightarrow$ `portal-engineer-example`; audio DSP $\rightarrow$ `audiophile-audio-engine`; living NPCs $\rightarrow$ `living-npc-and-causality-architect`).
- **Strict Zero-Jumble Project Scope Segregation (Anti-Contamination Invariant)**:
  - Because `brain` is permanently attached alongside the active project folder, universal skills from `brain/.agents/skills/` are 100% authorized for all projects.
  - Project-specific skills are authorized **ONLY** within their designated active workspace.
  - **CRITICAL HARD BLOCK**: An agent working in Project A must NEVER load, reference, or invoke skills belonging to Project B (e.g. no University-Portal skills in `hi`, no audiophile skills in `sample-project`, no NPC skills in `project-web`).
  - All code outputs, test scripts, and notebooks belong strictly in `<active-project>/temp_read/`. Never write single-project files into `brain/` root or foreign projects.

15. **Execution-First Mandate & Shared Fleet Observability for Argon Brain**:
    - **Zero Script Reading**: Subagents and agents MUST NEVER call `read_file` or `view_file` on `consult_argon.py` or `gemini_brain_driver.py`. Always execute them directly via `run_command`.
    - **Zero Intermediate Wrapper Scripts**: ?? **STRICT PROHIBITION**: NEVER create temporary Python wrapper scripts (e.g. `run_argon_query.py`, `query_argon.py`) or waste turns checking CLI `--help`. Execute `consult_argon.py` directly on Turn 1!
      - Normal prompt: `python <BRAIN_ROOT>\.agents\skills\deep-thinking\scripts\consult_argon.py "<prompt>" -o temp_read/ans.md`
      - Multi-line prompt: `python <BRAIN_ROOT>\.agents\skills\deep-thinking\scripts\consult_argon.py --prompt-file temp_read/prompt.md -o temp_read/ans.md`
      - Deep research: `python <BRAIN_ROOT>\.agents\skills\deep-thinking\scripts\consult_argon.py "<topic>" --deep-research -o temp_read/research.md`
    - **2-Tier Argon Hybrid Routing Policy (`--api` Failover)**: Always use Tier 1 ($0-token Browser Bridge via `consult_argon.py` across the 6 Google One AI Premium accounts) by default, attaching context files via `-f`. Route to Tier 2 (`consult_argon.py --api` / `<WORKSPACE_ROOT>\api_router\argon.py` on Google Cloud Vertex AI) **ONLY** if all 6 browser accounts have hit their 5-hour quota limit OR when the user explicitly requests to use the Argon API.
    - **Shared Fleet & Dynamic Observability**:
      - All 6 Google One AI Premium profiles (Profile 14, 13, 16, 7, 8, 9) form a shared compute pool across all projects?never artificially hardcoded to specific projects.
      - Any agent can inspect live fleet status (`consult_argon.py --status`) to see which profiles are IDLE vs BUSY and their usage %, and decide which profile to select.
      - If an agent does not specify `--profile`, the system auto-selects the optimal idle profile with the lowest usage.
    - **Pre-Send Model Gate**: The driver strictly confirms `button.input-area-switch` displays Argon + High Thinking before prompt dispatch, aborting send if unverified (never defaults to Flash).
    - **Single-Tab Low-RAM Invariant**: Exactly 1 active tab per profile window to prevent host out-of-memory crashes (~3GB free RAM).
    - **Mandatory Sidebar Chat Purge**: All automated query runs default to `clean=True`. Upon delivering output to `temp_read/`, the driver automatically deletes the ephemeral conversation from the sidebar (Row -> 3-dots -> Delete -> Confirm modal), keeping user accounts pristine. Pass `--no-clean` only when debugging.
    - **Live Quota Observability**: Driver audits and reports live 5-hour quota and weekly quota limits before releasing leases, ensuring transparent fleet telemetry.
    - **Quill Editor Chip Preservation**: Prompt injection isolates text replacement to child `<p>` nodes, strictly preserving the `[ ⚛ Deep research ]` pill chip and file chips from destructive `selectAll` wiping.
