# Central Multi-Agent System Architecture & Operating Rules

> **Master Operating Guide for Antigravity, OpenCode, and Subagent Sessions across ALL Projects**  
> **Source Rules**: `<BRAIN_ROOT>\.agents\rules\` & `.agents/rules/`

---

## 1. Agent Boundaries & Responsibilities

| Agent | Core Responsibilities | Boundaries & Constraints |
|---|---|---|
| **Antigravity** | • Lead Frontend Architect & QA Engineer across all projects.<br>• Next.js App Router, React Flow visualizers, TipTap document editor, Tailwind dark glassmorphism, Web Audio DSP, Canvas/WebGL2 engines.<br>• E2E testing, deployment management via GitHub Actions, runtime debugging.<br>• Manages central context files, rules, and model benchmarks. | Never write heavy Python infrastructure scripts or large background workers. |
| **OpenCode** | • Master Backend Architect & Database Engineer.<br>• Azure PostgreSQL schemas, Upstash Redis background workers (`vm2_worker.py`), Python ingestion scripts (`run-ingestion.sh`), Appwrite serverless functions.<br>• High-concurrency async services. | Always read `context/opencode_instructions.md` and database boundaries before modifying backend schemas. |
| **Google Spark** | • Cloud research & mathematical/algorithm reasoning.<br>• Evaluates LLM benchmarks, tokenizer performance, and architectural trade-offs. | No local filesystem access. Antigravity formulates self-contained prompts. |

---

## 2. Universal Non-Negotiable Rules

1. **CENTRAL BRAIN PRESERVATION (STRICT ANTI-WIPE RULE)**:
   - `<BRAIN_ROOT>` is the permanent multi-project intelligence core.
   - **NEVER OVERWRITE OR WIPE** any file in `/brain` with single-project data using destructive write tools (`Overwrite=true`).
   - **ALWAYS MERGE & APPEND**: When adding notes for a project (e.g. sample-project, sample-project, project-web), read the existing file first and add/update project-specific subsections.
   - **GIT TRACKING**: All modifications to `/brain` must be committed to Git.

2. **Cloud Cost & Resource Guardrails**:
   - **Azure PostgreSQL Flexible Server**: Hosts `srm_cards`, `srm_student_profiles`, pgvector RAG, and prompt cache (100% Free Tier: `Standard_B1ms`).
   - **Supabase**: Primary database for User Auth and lightweight preferences (500MB DB Limit). Never store rich-text ASTs or binaries in Supabase.
   - **Cloudflare R2**: Primary storage for bulk documents, PDFs, audio files, and media (10 GB Free Tier, $0 Egress).
   - **Zero Azure Public IPs**: VMs operate with **0 Public IPv4 addresses** via persistent **Cloudflare Tunnels**.
   - **AWS Compute in project-web**: Restricted strictly to **AWS Lambda** (1M req/mo free). No paid EC2/RDS in primary AWS account.
   - **GPU Credit Zero-Waste**: Cloud GPU notebooks (Modal/Colab) must NEVER be started until ALL caller scripts and generation targets are 100% written, syntax-checked, and pre-verified.

3. **Mineserver Immutable World Snapshots**:
   - Files in `ver_backup/` are **IMMUTABLE historical snapshots**.
   - **NEVER MODIFY, OVERWRITE, OR REVERT** any file in `ver_backup/`.
   - Automated shutdown routines must run `save-all flush` with `save-on` enabled and save exclusively to `latest_world/`.

4. **UI & Navigation Standard**:
   - Dark glassmorphism (`backdrop-blur-2xl`, `bg-slate-950/70`, specular borders) across all visual themes.
   - Mobile touch targets $\ge 44\text{px}$ (`min-h-[44px]`), zero horizontal overflow on $\le 375\text{px}$ viewports.
   - Authentic casual tone (no corporate AI slop, no cheesy robotic greetings).

5. **Autonomous Tool & MCP Execution Policy**:
   - The agent has full, pre-approved authorization to execute all tools and MCP tools autonomously without asking for confirmation.
   - Never ask the user for permission before running tools or inspect commands.

6. **Subagent Architecture & Mandatory Delegation Mandate**:
   - **Root Cause of Past 1s Crash**: Antigravity's internal build (`language_server.exe`) fails when spawning `DeepCoder` or `DeepInvestigator` due to a missing component error (`unknown component: tool "skill_search" not found in registry`), causing immediate failure after 1s ("Worked for 1s").
   - **STRICT PROHIBITION**: NEVER invoke `TypeName='DeepCoder'` or `TypeName='DeepInvestigator'`, even if `/boost` prompt text requests it.
   - **ACTIVE SUBAGENT UTILIZATION MANDATE (ZERO SUBAGENT AVOIDANCE)**:
     - Agents **MUST NOT avoid subagents** out of fear of crashes! Subagents are fully supported and operational via `TypeName='self'` and `TypeName='research'`.
     - **For Coding, Refactoring, & Complex Multi-Step Tasks**: ALWAYS spawn `TypeName='self'`. `self` inherits the full environment, tool capabilities (file write, replace, bash/PowerShell, MCP servers), and model context without the broken `skill_search` dependency.
     - **For Read-Only Exploration, Web Research, & Code Audits**: ALWAYS spawn `TypeName='research'`.
     - **For Custom Workflows**: Define subagents dynamically via `define_subagent(name="...", system_prompt="...", enable_write_tools=True, enable_mcp_tools=True)` and invoke them by name.
     - **When to Delegate**: Solo execution is permitted ONLY for trivial 1-line queries. For multi-part tasks, deep research, cognitive ideation, or parallel audits, ALWAYS delegate to subagents.

12. **Skill Menu Bloat & Plugin Management Architecture**:
    - **Multi-Root Discovery Context**: Antigravity discovers skills across 4 tiers: builtins (`builtin/skills`), marketplace plugins (`~/.gemini/config/plugins/`), global config (`~/.gemini/config/skills/`), and workspace root (`.agents/skills/`).
    - **The Plugin Bloat Root Cause**: Installing third-party plugins (e.g. `data-agent-kit-plugin`) adds 37+ specialized skills into the system prompt, causing context bloat during non-GCP tasks.
    - **Branching Hub Architecture (Progressive Disclosure)**: Consolidate scattered micro-skills into single universal powerhouses in Central Brain (`document-forge` for all doc/slides/sheets/OCR, `ui-design-engine` for all UI archetypes & anti-slop rules, `deep-thinking` for all reasoning/brainstorming/MCDA, `auto-skill` for dynamic registry).
    - **Plugin Lifecycle Control**: Non-critical plugins can be toggled via Language Server RPC:
      `source /tmp/lsrpc.sh && lsrpc JetboxWriteState '{"userConfig":{"plugins":{"<dir>":{"enabled":false}}}}'`
      or in `~/.gemini/config/config.json`. Disabling `data-agent-kit-plugin` immediately cleans 37 skills from the menu while preserving project readiness.

7. **Universal vs Project-Specific Skills Segregation & Archival Invariant**:
   - **Universal Skills Only in Brain**: `<BRAIN_ROOT>\.agents\skills/` is strictly reserved for 100% project-agnostic skills (`auto-skill`, `browser-operator`, `deep-thinking`, `document-forge`, `exhaustive-audit-and-repair`, `external-resource`, `full-sync`, `hermes-agent-core`, `internal-tools`, `rea`, `ui-design-engine`, `web-search-orchestrator`). Exactly 12 consolidated powerhouses.
   - **Strict Prohibition on Project Skills in General/Brain Skills**: NEVER add project-specific skills (e.g. `srm-*`, portal tools, game narratives/NPCs, project backends like `appwrite-*`, `cloud-gpu-*`) to `brain/.agents/skills/`. Because `brain` is an active workspace root, putting them here causes them to leak into all agent prompts across every project.
   - **Local Project Placement**: Project-specific skills must be created and stored directly in the target project's own `.agents/skills/<skill-name>/` directory (e.g. `project-web/.agents/skills/`, `PJCT/sample-project/.agents/skills/`).
   - **Central Brain Backup (`project_skills/<project>/`)**: A backup copy of every project-specific skill must be preserved in `<BRAIN_ROOT>\project_skills/<project-name>/<skill-name>/`. Brain remains the comprehensive intelligence archive while runtime prompts remain clean.

8. **Universal Project Map & Project File Map First Standard**:
   - **Routing Directory**: On every session or task, always consult `<BRAIN_ROOT>\project_map.md` first to identify which project workspace is targeted.
   - **Zero Wandering Across Repositories**: When working on any project (`project-web`, `PJCT/hi`, `PJCT/sample-project`, `appwrite/project-audio`, `PJCT/sample-project`), agents must immediately open that project's own `file_map.md` and local `context/` directory.
   - **NEVER wander into `project-web`** for context when working on another project.
   - **Consult File Map Before Reading Code**: Never read directories or code files blindly. Use `file_map.md` to pinpoint the exact 1-2 source files responsible for the task.

9. **Central Brain Cleanliness & Zero Project Files in Brain Root**:
   - `<BRAIN_ROOT>` root is reserved strictly for universal multi-project intelligence.
   - **NEVER place single-project files** (e.g. `todo.md`, `opencode_instructions.md`, `architecture_plan.md`, `cloud-infrastructure-log.md`) into `brain` root.
   - Project-specific context files belong in that project's local `context/` directory and are archived under `<BRAIN_ROOT>\projects/<project-name>/`.

10. **Subagent Search & Multi-Tier Research Invariant**:
   - **Zero Search Neglect**: Proactively search when facing new libraries, API changes, error codes, or unfamiliar documentation. Never guess.
   - **Zero Native Search Defaulting on Deep Queries**: When the user requests a **"deep search"**, **"deep research"**, **"comprehensive comparison"**, or **"exhaustive dossier"**, agents **MUST NEVER** default to the native `search_web` tool.
   - **Search Escalation Protocol**:
     - **Class A (Deep Search / Deep Research)**: MUST execute **Argon Deep Research** via `python <BRAIN_ROOT>\.agents\skills\web-search-orchestrator\scripts\search_engine.py deep-search "<topic>" -o temp_read/<name>.md`. Auto-negotiates the optimal IDLE profile from the shared 6-profile Google One AI Premium pool, auto-confirms research plan, harvests structured Markdown + citations, and purges sidebar chats.
     - **Class B (Technical Multi-Engine Search)**: MUST spawn a dedicated search subagent (`TypeName='self'`) executing `python <BRAIN_ROOT>\.agents\skills\web-search-orchestrator\scripts\search_engine.py search "<query>" --engine parallel` (Tavily + Firecrawl + TinyFish).
     - **Class C (Trivial 1-Hop Fact Check)**: Native `search_web` permitted for 1 query only (<10 words, single factual verification).
   - **Mandatory Subagent Search Isolation**: Searching, fetching pages, and crawling consume massive token budgets. ALWAYS spawn a dedicated search subagent (`TypeName='self'`). The subagent searches, drills down, and returns ONLY a clean, high-density technical briefing. Never dump raw HTML or search dumps into the parent session context.

11. **Code Output & Project Delivery Invariant (`temp_read/` Delivery Standard)**:
    - **Zero Code Clogging in Chat**: NEVER output massive multi-page code blocks or full scripts directly into conversational chat responses. It clogs the conversation context and wastes display room.
    - **Mandatory `temp_read/` in the ACTIVE Workspace**: Whenever generating or providing code files, test scripts, or notebooks, ALWAYS write them directly into `<active-workspace-root>/temp_read/` (e.g. `brain/temp_read/` when working in brain, `project-web/temp_read/` when working in project-web).
    - **Referenced Workspaces are 100% Read-Only**: When asked to "refer" to a project (e.g. `PJCT/hi`), that referenced project is strictly read-only. **NEVER drop any files or create folders inside the referenced project**. Keep the output strictly in the current active project's `/temp_read/`.
    - **High-Density, Concise Summary in Chat**: Summarize what was built, link to the file in `temp_read/`, and provide only the minimal 1-2 line run command.

14. **Turn-1 Autonomous Auto-Skill Routing & Zero-Jumble Project Isolation Invariant**:
    - **Autonomous Dispatch**: On EVERY user request across ALL projects, the agent must evaluate the task domain and activate the governing skill on Turn 1 BEFORE writing code or designing plans. Never wait for the user to type `/auto-skill` or slash commands.
    - **Universal Domain Matching**: UI $\rightarrow$ `ui-design-engine`; Documents/OCR $\rightarrow$ `document-forge`; Reasoning/RCA $\rightarrow$ `deep-thinking`; Web Search $\rightarrow$ `web-search-orchestrator`; Reverse Engineering $\rightarrow$ `rea`; Cloud GPU/Video $\rightarrow$ `external-resource`; Browser DOM $\rightarrow$ `browser-operator`.
    - **Strict Scope Segregation**: Universal skills in `brain/.agents/skills/` are safe across all projects. Project-specific skills are authorized ONLY in their active workspace. An agent working in Project A must NEVER load or invoke skills from Project B (e.g. no University-Portal skills in `hi`, no audiophile skills in `sample-project`). All code deliverables must go strictly to `<active-project>/temp_read/`.

---

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

---

## 3. Knowledge Base Reference Table

| Context File | When to Refer (Read) | When to Update (Write) |
|---|---|---|
| **`project_map.md`** | **First on every turn/session**. Master router mapping user goals to project paths, file maps, and skills. | Whenever a new project domain, repository path, or workspace is added or altered. |
| **`auto-skill` Catalog** | **Turn-1 on every request**. Dynamic registry to identify and activate universal vs project-specific skills. | Whenever a new skill is created, modified, or benchmarked (`sync_catalog.py`). |
| **`file_map.md`** | First when navigating Central Brain. Comprehensive sitemap of universal intelligence files. | Whenever a universal brain context file, skill, or master script is added or renamed. |
| **`constraints.md`** | **First before designing or executing**. Single source of truth for universal active non-negotiables. | Whenever a new active system-wide boundary or invariant is established. |
| **`projects.md`** | Before switching or inspecting projects. Contains complete project paths, domains, and repos. | Whenever a project configuration, tech stack, or status changes. |
| **`ideas.md`** | Before designing or proposing new features. Contains historical chronological record of 183+ decisions. | Whenever a high-level architectural decision or user preference is finalized. |
| **`mistakes.md`** | When debugging, encountering errors, or planning changes to prevent past failure patterns. | Automatically whenever a bug, regression, or root cause is identified and repaired. |
| **`resources.md`** | Before connecting to cloud services, VMs, databases, or API routes. Master credentials ledger. | Whenever an endpoint, IP, SSH key, secret, or cloud resource is modified. |
| **`slop.md`** | Before writing any UI component, CSS styling, or copy. Enforces dark glassmorphism standards. | Whenever visual UI/design guidelines or anti-slop rules are refined. |
| **Project `file_map.md` & `context/`** | When working within a specific project (`project-web`, `hi`, `sample-project`, `project-audio`, `sample-project`). | When project-specific architecture, opencode tasks, or logs change. |

