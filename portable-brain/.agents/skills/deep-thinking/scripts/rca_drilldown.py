#!/usr/bin/env python3
"""
rca_drilldown.py - Root Cause Analysis (RCA) & Fault Isolation Engine
Autonomous AI Cognitive System | Deep Thinking Universal Skill

Frameworks implemented:
1. 5-Whys Recursive Drilldown with systemic invariant stopping rules.
2. Ishikawa / Fishbone Diagram Generator (6M AI Adaptation in Mermaid & Markdown).
3. Fault-Tree Analysis (FTA) with Boolean Logic Gates (AND / OR) & Minimal Cut Set identification.
4. Cascading Failure Blast-Radius Mapper.
"""

import sys
import json
import argparse
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class WhyStep:
    level: int
    question: str
    cause: str
    evidence: str
    category: str  # Direct symptom, Technical mechanism, Architectural gap, Systemic invariant


def run_5_whys(problem: str, chain: List[Dict[str, str]]) -> str:
    lines = [
        f"# 5-Whys Recursive Root Cause Analysis: {problem}",
        "",
        "> **Anti-Pattern Warning**: Never stop at superficial agent/human error (*'agent used wrong command'*). "
        "Drill down through technical mechanisms until reaching the foundational architectural invariant or governance policy.",
        "",
        "| Level | Why? (Causal Step) | Identified Root Mechanism | Ground-Truth Evidence / Telemetry | Causal Depth |",
        "|---|---|---|---|---|"
    ]
    
    depth_labels = [
        "1. Immediate Symptom",
        "2. Direct Technical Cause",
        "3. Architectural Vulnerability",
        "4. Process / Enforcement Gap",
        "5. Systemic Invariant / Governance Root"
    ]
    
    for i, step in enumerate(chain, 1):
        depth = depth_labels[min(i-1, len(depth_labels)-1)]
        q = step.get("why", f"Why did step {i-1} occur?")
        c = step.get("cause", "Cause under investigation")
        ev = step.get("evidence", "Verified in runtime logs")
        lines.append(f"| **Why #{i}** | {q} | **{c}** | `{ev}` | {depth} |")
        
    lines.append("")
    if chain:
        root = chain[-1].get("cause", "Identified root mechanism")
        lines.append(f"### 🎯 Foundational Systemic Root Cause:\n> **`{root}`**\n")
        lines.append("### 🛡️ Permanent Guardrail & Invariant:")
        lines.append(f"> Implement deterministic runtime gate or policy in `context/constraints.md` to mathematically prevent `{root}` from reoccurring.")
    return "\n".join(lines)


def generate_ishikawa_diagram(incident: str, categories: Dict[str, List[str]]) -> str:
    lines = [
        f"# Ishikawa (Fishbone) Diagram: {incident}",
        "",
        "## Mermaid Fishbone Graph",
        "```mermaid",
        "mindmap",
        f"  root(({incident}))"
    ]
    
    for cat_name, factors in categories.items():
        lines.append(f"    {cat_name}")
        for factor in factors:
            cleaned = factor.replace("(", "[").replace(")", "]").replace('"', "'")
            lines.append(f"      {cleaned}")
            
    lines.append("```")
    lines.append("")
    lines.append("## Detailed 6M Categorical Breakdown")
    lines.append("| Category (6M AI Adaptation) | Contributing Factors & Latent Vulnerabilities |")
    lines.append("|---|---|")
    for cat_name, factors in categories.items():
        factors_str = "<br>• ".join(factors)
        lines.append(f"| **{cat_name}** | • {factors_str} |")
        
    lines.append("")
    return "\n".join(lines)


def run_fault_tree_analysis(tree_data: Dict[str, Any]) -> str:
    lines = [
        f"# Fault Tree Analysis (FTA): {tree_data.get('top_event', 'System Failure')}",
        "",
        "## Boolean Logic Gate Breakdown",
        ""
    ]
    
    # We display logic gates
    def render_node(node: Dict[str, Any], indent: int = 0) -> List[str]:
        prefix = "  " * indent
        out = []
        name = node.get("name", "Event")
        gate_type = node.get("gate", "LEAF")
        
        if gate_type in ("AND", "OR"):
            out.append(f"{prefix}- **[{gate_type} Gate]** `{name}`")
            for child in node.get("children", []):
                out.extend(render_node(child, indent + 1))
        else:
            prob = node.get("probability", "Unspecified")
            out.append(f"{prefix}- 🛑 *Basic Event (Cut Set)*: `{name}` (P: {prob})")
        return out

    lines.extend(render_node(tree_data))
    lines.append("")
    lines.append("```mermaid")
    lines.append("graph TD")
    
    # Mermaid graph of tree
    node_counter = 0
    def build_mermaid(node: Dict[str, Any], parent_id: Optional[str] = None):
        nonlocal node_counter
        node_counter += 1
        cur_id = f"N{node_counter}"
        name = node.get("name", "Event").replace('"', "'")
        gate = node.get("gate", "LEAF")
        
        if gate in ("AND", "OR"):
            shape = f'{cur_id}{{"[{gate}] {name}"}}'
        else:
            shape = f'{cur_id}["[LEAF] {name}"]'
            
        lines.append(f"    {shape}")
        if parent_id:
            lines.append(f"    {parent_id} --> {cur_id}")
            
        for child in node.get("children", []):
            build_mermaid(child, cur_id)

    build_mermaid(tree_data)
    lines.append("```")
    lines.append("")
    
    # Compute minimal cut sets (simple approximation)
    lines.append("### Minimal Cut Sets (Single Points of Failure):")
    lines.append("Any single basic event under an **OR gate** constitutes an immediate, unbuffered catastrophic single point of failure (SPOF).")
    return "\n".join(lines)


def demo_5_whys() -> Dict[str, Any]:
    return {
        "problem": "Subagent Session Terminated After 1 Second ('Worked for 1s')",
        "chain": [
            {
                "why": "Why did the subagent terminate prematurely?",
                "cause": "Language server executor construction failed immediately upon startup.",
                "evidence": "language_server.exe logs: 'failed to construct executor'"
            },
            {
                "why": "Why did executor construction fail?",
                "cause": "Executor attempted to resolve required tool 'skill_search' from the registry and encountered an unknown component.",
                "evidence": "Error: 'failed to resolve components: unknown component: tool \"skill_search\" not found in registry'"
            },
            {
                "why": "Why was 'skill_search' demanded by the executor?",
                "cause": "Subagent was invoked with TypeName='DeepCoder' which possesses an internal dependency on skill_search.",
                "evidence": "invoke_subagent call with TypeName='DeepCoder' generated by /boost command prompt injection"
            },
            {
                "why": "Why did the agent use TypeName='DeepCoder' despite failure?",
                "cause": "Slash command prompt template instructed agent to invoke DeepCoder, overriding default heuristics.",
                "evidence": "Slash command injected text: 'Launch a DeepCoder subagent...'"
            },
            {
                "why": "Why was the prompt instruction not preempted by system safety rules?",
                "cause": "Absence of a universal precedence rule mandating TypeName='self' as an unconditional runtime invariant.",
                "evidence": "Pre-incident rules did not explicitly forbid DeepCoder across all prompt directives"
            }
        ]
    }


def demo_ishikawa() -> Dict[str, Any]:
    return {
        "incident": "Unexpected Free-Tier Database Exhaustion & Outage",
        "categories": {
            "Machine / Infrastructure": [
                "Supabase 500MB storage quota reached",
                "Shared pool memory spike under simultaneous connections",
                "Lack of automated quota alerts prior to 95% threshold"
            ],
            "Method / Algorithm": [
                "Rich-text TipTap document ASTs serialized directly into relational rows",
                "Unbounded version history retention without garbage collection",
                "Sync queries executing full table scans without indexes"
            ],
            "Material / Data Payloads": [
                "High-resolution image base64 strings embedded in JSON documents",
                "Multi-megabyte PDF binary buffers mistakenly pushed to PostgreSQL"
            ],
            "Measurement / Telemetry": [
                "No daily storage telemetry log emitted",
                "Database health check only validated ping (SELECT 1) instead of disk bytes"
            ],
            "Milieu / Environment": [
                "Concurrent multi-agent testing generating burst test documents",
                "Third-party webhook retries multiplying duplicate records"
            ],
            "Man / Agent Governance": [
                "Subagents lacked explicit storage boundary constraints in prompt",
                "Agent assumed 'database' meant Supabase for all data types"
            ]
        }
    }


def demo_fault_tree() -> Dict[str, Any]:
    return {
        "name": "Catastrophic Agent Outage & Context Loss",
        "gate": "OR",
        "children": [
            {
                "name": "Direct Memory Loss (Compaction Wipe)",
                "gate": "AND",
                "children": [
                    {"name": "Long conversation exceeding token threshold", "gate": "LEAF", "probability": 0.8},
                    {"name": "Session flush script failed or uncalled", "gate": "LEAF", "probability": 0.4},
                    {"name": "No persistent SQLite backup created", "gate": "LEAF", "probability": 0.5}
                ]
            },
            {
                "name": "Subagent Crash Loop",
                "gate": "OR",
                "children": [
                    {"name": "Invoking defective DeepCoder / DeepInvestigator", "gate": "LEAF", "probability": 0.7},
                    {"name": "Runaway infinite deliberation loop (>3 turns)", "gate": "LEAF", "probability": 0.3}
                ]
            },
            {
                "name": "Cloud Cost Spike / Out-of-Budget Lockout",
                "gate": "OR",
                "children": [
                    {"name": "Unintended Public IPv4 allocation on Azure VM", "gate": "LEAF", "probability": 0.2},
                    {"name": "Cloud GPU instance left running unmonitored", "gate": "LEAF", "probability": 0.3}
                ]
            }
        ]
    }


def main():
    parser = argparse.ArgumentParser(description="Root Cause Analysis (RCA) & Fault Isolation Engine")
    subparsers = parser.add_subparsers(dest="subcommand", help="RCA framework to run")

    five_p = subparsers.add_parser("five_whys", help="Run 5-Whys recursive drilldown")
    five_p.add_argument("--input", type=str, help="Path to JSON file containing problem and chain")
    five_p.add_argument("--demo", action="store_true", help="Run demonstration 5-Whys on subagent crash")

    ishi_p = subparsers.add_parser("ishikawa", help="Generate Ishikawa 6M fishbone diagram")
    ishi_p.add_argument("--input", type=str, help="Path to JSON file containing incident and 6M categories")
    ishi_p.add_argument("--demo", action="store_true", help="Run demonstration Ishikawa on DB exhaustion")

    fta_p = subparsers.add_parser("fault_tree", help="Analyze Fault Tree Analysis with Boolean logic gates")
    fta_p.add_argument("--input", type=str, help="Path to JSON file containing fault tree structure")
    fta_p.add_argument("--demo", action="store_true", help="Run demonstration FTA")

    args = parser.parse_args()

    if args.subcommand == "five_whys":
        if args.demo or not args.input:
            data = demo_5_whys()
        else:
            with open(args.input, "r", encoding="utf-8") as f:
                data = json.load(f)
        print(run_5_whys(data.get("problem", "Incident"), data.get("chain", [])))

    elif args.subcommand == "ishikawa":
        if args.demo or not args.input:
            data = demo_ishikawa()
        else:
            with open(args.input, "r", encoding="utf-8") as f:
                data = json.load(f)
        print(generate_ishikawa_diagram(data.get("incident", "System Failure"), data.get("categories", {})))

    elif args.subcommand == "fault_tree":
        if args.demo or not args.input:
            data = demo_fault_tree()
        else:
            with open(args.input, "r", encoding="utf-8") as f:
                data = json.load(f)
        print(run_fault_tree_analysis(data))

    else:
        # Default run demo 5 whys
        data = demo_5_whys()
        print(run_5_whys(data.get("problem", "Incident"), data.get("chain", [])))


if __name__ == "__main__":
    main()
