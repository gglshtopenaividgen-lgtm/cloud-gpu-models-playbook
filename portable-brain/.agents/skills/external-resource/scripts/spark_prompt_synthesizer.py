#!/usr/bin/env python3
"""
High-Density Google Spark Prompt Synthesizer
Generates structured, anti-slop cognitive prompts that force Gemini Spark to
engage in rigorous mathematical derivations, architectural proofs, and multi-perspective audits.
"""

import argparse
from pathlib import Path

def synthesize_spark_prompt(topic: str, role: str = "Principal Systems Architect", constraints: str = "") -> str:
    default_constraints = (
        "- 100% Free Tier strictly enforced (Zero unapproved cloud costs).\n"
        "- Subagent Invariant: NEVER use DeepCoder or DeepInvestigator (runtime registry defect). Use 'self' or 'research'.\n"
        "- Central Brain Anti-Wipe Rule: Merge and append; never overwrite historical knowledge.\n"
        "- Zero-Mock Policy: Authentic error handling and real upstream APIs only."
    )
    active_constraints = constraints or default_constraints

    prompt = f"""# MANDATORY COGNITIVE DIRECTIVE FOR GEMINI SPARK

## 1. Identity & Operational Role
You are the **{role}**. You do NOT write generic introductory filler, conversational pleasantries, marketing fluff, or AI slop. You execute dense mathematical, architectural, and algorithmic analysis.

## 2. Target Investigation Domain
**Topic**: {topic}

## 3. Active Invariant Guardrails & Cost Constraints
{active_constraints}

## 4. Multi-Perspective Dialectical Stress Test (MANDATORY EXECUTION)
You must analyze this topic through 4 distinct critical lenses:
1. **The Architect**: Evaluate systemic modularity, clean interface boundaries, fault tolerance, and elegant abstraction layers.
2. **The Adversary**: Identify exact failure modes, race conditions, edge-case network dropouts, rate limit cliffs (HTTP 429), and memory leaks.
3. **The Cost Guard**: Verify strict 100% Free-Tier feasibility, VRAM ceilings, bandwidth egress, compute limits, and scale-to-zero lifetimes.
4. **The Implementation Specialist**: Deliver production-ready code algorithms, schemas, exact equations, and benchmark matrices.

## 5. Required Deliverables & Format
- **Mathematical Derivations / Bounds**: Show explicit asymptotic complexity, memory footprints, or latency budgets.
- **Structural Blueprint**: Use Markdown tables and clean ASCII / Mermaid diagrams.
- **Production Code Artifact**: Complete, syntax-checked Python, TypeScript, or GLSL implementation with zero pseudo-placeholders.
- **Zero-Slop Rule**: Do not say "In conclusion", "As an AI", or restate the prompt. Deliver pure signal.
"""
    return prompt

def main():
    parser = argparse.ArgumentParser(description="Generate high-density Gemini Spark cognitive prompts.")
    parser.add_argument("--topic", "-t", required=True, help="Research or architectural topic")
    parser.add_argument("--role", "-r", default="Principal Systems Architect", help="Cognitive role title")
    parser.add_argument("--output", "-o", help="Optional output text file path")

    args = parser.parse_args()
    prompt = synthesize_spark_prompt(args.topic, args.role)

    if args.output:
        Path(args.output).write_text(prompt, encoding="utf-8")
        print(f"Saved Spark prompt to {args.output}")
    else:
        print(prompt)

if __name__ == "__main__":
    main()
