#!/usr/bin/env python3
"""
Google Spark & Gemini Deep Research Prompt Synthesizer
Formulates self-contained, high-density research prompts with embedded schemas,
physical hardware constraints, and trade-off matrices.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def synthesize_prompt(
    subsystem_name: str,
    physical_constraints: list[str],
    analytical_questions: list[str],
    embedded_signatures: str
) -> str:
    constraints_block = "\n".join(f"- {c}" for c in physical_constraints)
    questions_block = "\n".join(f"{idx}. {q}" for idx, q in enumerate(analytical_questions, 1))

    return f"""# Research Brief & Mathematical Optimization Directive: {subsystem_name}

> **Role for Google Spark / Gemini Deep Research**: Lead Cloud Systems Architect, High-Performance Distributed Systems Engineer & Algorithmic Researcher.

---

## 1. Problem Statement & Operational Context
We are architecting the **{subsystem_name}** subsystem for a high-concurrency, multi-model agent platform. Because you have no local filesystem or repository access, this prompt embeds all required data schemas, physical hardware ceilings, and architectural invariants.

---

## 2. Hard Non-Negotiable Invariants & Physical Constraints
{constraints_block}

---

## 3. Embedded Data Contracts & System Signatures
```typescript
{embedded_signatures}
```

---

## 4. Specific Analytical & Architectural Questions
{questions_block}

---

## 5. Required Output Format
- Provide rigorous, mathematically backed reasoning with concrete time-complexity ($O(n)$) and memory footprint bounds.
- Deliver production-ready code algorithms (TypeScript / Python 3.14) without placeholder comments.
- Explicitly benchmark latency overhead and failure recovery protocols under edge network partitions.
"""


def main():
    parser = argparse.ArgumentParser(description="Synthesize Google Spark / Gemini Deep Research Prompt")
    parser.add_argument("--subsystem", type=str, default="University-Portal Batch Pre-Generation Engine", help="Subsystem name")
    parser.add_argument("--output", type=Path, default=None, help="Output markdown path")
    args = parser.parse_args()

    constraints = [
        "Cloudflare Workers Edge Timeout: Hard 30-second ceiling (AbortController at 25s mandatory).",
        "Zero Billable Public IPv4 Addresses: All VM ingress routed through Cloudflare Tunnels.",
        "Database Boundaries: Supabase 500MB DB Limit (No binaries/documents). Bulk in Cloudflare R2 ($0 egress).",
        "Inference Hierarchy: Groq (117ms) -> Mistral (355ms) -> Cerebras (422ms) -> OpenRouter Free Tier (1,000 req/day).",
    ]

    questions = [
        "What is the optimal batching and bucketing window to stream pre-generated course outlines without exceeding Edge memory limits?",
        "How can token consumption be minimized while maintaining 100% precision on course syllabus extraction from OCR PDFs?",
        "Design the mathematical retry/cooldown backoff function for handling HTTP 429 rate limits across 14 heterogeneous LLM providers."
    ]

    sample_sigs = """interface PreloadBatchPlan {
  semester: number;
  branch: string;
  courseCode: string;
  units: Array<{
    unitNumber: number;
    title: string;
    keyConcepts: string[];
    suggestedImagePrompts: string[];
  }>;
}"""

    prompt = synthesize_prompt(args.subsystem, constraints, questions, sample_sigs)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(prompt, encoding="utf-8")
        print(f"✅ Generated Spark prompt at: {args.output}")
    else:
        print(prompt)


if __name__ == "__main__":
    main()
