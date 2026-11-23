# Central Agent Brain — Universal Knowledge Base

> **Location**: `./` — Shared across ALL projects and ALL agent sessions.
> **Master Rule**: This is the permanent multi-project intelligence core. **NEVER OVERWRITE** with single-project data. **ALWAYS MERGE & APPEND**. All changes must be committed to Git.

---

## 🗺️ Master File Sitemap

| File | Purpose | When to Read |
|---|---|---|
| [`AGENTS.md`](file:///./AGENTS.md) | Universal operational rules, multi-agent roles, boundaries, and protection policies | **Start of every session** |
| [`constraints.md`](file:///./constraints.md) | Living single source of truth for active operational boundaries & free tiers | **First on every turn/task** |
| [`project_map.md`](file:///./project_map.md) | Master routing directory mapping all projects to workspaces & file maps | First to navigate projects |
| [`projects.md`](file:///./projects.md) | Master registry of all active projects (paths, repos, stacks, states) | When switching or surveying projects |
| [`file_map.md`](file:///./file_map.md) | Central Brain file map & fast navigation index | When navigating Central Brain |
| [`ideas.md`](file:///./ideas.md) | Master chronological requirements ledger across all projects | Before designing or planning features |
| [`mistakes.md`](file:///./mistakes.md) | Comprehensive failure logs, anti-patterns, and root-cause solutions | When debugging or planning changes |
| [`resources.md`](file:///./resources.md) | Active database connections, cloud endpoints, SSH keys, master secrets | Before touching any cloud service |
| [`model_benchmarks.md`](file:///./model_benchmarks.md) | Live measured latency rankings & model health across 55+ models | When diagnosing LLM latency or routing |
| [`slop.md`](file:///./slop.md) | Dark glassmorphism, mobile touch targets >=44px, anti-slop codex | Before building UI components |
| [`EXTERNAL_HARNESS_INSTRUCTIONS.md`](file:///./EXTERNAL_HARNESS_INSTRUCTIONS.md) | Operating directive for external AI coding harnesses (Cursor, Claude Code, Aider) | When external harnesses connect |

---

## 📂 Core Directories

- [`ai_api/`](file:///./ai_api/): Central AI API Registry separated by pricing mechanics:
  - [`rate_limited_and_free.md`](file:///./ai_api/rate_limited_and_free.md) (Category 1: Rate-limited, renewable, 100% free models).
  - [`limited_credits_and_paid.md`](file:///./ai_api/limited_credits_and_paid.md) (Category 2: Limited credits & paid models; OpenRouter 1,000 prompts/day key; Lightning AI paid credits).
  - [`other_providers.md`](file:///./ai_api/other_providers.md) (Category 3: Search, sandboxes, Redis, scrapers).
- [`research/`](file:///./research/): Grounded forensic research datasets:
  - [`cloud_compute_platforms.md`](file:///./research/cloud_compute_platforms.md) (Comprehensive master reference for all cloud compute and GPU platforms).
  - [`open_source_skills_memory_research.md`](file:///./research/open_source_skills_memory_research.md) (Hermes agent, CoALA cognitive architectures, ContextEngine).
  - [`hi_frontier_research/`](file:///./research/hi_frontier_research/) (Modules 01-08: Ternary, TPU JAX, Voice/LivePortrait, Deassistantized chat, Loop Eng).
- [`.agents/rules/`](file:///./.agents/rules/): Core rule files automatically loaded by Antigravity and subagents.
- [`.agents/skills/`](file:///./.agents/skills/): Exactly 13 Universal Consolidated Powerhouse Skills.
- [`projects/`](file:///./projects/): Permanent centralized backup archives of project-specific contexts.
- [`project_skills/`](file:///./project_skills/): Permanent centralized backup archives of project-specific skills.
