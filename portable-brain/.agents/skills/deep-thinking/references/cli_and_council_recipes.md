# Deep Thinking: Extended CLI Recipes, Multi-Perspective Councils & Cognitive Tooling

This reference contains advanced recipes for `deep-thinking`, including multi-model consultation councils, prompt synthesis, and dialectical stress testing.

---

## 1. Multi-Perspective Consultation Councils (`consult_argon.py`)

Run multi-agent deliberation across diverse perspectives:
```bash
# Dialectical council on an architectural plan:
python .agents/skills/deep-thinking/scripts/consult_argon.py --council plan --file path/to/plan.md --rounds 2

# Code diff audit council:
python .agents/skills/deep-thinking/scripts/consult_argon.py --council diff --rounds 1

# Full comprehensive panel:
python .agents/skills/deep-thinking/scripts/consult_argon.py --council full --prompt "Evaluate storage trade-offs between R2 and Postgres for large ASTs"
```

### Council Personas:
- **Argon Architect**: Focuses on boundary enforcement, scalability invariants, and storage tier constraints.
- **Neon Creative/Critic**: Focuses on counter-hypotheses, failure edge-cases, and UX implications.
- **Spark Analyst**: Focuses on algorithmic efficiency, token optimization, and mathematical rigors.

---

## 2. Google Spark Prompt Synthesis (`synthesize_prompt.py`)

Synthesize self-contained, high-density reasoning prompts for Google Spark or external frontier models:
```bash
python .agents/skills/deep-thinking/scripts/synthesize_prompt.py \
  --task "Derive optimal multi-profile lease rotation algorithm" \
  --context "3 profiles max, 6 tabs max, 3.5h rolling quota" \
  --out temp_read/spark_prompt.md
```

---

## 3. Storage Hierarchy Architecture & Constraints

When designing data models across projects:
- **Supabase (500 MB DB Limit)**: User authentication, lightweight user profile metadata, minimal telemetry. Never store large documents or ASTs.
- **Cloudflare R2 (10 GB Free Storage / $0 Egress)**: Full rich-text JSON ASTs, large document revisions, media uploads, export archives.
- **Azure PostgreSQL (Standard_B1ms Free Tier)**: Relational tables, `pgvector` embeddings, academic taxonomy, high-volume telemetry.
