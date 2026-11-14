# Open-Source Agent Skill Architectures, Memory & Compaction Research Briefs

> **Source**: Grounded Deep Research on Nous Research Hermes Agent, Anthropic Agent Skills, CoALA Cognitive Architectures, and ContextEngine.  
> **Archived In**: `<BRAIN_ROOT>\research\open_source_skills_memory_research.md`  
> **Date**: 2026-09-03

---

## 1. Open-Source Agent Skill Architectures & Autonomous Skill Synthesis

### Top 5 Frameworks
1. **[NousResearch/hermes-agent](https://github.com/nousresearch/hermes-agent)** (~240k+ stars): Native self-evolution, runtime skill creation, security quarantine, slash-command routing. Extends `agentskills.io` markdown format.
2. **[anthropics/skills](https://github.com/anthropics/skills) / [agentskills/agentskills](https://github.com/agentskills/agentskills)** (~40k+ stars): Reference implementation for open Agent Skills specification (`agentskills.io/specification`). Progressive context disclosure.
3. **[Significant-Gravitas/AutoGPT](https://github.com/significant-gravitas/autogpt)** (~187k+ stars): Graph-based block execution engine with persistent execution trajectories.
4. **[crewAIInc/crewAI](https://github.com/crewaiinc/crewai)** (~58k+ stars): Role-based agent orchestration with event-driven flows and cache-backed tool execution registries.
5. **[huggingface/smolagents](https://github.com/huggingface/smolagents)** (~29k+ stars): Code-first agent execution (`CodeAgent`) executing raw Python in sandboxes.

### Progressive Disclosure Hierarchy (agentskills.io)
- **Level 0 (System Startup Index)**: Only `name` + `description` loaded into agent prompt (~50–100 tokens/skill). Maintaining 100 skills requires only ~6,000–8,000 tokens.
- **Level 1 (Targeted Activation)**: When task matches triggering keywords in description, load `SKILL.md` body on-demand (<5,000 tokens).
- **Level 2 (Leaf Execution & Resources)**: Scripts in `scripts/`, deep docs in `references/`, schemas in `assets/` are loaded only when an invariant step explicitly calls them.

### 4-Stage Autonomous Distillation Pipeline
1. **Trajectory Normalization & Failure Pruning**: Filter non-zero exit codes, deduplicate idempotent reads from `transcript.jsonl`.
2. **Parameterization & Invariant Extraction**: Replace machine-specific paths with `<PROJECT_DIR>`, `<USER_HOME>`, extract preconditions and assertions.
3. **Two-Pass Runbook Synthesis**: Pass A generates `SKILL.md`; Pass B verifies grounding against AST execution traces.
4. **Automated Registry Validation Gate**: Schema linting, security scanning (secret leaks, destructive commands), and isolated test replay.

---

## 2. Long-Term Experiential Memory & Dialectical User Modeling

### Curated Memory Architecture (`USER.md` & `MEMORY.md`)
- **`USER.md`**: Dialectical persona & interaction profile. Hard-capped at **1,375 characters** (~350 tokens).
- **`MEMORY.md`**: Project invariants, bug workarounds, environment constraints. Hard-capped at **2,200 characters** (~550 tokens).
- **Total Injected Memory Budget**: Strictly $\le 3,500$ characters.

### SQLite FTS5 (BM25) vs. Vector Embeddings
- **Retrieval Latency**: FTS5 runs in **0.2ms – 0.8ms** (pure C/stdlib in WAL mode) vs 15ms–65ms for vector models.
- **Symbol Precision**: 100% exact identifier recall on stack traces (`ECONNREFUSED`, `TypeError`) and flags, whereas vector embeddings smear exact code symbols into arbitrary subwords.
- **Dependency Overhead**: 0 MB (Python stdlib `sqlite3`) vs 250MB–1.2GB for vector models.

### Scope Precedence: Project-Local > Global
- When a local codebase rule conflicts with a global preference, **Project Local trumps Global**.

---

## 3. ContextEngine & Progressive Context Compaction

### Tri-Partition Model
- **Partition A: Immutable Invariant Ledger**: Zero-loss target. Hard negative constraints, ports, credentials, zero-mock rules. Never summarized.
- **Partition B: Hierarchical AST Skeleton**: Code bodies stripped to signatures, docstrings, and exports.
- **Partition C: Distilled Episodic Graph**: Recency buffer (last 8–10 turns preserved verbatim).

### Prompt Cache Alignment
- Split context into **Static Anchor (Cached)**, **Consolidated Summary Block (Semi-Static / Block-Cached)**, and **Rolling Recency Buffer (Dynamic)** to maximize 90% prompt cache discounts on Claude/Gemini.

---

## 4. Universal Agent Bootstrapping & Multi-Project Central Brain

### Hub-and-Spoke Sovereign Memory Model
- **Central Brain (`<BRAIN_ROOT>`)**: Read-only master intelligence repository. Protected by strict Zero-Wipe Invariant.
- **Project Workspace**: Isolated spoke with hydrated `.agents/skills/hermes-agent/`, `.agents/rules/`, and `.hermes/project_memory.db`.
- **Sentinel Block Merging**: Injects managed rules between `<!-- HERMES-MANAGED:START -->` and `<!-- HERMES-MANAGED:END -->`, preserving user sovereign rules outside the sentinels.
