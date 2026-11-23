# Central Brain operating rules

## Route before acting

1. Open ./project_map.md first. Use the active project's file_map.md and relevant context/ before reading source. Brain is an attached co-folder in many projects. Start with the files identified by the map.
2. On the first turn, activate the governing skill. Consult auto-skill for routing. Use the active project's .agents/skill_overlays/<skill>.md via resolve_skill_overlay.py; validate scope before loading it. Project-only skills stay in that project's .agents/skills/ with backups in Brain project_skills/<project>/. Gemini prompt personas stay in .agents/gemini_skills/. Never load a foreign project's skills.
3. Brain's 13 universal skills are auto-skill, browser-operator, deep-thinking, document-forge, exhaustive-audit-and-repair, external-resource, full-sync, hermes-agent-core, internal-tools, offload, rea, ui-design-engine and web-search-orchestrator. Keep one canonical copy in Brain .agents/skills/. Windows Codex uses per-skill junctions in ~/.agents/skills/ and scans the active repo's local skills up to its Git root. Use references for details and avoid duplicate installs.

## Preserve project boundaries

- Brain is the permanent multi-project knowledge base. Read before merging and preserve other projects' content. Keep project records in local context/ with Brain archives under projects/<project>/. Commit scoped Brain changes in Git. Preserve existing user changes and exclude credentials and scratch output.
- Put delivered scripts, notebooks and reports in the active project's temp_read/ and link them in chat. Referenced workspaces are read-only. Apply changes to tracked source only when the task calls for it.
- Mineserver ver_backup/ is immutable. Shutdown uses save-all flush with save-on enabled and writes only to latest_world/.
- Work autonomously on authorized actions within the current host permission and approval settings. Use real upstream data and actionable error or empty states in production.

## Coordinate and verify

- Antigravity plans, leads frontend architecture and QA, and coordinates offload. Codex and AGY workers implement and verify assigned work or collaborate as peers. OpenCode owns backend infrastructure and database work. Read the target context/opencode_instructions.md and database boundaries before backend schema changes. Google Spark handles cloud reasoning with self-contained prompts.
- Use offload_manager.py with explicit --project or --workspaces every time. Select the target board from all active workspace roots; use Brain only for Brain work or its sole workspace. Offload V3 supports main-X, worker-X and collab-X. Send exact files, skills, boundaries and verification. Report blockers with worker-ask and deliver with worker-complete. Use --preserve-listening for delegated work.
- Antigravity must avoid DeepCoder and DeepInvestigator, which fail on missing skill_search. Use TypeName='self' for implementation or 'research' for read-only work. Codex uses its native agent interface. Inline quick tasks (<=20s); use one worker for focused heavy work, or 2-4 for at least three disjoint slices. Cap joint deliberation at three rounds and ten messages per turn.
- Check relevant types, syntax, tests, user flows and runtime/CI before reporting completion. Confirm regressions are covered where behavior changes. Be direct and conversational.
- For significant tasks, use hermes-agent-core to recall prior decisions. Flush durable decisions and failure lessons before compaction or at milestones. Use browser-operator's compact DOM index where applicable.

## Use the frontier pool

The 11 Google AI Pro profiles have 3-5 hour rolling quota windows. Proactively use AI Studio Playground via consult_argon.py for architecture, code/skill reviews and independent critique. Use gemini-4-argon or gemini-4-neon High with Search off. Use Gemini Web 4 Neon High for Chat, --deep-research and --task. Prefer Deep Research for multi-source work to use the rolling window efficiently. Use dedicated research agents for multi-source exploration, return concise cited findings, and avoid defaulting to native search for deep requests. Use web-search-orchestrator and primary docs for technical verification.

- Drain seven Tier-1 Alts first across the independent surface buckets. Four Tier-2 Daily Drivers are strictly last. Globally use at most three agent profiles and six agent tabs. Never touch or close user-owned tabs or windows. Block 4 Hydrogen and 4 Carbon. AI Studio /apps is retired. Use Vertex AI only when the browser pool is exhausted or the user requests it.
- Run bundled driver CLIs directly. During operations, do not read consult_argon.py, gemini_brain_driver.py or aistudio_subagent.py or add wrappers. The interactive bridge is 127.0.0.1:9229 on WinSta0\Default. Antigravity's isolated exebox desktop cannot launch those windows. Use Start_Gemini_Session.bat on the interactive desktop.
- Follow deep-thinking and browser-operator for composable context, secret redaction, leased profiles, tab parking, Task completion gates, and agent-owned chat cleanup. NotebookLM uses at most 12 scrubbed bundles and --cleanup-notebooks. Use offload's worktree procedure for NTFS junction-safe cleanup.

## Cost and product invariants

- Azure VMs use zero public IPv4 addresses through Cloudflare Tunnels and P6 64GB SSDs or smaller. Azure PostgreSQL Standard_B1ms hosts relational and vector data including SRM cards, profiles and cache. Supabase holds auth and lightweight preferences within 500MB. Use Cloudflare R2 for rich-text ASTs, binaries and media. FLH-ONE primary AWS compute is Lambda only. Keep free-tier constraints and verify cost-changing operations.
- Launch cloud GPU notebooks only after caller scripts and payloads are written, syntax-checked and verified.
- Use dark glassmorphism, touch targets >=44px, and no horizontal overflow at widths <=375px. Consult slop.md.

| Reference | Use |
| --- | --- |
| project_map.md, projects.md | Route to the active project and its root |
| file_map.md, local file_map.md | Find source and context |
| constraints.md | Shared non-negotiables |
| ideas.md | Prior decisions and rationale |
| mistakes.md | Root causes and durable lessons |
| resources.md | Infrastructure reference; keep secrets out of prompts |
| slop.md | UI and copy standards |
