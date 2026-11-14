#!/usr/bin/env python3
"""
structured_brainstorm.py - Lateral Ideation & Cognitive Brainstorming Generator
Autonomous AI Cognitive System | Deep Thinking Universal Skill

Frameworks implemented:
1. SCAMPER (Substitute, Combine, Adapt, Modify, Put to other use, Eliminate, Reverse)
2. Six Thinking Hats (de Bono: White, Red, Black, Yellow, Green, Blue)
3. Inversion (Munger / Jacobi: Anti-Goal Inversion & Failure Roadmapping)
4. First Principles Decomposition (Feynman / Musk: Axiomatic breakdown)
5. TRIZ Inventive Principles Matrix for Software & AI Agent Architecture
"""

import sys
import json
import argparse
from typing import Dict, Any, List


TRIZ_CONTRADICTIONS_DB = {
    "speed_vs_consistency": {
        "tension": "Desire for sub-second execution speed vs. guarantee of strict data consistency/correctness.",
        "principles": [
            {"id": 1, "name": "Segmentation", "application": "Decouple synchronous critical-path transactions from eventual background consistency jobs."},
            {"id": 10, "name": "Prior Action", "application": "Pre-compute embeddings or cache warm query paths prior to user request."},
            {"id": 24, "name": "Intermediary / Caching", "application": "Insert an in-memory Redis or edge KV buffer to absorb instant reads."},
            {"id": 19, "name": "Periodic Action", "application": "Shift from continuous sync to micro-batched scheduled reconciliation."}
        ]
    },
    "autonomy_vs_safety": {
        "tension": "Maximizing autonomous agent agency vs. preventing catastrophic commands, data loss, or cost runaways.",
        "principles": [
            {"id": 2, "name": "Extraction / Taking Out", "application": "Isolate high-risk operations behind deterministic policy enforcers rather than prompt warnings."},
            {"id": 23, "name": "Feedback", "application": "Implement closed-loop telemetry and proof-of-work validation before signaling task completion."},
            {"id": 35, "name": "Parameter Changes", "application": "Grant read autonomy freely, but require pre-flight simulation or approval gates for destructive writes."}
        ]
    },
    "modularity_vs_latency": {
        "tension": "High modularity (many small micro-agents/services) causes network hop latency and serialization overhead.",
        "principles": [
            {"id": 5, "name": "Merging / Consolidation", "application": "Group tightly-coupled conversational reasoning steps into a single monolithic agent context."},
            {"id": 7, "name": "Nested Doll", "application": "Nest specialized subagents inside the parent runtime memory rather than making external HTTP hops."},
            {"id": 3, "name": "Local Quality", "application": "Optimize critical sub-paths with zero-overhead in-process function calls while keeping non-critical boundaries modular."}
        ]
    },
    "capability_vs_cost": {
        "tension": "Desire for frontier reasoning quality (expensive models, GPUs) vs. strict zero-dollar or low-budget operational limits.",
        "principles": [
            {"id": 25, "name": "Self-Service", "application": "Use self-hosted free tier compute (Azure B1ms, Cloudflare Workers, local scripts) to handle 90% of deterministic logic."},
            {"id": 6, "name": "Universality", "application": "Use versatile generalist models with structured prompts to replace arrays of multiple specialized proprietary models."},
            {"id": 13, "name": "The Other Way Round (Inversion)", "application": "Filter and reduce candidate volume upfront so only high-value, pre-vetted queries touch expensive reasoning models."}
        ]
    },
    "generality_vs_specialization": {
        "tension": "Generalist universal skills vs. hyper-tailored project-specific constraints.",
        "principles": [
            {"id": 1, "name": "Segmentation & Tiering", "application": "Universal skills remain in Central Brain root; project-specific extensions live in project-local skills and mirror to project_skills/."}
        ]
    }
}


def generate_scamper(topic: str) -> str:
    lines = [
        f"# SCAMPER Lateral Ideation: {topic}",
        "",
        "| Dimension | Prompt Lens | Architectural Prompt & Probe |",
        "|---|---|---|",
        f"| **S - Substitute** | Swap components, providers, or mechanisms | What happens if we substitute expensive cloud APIs with local deterministic algorithms or edge workers for *{topic}*? |",
        f"| **C - Combine** | Fuse multiple features or tools | Can we combine ingestion, validation, and schema formatting into a single atomic pipeline step? |",
        f"| **A - Adapt** | Borrow solutions from biological or mechanical domains | How does a hardware CPU cache or biological immune system solve the equivalent problem in *{topic}*? |",
        f"| **M - Modify / Magnify** | Scale parameters up or down 100x | If we had to handle 10,000x current concurrency or run on 16MB RAM, how would the architecture adapt? |",
        f"| **P - Put to Another Use** | Repurpose existing assets | Can existing log streams or SQLite metadata caches be repurposed to serve as real-time RAG context? |",
        f"| **E - Eliminate** | Cut unnecessary layers to absolute zero | What is the single most unnecessary abstraction, middleware, or subagent in *{topic}*? Cut it. |",
        f"| **R - Reverse / Rearrange** | Invert the execution flow | What if the consumer pulls data on demand instead of the producer pushing it? What if validation happens first? |",
        ""
    ]
    return "\n".join(lines)


def generate_six_hats(topic: str) -> str:
    lines = [
        f"# Six Thinking Hats Protocol (Edward de Bono): {topic}",
        "",
        "### ⚪ White Hat (Objective Data & Facts)",
        f"- What hard metrics, benchmark logs, and verified ground-truth constraints exist for *{topic}*?",
        "- What facts are missing, and how can they be empirically measured right now?",
        "",
        "### 🔴 Red Hat (Intuition, Instinct & Aesthetics)",
        f"- What is our immediate gut reaction to *{topic}*? Does the design feel bloated, fragile, or elegant?",
        "- Zero justification required: does this feel like AI slop or high-craft precision?",
        "",
        "### ⚫ Black Hat (Critical Risk & Devil's Advocate)",
        f"- What is the primary failure mode of *{topic}* under adverse conditions?",
        "- What edge cases, rate limits, quota caps, and silent errors could corrupt the system?",
        "",
        "### 🟡 Yellow Hat (Optimistic Value & Upside)",
        f"- What is the best-case operational payoff if *{topic}* succeeds?",
        "- What compounding leverage or architectural superpowers does this unlock for the agent squad?",
        "",
        "### 🟢 Green Hat (Lateral Leaps & Unconventional Creativity)",
        f"- What radical, non-obvious, or counter-intuitive approach could bypass the standard bottlenecks of *{topic}* entirely?",
        "- How would we solve this if normal tools were completely unavailable?",
        "",
        "### 🔵 Blue Hat (Metacognition & Synthesis)",
        f"- What are the concrete next steps? How do we synthesize the White, Black, Yellow, and Green insights into a single unified plan?",
        "- What is our decision lock criterion?",
        ""
    ]
    return "\n".join(lines)


def generate_inversion(topic: str) -> str:
    lines = [
        f"# Munger Inversion Analysis: {topic}",
        "",
        "> *'Invert, always invert: Turn a situation or problem upside down. What happens if we do the exact opposite of what we want to achieve?' — Carl Jacobi / Charlie Munger*",
        "",
        "## Anti-Goal Formulation",
        f"**Question**: *How could an autonomous agent guarantee absolute, unmitigated disaster when implementing '{topic}'?*",
        "",
        "### 1. Primary Disaster Vectors (Anti-Patterns to Guarantee Failure)",
        f"- **Data Destruction**: Silently wipe existing project context or overwrite `/brain` files without reading first.",
        f"- **Resource Exhaustion**: Trigger runaway subagent loops or infinite retries that burn tokens and deplete quotas.",
        f"- **Runtime Crash**: Call defective components (e.g. `DeepCoder` requiring missing `skill_search`) causing immediate 1s aborts.",
        f"- **Blind Assumption**: Announce complete success without compiling code or verifying live runtime status.",
        f"- **Slop Generation**: Dump unformatted massive raw code blocks into chat instead of using clean `temp_read/` outputs.",
        "",
        "## Inversion Defense Shield (The Reversal)",
        "By systematically enumerating and blocking every single anti-pattern above, project success is the inevitable mathematical remainder:",
        "1. Block all destructive overwrites (`brain` anti-wipe rule).",
        "2. Enforce hard iteration caps (3 deliberation rounds, max 10 messages).",
        "3. Mandate `TypeName='self'` for all engineering subagents.",
        "4. Require live proof-of-work static checks (`python -m py_compile`, `tsc --noEmit`) before sign-off.",
        "5. Direct all script deliverables into `temp_read/` and summarize cleanly.",
        ""
    ]
    return "\n".join(lines)


def generate_first_principles(topic: str) -> str:
    lines = [
        f"# First Principles Decomposition (Aristotle / Feynman / Musk): {topic}",
        "",
        "## Step 1: Strip Analogical Thinking",
        f"- Identify conventional wisdom: *'Everyone does X because industry standards say so.'*",
        f"- Challenge the analogy: *'Why do we actually need X for {topic}? Is X truly required or just familiar baggage?'*",
        "",
        "## Step 2: Identify Fundamental Axiomatic Truths",
        "- **Physical/Hardware Limits**: CPU clock cycles, RAM capacity, network ping round-trip speed of light (~5ms per 1,000km).",
        "- **Information Theory**: Shannon entropy, token bandwidth, minimum bits required to represent the state.",
        "- **Economic Invariants**: Free Tier boundaries (Azure B1ms 750h, Cloudflare 10GB R2, Supabase 500MB DB).",
        "",
        "## Step 3: Reconstruct Upwards from Axioms",
        f"- Given ONLY the fundamental truths, what is the absolute simplest, most direct computational path to satisfy the goal of *{topic}*?",
        "- Build the leanest architecture with zero redundant abstractions.",
        ""
    ]
    return "\n".join(lines)


def generate_triz(contradiction_key: str = None) -> str:
    lines = ["# TRIZ Inventive Principles for Software & AI Agents", ""]
    if contradiction_key and contradiction_key in TRIZ_CONTRADICTIONS_DB:
        items = {contradiction_key: TRIZ_CONTRADICTIONS_DB[contradiction_key]}
    else:
        items = TRIZ_CONTRADICTIONS_DB

    for key, data in items.items():
        lines.append(f"## Contradiction: `{key}`")
        lines.append(f"> **Tension**: {data['tension']}")
        lines.append("")
        lines.append("| TRIZ Principle | Software Architecture Implementation |")
        lines.append("|---|---|")
        for p in data["principles"]:
            lines.append(f"| **#{p['id']} {p['name']}** | {p['application']} |")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Structured Brainstorming & Lateral Ideation Tool")
    subparsers = parser.add_subparsers(dest="framework", help="Brainstorming framework to generate")

    subparsers.add_parser("scamper", help="SCAMPER lateral ideation framework").add_argument("--topic", default="Autonomous Agent Reasoning Engine")
    subparsers.add_parser("sixhats", help="Edward de Bono Six Thinking Hats protocol").add_argument("--topic", default="Autonomous Agent Architecture")
    subparsers.add_parser("inversion", help="Charlie Munger Anti-Goal Inversion protocol").add_argument("--topic", default="AI Agent Reliability")
    subparsers.add_parser("firstprinciples", help="First Principles axiomatic decomposition").add_argument("--topic", default="Autonomous AI Agent Memory & Execution")
    triz_p = subparsers.add_parser("triz", help="TRIZ inventive principles for software contradictions")
    triz_p.add_argument("--contradiction", choices=list(TRIZ_CONTRADICTIONS_DB.keys()), default=None)
    
    all_p = subparsers.add_parser("all", help="Generate full multi-framework brainstorming suite")
    all_p.add_argument("--topic", default="Next-Gen Autonomous Agent Cognitive Architecture")

    args = parser.parse_args()

    if args.framework == "scamper":
        print(generate_scamper(args.topic))
    elif args.framework == "sixhats":
        print(generate_six_hats(args.topic))
    elif args.framework == "inversion":
        print(generate_inversion(args.topic))
    elif args.framework == "firstprinciples":
        print(generate_first_principles(args.topic))
    elif args.framework == "triz":
        print(generate_triz(args.contradiction))
    elif args.framework == "all":
        print(f"# Complete Multi-Perspective Cognitive Ideation Suite\n\nTarget Domain: {args.topic}\n")
        print(generate_first_principles(args.topic))
        print("---")
        print(generate_inversion(args.topic))
        print("---")
        print(generate_six_hats(args.topic))
        print("---")
        print(generate_scamper(args.topic))
        print("---")
        print(generate_triz())
    else:
        print(generate_six_hats("Autonomous Agent Reasoning Engine"))


if __name__ == "__main__":
    main()
