---
name: deep-thinking
description: "Multi-perspective deep reasoning, hypothesis branching, architectural ideation, Spark/Gemini research prompt synthesis, and cloud storage blueprinting."
---

# Deep Thinking: Unified Cognitive Architecture & Reasoning Core

> **Step-0 Project Overlay**: Before executing, check if `<active-project>/.agents/skill_overlays/deep-thinking.md` exists (via `python .agents/skills/auto-skill/scripts/resolve_skill_overlay.py --project <root> --skill deep-thinking`).

> [!IMPORTANT]
> ⛔ **EXECUTION-FIRST MANDATE**: Scripts in `scripts/` are executable software tools, NOT documentation. Never ask the user to run them or read them passively. Execute immediately via shell commands. When invoking Windows binaries from WSL, append `< /dev/null`.

---

## 1. When to Activate Deep Thinking

Activate autonomously whenever facing architectural ambiguity, system-level design decisions, tricky root cause analysis (subtle race conditions, cascading errors), database schema modifications, or explicit slash directives (`/boost`, `/goal`, *"think deeply"*).

---

## 2. Universal Storage Tier Boundaries (MANDATORY)

| Tier / Provider | Free Tier Limit | Permitted Data Types | STRICTLY FORBIDDEN |
|:---|:---|:---|:---|
| **Tier 1: Metadata (Supabase)** | **500 MB DB Limit** | Auth, user metadata, lightweight preferences, text notes | 🛑 Rich-text JSON ASTs, large documents, binary payloads |
| **Tier 2: Object Vault (Cloudflare R2)** | **10 GB Storage / $0 Egress** | Full rich-text JSON ASTs, document revisions, media, exports | 🛑 Low-latency relational SQL foreign-key queries |
| **Tier 3: Relational/Vector (Azure Postgres)** | **Standard_B1ms 750h/mo Free** | AI Vector Embeddings (`pgvector`), heavy taxonomy, prompt cache | 🛑 Global public passwords, paid public IPv4 addresses |

---

## 3. The 5-Phase Cognitive Loop

1. **Phase 1: Framing & Scoping** — Identify core objective, boundaries, non-negotiable invariants, and success metrics.
2. **Phase 2: Dialectical Stress Testing** — Formulate 3 competing hypotheses (Null, Mainstream, Radical/Orthogonal).
3. **Phase 3: Sequential Thinking** — Step-by-step reasoning with hypothesis pruning and falsification checks.
4. **Phase 4: Anti-Pattern Verification** — Cross-check proposed solution against historical failures in `mistakes.md`.
5. **Phase 5: Decision Lock** — Document final trade-offs, commit durable decisions to `ideas.md`, and generate action items.

---

## 4. Rolling-Window AI Pro Utilization

Proactively leverage the 11 Google AI Pro accounts across rolling 3–5 hour quota windows:
- **Architecture & Code Critique**: AI Studio Playground via `consult_argon.py` with `gemini-4-argon` or `gemini-4-neon` (High thinking, `--search off`).
- **Research & Dossiers**: Gemini Web `4 Neon` High via `consult_argon.py --deep-research` or `--task`.
- **Drain Priority**: Always prioritize the 7 Tier-1 Alt profiles; reserve 4 Tier-2 Daily Drivers strictly as last resort.

---

## 5. Core CLI Commands

```bash
# 1. Consult AI Studio Argon/Neon for architectural critique
python .agents/skills/deep-thinking/scripts/consult_argon.py --prompt "Evaluate storage trade-offs"

# 2. Multi-perspective council deliberation (plan review)
python .agents/skills/deep-thinking/scripts/consult_argon.py --council plan --file path/to/plan.md --rounds 1

# 3. Code diff audit council
python .agents/skills/deep-thinking/scripts/consult_argon.py --council diff --rounds 1

# 4. Synthesize self-contained Google Spark reasoning prompt
python .agents/skills/deep-thinking/scripts/synthesize_prompt.py --task "<task>" --out temp_read/spark_prompt.md
```

---

## 6. References & Cognitive Frameworks

- [Extended CLI Recipes & Council Guide](references/cli_and_council_recipes.md) — Comprehensive council recipes and persona prompts.
- [Cognitive Reasoning Frameworks](references/cognitive_reasoning_frameworks.md) — Detailed dialectical reasoning blueprints.
- [Architecture Spec Template](references/architecture_spec_template.md) — Production-ready architectural specification template.
- [Spark Prompt Template](references/spark_prompt_template.md) — High-density prompt template for Google Spark.