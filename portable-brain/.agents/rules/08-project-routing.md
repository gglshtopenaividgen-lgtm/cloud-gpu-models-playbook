---
description: >-
  Master project routing and file map first standard across all workspaces.
  Always refer to project_map.md and the project file_map.md before navigating code.
trigger: always_on
---
# Master Project Routing & Autonomous Auto-Skill Standard

1. **Routing Invariant**: On every session or user request, always consult `<BRAIN_ROOT>\project_map.md` first to identify the active target project.
2. **Project Independence & Anti-Wandering**: Open that project's designated `file_map.md` and read only the 1-2 source files needed. NEVER inspect or read `project-web/context/` when working on another project.
3. **Turn-1 Autonomous Auto-Skill Resolution**:
   - On every task, automatically evaluate which universal or project skill governs the domain before executing.
   - Zero passive waiting: NEVER wait for the user to type `/auto-skill` or slash commands.
   - If uncertain of matching skills, query:
     `python <BRAIN_ROOT>\.agents\skills\auto-skill\scripts\select_skill.py "<domain>" --project <active_project>`
4. **Strict Zero-Jumble Project Scope Segregation**:
   - **Universal Skills** (`brain/.agents/skills/`): 100% permitted across all projects.
   - **Active Project Skills** (`<active_project>/.agents/skills/`): Authorized ONLY for the active project.
   - **Foreign Project Skills**: STRICTLY PROHIBITED. Never cross-contaminate skills, code, or context between projects.
5. **Brain Cleanliness & Delivery Standard**:
   - NEVER place single-project files into `brain/` root.
   - All code, scripts, or outputs must go strictly to `<active_project>/temp_read/`.
6. **Shared Argon Fleet & Execution-First Invariant**:
   - Universal tools and Chrome profiles are a shared compute pool across all projects?never artificially hardcoded to specific projects.
   - Any agent can inspect live fleet status (`consult_argon.py --status` or `search_engine.py deep-search --status`) to see which profiles are IDLE vs BUSY and their usage %, and decide which profile to select.
   - If an agent does not specify `--profile`, the system auto-selects the optimal idle profile with the lowest usage.
   - **STRICT PROHIBITION**: NEVER call `read_file` or `view_file` on driver scripts (`consult_argon.py`, `gemini_brain_driver.py`, `search_engine.py`, `gemini_deep_research.py`) and NEVER fall back to paid GCP Vertex AI (`custom_tools/api_router/argon.py`). Always execute directly via `run_command`.
   - **Zero Intermediate Wrapper Scripts**: ?? **STRICT PROHIBITION**: NEVER create temporary Python wrapper scripts (e.g. `run_argon_query.py`, `query_argon.py`) or waste turns running CLI `--help`. Execute `consult_argon.py` directly on Turn 1!
     - Normal Prompt: `python <BRAIN_ROOT>\.agents\skills\deep-thinking\scripts\consult_argon.py "<prompt>" -o temp_read/ans.md`
     - Multi-line Prompt: `python <BRAIN_ROOT>\.agents\skills\deep-thinking\scripts\consult_argon.py --prompt-file temp_read/prompt.md -o temp_read/ans.md`
     - Deep Research: `python <BRAIN_ROOT>\.agents\skills\deep-thinking\scripts\consult_argon.py "<topic>" --deep-research -o temp_read/research.md`
   - **Default Sidebar Chat Purge**: Runs default to `clean=True`, automatically deleting the ephemeral chat from the Gemini sidebar after delivering output to `temp_read/`.
   - **Live Quota Observability**: Audits and prints 5-hour and weekly usage limits before lease release.
   - **Quill Chip Preservation**: Preserves the `[ ⚛ Deep research ]` pill chip in the input box during prompt insertion.
7. **Search Escalation Standard**:
   - Never default to native `search_web` for deep research or complex technical queries.
   - For "deep search" / "deep research": MUST execute Argon Deep Research (`search_engine.py deep-search` or `gemini_deep_research.py`).
   - For technical search / documentation: MUST spawn a search subagent (`TypeName='self'`) to run `search_engine.py search "<query>" --engine parallel`.
   - Native `search_web` is permitted strictly for 1-hop trivial fact checks (<10 words).
