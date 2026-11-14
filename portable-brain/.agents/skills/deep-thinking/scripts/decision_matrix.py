#!/usr/bin/env python3
"""
decision_matrix.py - Decision Engineering & Multi-Criteria Decision Analysis (MCDA) CLI Tool
Autonomous AI Cognitive System | Deep Thinking Universal Skill

Capabilities:
1. Multi-Criteria Decision Analysis (WSM & TOPSIS algorithms).
2. Pareto Frontier Detection (Identifies non-dominated architectural options).
3. Failure Mode and Effects Analysis (FMEA) with Risk Priority Number (RPN) scoring.
4. Trilemma Trade-Off Matrix (Latency vs Cost vs Quality) generator.
"""

import sys
import json
import math
import argparse
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple


@dataclass
class Criterion:
    name: str
    weight: float
    is_benefit: bool = True  # True: higher is better; False: lower is better (cost/latency)


@dataclass
class Alternative:
    name: str
    scores: Dict[str, float]


def normalize_weights(criteria: List[Criterion]) -> List[Criterion]:
    total_weight = sum(c.weight for c in criteria)
    if total_weight <= 0:
        raise ValueError("Total criteria weight must be > 0")
    return [Criterion(name=c.name, weight=c.weight / total_weight, is_benefit=c.is_benefit) for c in criteria]


def compute_wsm(alternatives: List[Alternative], criteria: List[Criterion]) -> Dict[str, float]:
    """Weighted Sum Model with min-max normalization."""
    criteria = normalize_weights(criteria)
    results = {}
    
    # Compute min and max for each criterion
    crit_bounds = {}
    for c in criteria:
        vals = [alt.scores.get(c.name, 0.0) for alt in alternatives]
        min_v = min(vals) if vals else 0.0
        max_v = max(vals) if vals else 1.0
        crit_bounds[c.name] = (min_v, max_v)
        
    for alt in alternatives:
        total = 0.0
        for c in criteria:
            val = alt.scores.get(c.name, 0.0)
            min_v, max_v = crit_bounds[c.name]
            span = max_v - min_v
            
            if span == 0:
                norm_score = 1.0
            elif c.is_benefit:
                norm_score = (val - min_v) / span
            else:
                norm_score = (max_v - val) / span
                
            total += c.weight * norm_score
        results[alt.name] = round(total, 4)
        
    return results


def compute_topsis(alternatives: List[Alternative], criteria: List[Criterion]) -> Dict[str, float]:
    """TOPSIS (Technique for Order Preference by Similarity to Ideal Solution)."""
    criteria = normalize_weights(criteria)
    m = len(alternatives)
    if m == 0:
        return {}
        
    # 1. Vector normalization denominator
    denoms = {}
    for c in criteria:
        sum_sq = sum(alt.scores.get(c.name, 0.0) ** 2 for alt in alternatives)
        denoms[c.name] = math.sqrt(sum_sq) if sum_sq > 0 else 1.0
        
    # 2. Weighted normalized matrix
    v_matrix = {alt.name: {} for alt in alternatives}
    for alt in alternatives:
        for c in criteria:
            raw = alt.scores.get(c.name, 0.0)
            norm = raw / denoms[c.name]
            v_matrix[alt.name][c.name] = norm * c.weight
            
    # 3. Ideal positive (A+) and negative (A-) solutions
    ideal_pos = {}
    ideal_neg = {}
    for c in criteria:
        vals = [v_matrix[alt.name][c.name] for alt in alternatives]
        if c.is_benefit:
            ideal_pos[c.name] = max(vals)
            ideal_neg[c.name] = min(vals)
        else:
            ideal_pos[c.name] = min(vals)
            ideal_neg[c.name] = max(vals)
            
    # 4. Separation measures & Closeness
    closeness = {}
    for alt in alternatives:
        d_pos = math.sqrt(sum((v_matrix[alt.name][c.name] - ideal_pos[c.name]) ** 2 for c in criteria))
        d_neg = math.sqrt(sum((v_matrix[alt.name][c.name] - ideal_neg[c.name]) ** 2 for c in criteria))
        
        if (d_pos + d_neg) == 0:
            closeness[alt.name] = 0.5
        else:
            closeness[alt.name] = round(d_neg / (d_pos + d_neg), 4)
            
    return closeness


def find_pareto_frontier(alternatives: List[Alternative], criteria: List[Criterion]) -> List[str]:
    """Identifies non-dominated alternatives on the Pareto Frontier."""
    dominated = set()
    
    for i, a in enumerate(alternatives):
        for j, b in enumerate(alternatives):
            if i == j:
                continue
            # Check if b dominates a
            better_or_equal = True
            strictly_better = False
            
            for c in criteria:
                val_a = a.scores.get(c.name, 0.0)
                val_b = b.scores.get(c.name, 0.0)
                
                if c.is_benefit:
                    if val_b < val_a:
                        better_or_equal = False
                        break
                    elif val_b > val_a:
                        strictly_better = True
                else:
                    if val_b > val_a:
                        better_or_equal = False
                        break
                    elif val_b < val_a:
                        strictly_better = True
                        
            if better_or_equal and strictly_better:
                dominated.add(a.name)
                break
                
    return [a.name for a in alternatives if a.name not in dominated]


def run_mcda_analysis(data: Dict[str, Any]) -> Dict[str, Any]:
    criteria = [
        Criterion(
            name=c["name"],
            weight=float(c.get("weight", 1.0)),
            is_benefit=bool(c.get("is_benefit", True))
        )
        for c in data.get("criteria", [])
    ]
    
    alternatives = [
        Alternative(
            name=a["name"],
            scores={k: float(v) for k, v in a.get("scores", {}).items()}
        )
        for a in data.get("alternatives", [])
    ]
    
    wsm_scores = compute_wsm(alternatives, criteria)
    topsis_scores = compute_topsis(alternatives, criteria)
    pareto_frontier = find_pareto_frontier(alternatives, criteria)
    
    # Combined ranking
    ranking = []
    for a in alternatives:
        is_pareto = a.name in pareto_frontier
        wsm = wsm_scores.get(a.name, 0.0)
        topsis = topsis_scores.get(a.name, 0.0)
        composite = round(0.5 * wsm + 0.5 * topsis, 4)
        ranking.append({
            "name": a.name,
            "wsm_score": wsm,
            "topsis_score": topsis,
            "composite_score": composite,
            "pareto_optimal": is_pareto
        })
        
    ranking.sort(key=lambda x: x["composite_score"], reverse=True)
    for rank_idx, item in enumerate(ranking, 1):
        item["rank"] = rank_idx
        
    return {
        "title": data.get("title", "MCDA Decision Matrix"),
        "ranking": ranking,
        "pareto_frontier": pareto_frontier,
        "criteria": [{"name": c.name, "weight": c.weight, "is_benefit": c.is_benefit} for c in normalize_weights(criteria)]
    }


def format_mcda_markdown(result: Dict[str, Any]) -> str:
    lines = []
    lines.append(f"# {result['title']}")
    lines.append("")
    lines.append("## Criteria Weights & Attributes")
    lines.append("| Criterion | Normalized Weight | Optimization Target |")
    lines.append("|---|---|---|")
    for c in result["criteria"]:
        target = "Maximize (Benefit)" if c["is_benefit"] else "Minimize (Cost/Latency)"
        lines.append(f"| **{c['name']}** | {c['weight']:.2%} | {target} |")
    lines.append("")
    lines.append("## Ranked Alternatives")
    lines.append("| Rank | Alternative | Composite | WSM Score | TOPSIS Closeness | Pareto Frontier |")
    lines.append("|---|---|---|---|---|---|")
    for r in result["ranking"]:
        pareto_badge = "✅ Non-Dominated" if r["pareto_optimal"] else "❌ Dominated"
        lines.append(f"| #{r['rank']} | **{r['name']}** | **{r['composite_score']:.4f}** | {r['wsm_score']:.4f} | {r['topsis_score']:.4f} | {pareto_badge} |")
    lines.append("")
    lines.append(f"> **Top Recommendation**: `{result['ranking'][0]['name']}` (Composite: {result['ranking'][0]['composite_score']:.4f})")
    return "\n".join(lines)


# -------------------------------------------------------------
# FMEA: Failure Mode and Effects Analysis
# -------------------------------------------------------------

@dataclass
class FailureMode:
    failure_mode: str
    component: str
    potential_cause: str
    severity: int     # 1-10
    occurrence: int   # 1-10
    detection: int    # 1-10 (10 = hardest to detect)
    recommended_action: str

    @property
    def rpn(self) -> int:
        return self.severity * self.occurrence * self.detection

    @property
    def risk_level(self) -> str:
        if self.rpn >= 200 or self.severity >= 9:
            return "CRITICAL"
        elif self.rpn >= 120:
            return "HIGH"
        elif self.rpn >= 60:
            return "MEDIUM"
        else:
            return "LOW"


def run_fmea_analysis(modes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    analyzed = []
    for m in modes:
        fm = FailureMode(
            failure_mode=m["failure_mode"],
            component=m.get("component", "System"),
            potential_cause=m.get("potential_cause", "Unspecified"),
            severity=int(m.get("severity", 5)),
            occurrence=int(m.get("occurrence", 5)),
            detection=int(m.get("detection", 5)),
            recommended_action=m.get("recommended_action", "Implement defensive guardrail")
        )
        analyzed.append({
            "failure_mode": fm.failure_mode,
            "component": fm.component,
            "potential_cause": fm.potential_cause,
            "severity": fm.severity,
            "occurrence": fm.occurrence,
            "detection": fm.detection,
            "rpn": fm.rpn,
            "risk_level": fm.risk_level,
            "recommended_action": fm.recommended_action
        })
    analyzed.sort(key=lambda x: x["rpn"], reverse=True)
    return analyzed


def format_fmea_markdown(fmea_results: List[Dict[str, Any]]) -> str:
    lines = []
    lines.append("# Failure Mode and Effects Analysis (FMEA)")
    lines.append("")
    lines.append("| Component | Failure Mode | Cause | S | O | D | RPN | Level | Mandatory Mitigation |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in fmea_results:
        level_icon = "🛑" if r["risk_level"] == "CRITICAL" else ("⚠️" if r["risk_level"] == "HIGH" else "ℹ️")
        lines.append(f"| `{r['component']}` | {r['failure_mode']} | {r['potential_cause']} | {r['severity']} | {r['occurrence']} | {r['detection']} | **{r['rpn']}** | {level_icon} {r['risk_level']} | {r['recommended_action']} |")
    lines.append("")
    critical_count = sum(1 for r in fmea_results if r["risk_level"] == "CRITICAL")
    lines.append(f"> [!IMPORTANT]\n> Total Identified Risks: {len(fmea_results)} | Critical Blockers (RPN >= 200 or S >= 9): **{critical_count}**")
    return "\n".join(lines)


# -------------------------------------------------------------
# Trilemma Trade-Off Matrix
# -------------------------------------------------------------

def generate_trilemma_matrix(archetypes: List[Dict[str, Any]]) -> str:
    lines = []
    lines.append("# Trilemma Trade-Off Matrix: Latency vs. Cost vs. Quality")
    lines.append("")
    lines.append("| Architecture Option | Latency Profile | Cost Profile | Quality / Consistency | Pareto Niche |")
    lines.append("|---|---|---|---|---|")
    for arch in archetypes:
        lines.append(f"| **{arch['name']}** | {arch.get('latency', 'N/A')} | {arch.get('cost', 'N/A')} | {arch.get('quality', 'N/A')} | *{arch.get('niche', 'General')}* |")
    lines.append("")
    return "\n".join(lines)


# -------------------------------------------------------------
# CLI Interface & Demonstration
# -------------------------------------------------------------

def demo_mcda_data() -> Dict[str, Any]:
    return {
        "title": "Architectural Evaluation: RAG Vector Store & Context Routing",
        "criteria": [
            {"name": "query_latency_ms", "weight": 0.25, "is_benefit": False},
            {"name": "free_tier_sustainability", "weight": 0.35, "is_benefit": True},
            {"name": "vector_recall_accuracy", "weight": 0.25, "is_benefit": True},
            {"name": "operational_simplicity", "weight": 0.15, "is_benefit": True}
        ],
        "alternatives": [
            {
                "name": "Azure PostgreSQL Flexible (pgvector Standard_B1ms)",
                "scores": {"query_latency_ms": 18.0, "free_tier_sustainability": 9.5, "vector_recall_accuracy": 9.0, "operational_simplicity": 8.0}
            },
            {
                "name": "Cloudflare Vectorize + Workers",
                "scores": {"query_latency_ms": 8.0, "free_tier_sustainability": 8.0, "vector_recall_accuracy": 7.5, "operational_simplicity": 8.5}
            },
            {
                "name": "Supabase pgvector (Free Tier 500MB)",
                "scores": {"query_latency_ms": 25.0, "free_tier_sustainability": 4.0, "vector_recall_accuracy": 8.5, "operational_simplicity": 9.0}
            },
            {
                "name": "Dedicated VM Milvus / Qdrant",
                "scores": {"query_latency_ms": 5.0, "free_tier_sustainability": 2.0, "vector_recall_accuracy": 9.8, "operational_simplicity": 3.0}
            }
        ]
    }


def demo_fmea_data() -> List[Dict[str, Any]]:
    return [
        {
            "component": "Subagent Invocation",
            "failure_mode": "Missing 'skill_search' tool in registry causing 1s crash",
            "potential_cause": "Calling TypeName='DeepCoder' or 'DeepInvestigator' in language_server.exe runtime",
            "severity": 10,
            "occurrence": 9,
            "detection": 2,
            "recommended_action": "Strict invariant: Mandate TypeName='self' for all engineering subagents"
        },
        {
            "component": "Database Storage",
            "failure_mode": "Supabase 500MB quota exhaustion and instance suspension",
            "potential_cause": "Writing rich-text AST documents or large binary payloads into Supabase tables",
            "severity": 9,
            "occurrence": 7,
            "detection": 3,
            "recommended_action": "Strict 3-tier boundary: All documents/PDFs/ASTs stored exclusively in Cloudflare R2"
        },
        {
            "component": "Cloud VM Networking",
            "failure_mode": "Azure billing surprise from Public IPv4 addresses",
            "potential_cause": "Allocating public IP instead of Cloudflare Tunnel routing",
            "severity": 8,
            "occurrence": 5,
            "detection": 4,
            "recommended_action": "Enforce 0 public IP policy; connect via persistent Cloudflare Tunnel daemon"
        },
        {
            "component": "Context Compaction",
            "failure_mode": "Critical architectural decisions lost during conversational pruning",
            "potential_cause": "Unbounded conversation history compacted without SQLite memory flush",
            "severity": 7,
            "occurrence": 6,
            "detection": 5,
            "recommended_action": "Trigger session_flush.py before context compaction; log to ideas.md and hermes db"
        }
    ]


def main():
    parser = argparse.ArgumentParser(description="Decision Engineering & MCDA CLI Tool for AI Agents")
    subparsers = parser.add_subparsers(dest="subcommand", help="Subcommand to execute")

    # MCDA subcommand
    mcda_parser = subparsers.add_parser("score", help="Score alternatives using MCDA (WSM + TOPSIS + Pareto)")
    mcda_parser.add_argument("--input", type=str, help="Path to input JSON file containing criteria and alternatives")
    mcda_parser.add_argument("--json", action="store_true", help="Output raw JSON instead of Markdown")
    mcda_parser.add_argument("--demo", action="store_true", help="Run with demonstration architectural data")

    # FMEA subcommand
    fmea_parser = subparsers.add_parser("fmea", help="Analyze failure modes using FMEA (RPN calculation)")
    fmea_parser.add_argument("--input", type=str, help="Path to input JSON file containing failure modes")
    fmea_parser.add_argument("--json", action="store_true", help="Output raw JSON instead of Markdown")
    fmea_parser.add_argument("--demo", action="store_true", help="Run with demonstration system failure modes")

    # Tradeoff subcommand
    tradeoff_parser = subparsers.add_parser("tradeoff", help="Generate 3-way Trilemma Trade-Off Matrix")
    tradeoff_parser.add_argument("--input", type=str, help="Path to input JSON file containing archetypes")

    args = parser.parse_args()

    if args.subcommand == "score":
        if args.demo or not args.input:
            data = demo_mcda_data()
        else:
            with open(args.input, "r", encoding="utf-8") as f:
                data = json.load(f)
        result = run_mcda_analysis(data)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(format_mcda_markdown(result))

    elif args.subcommand == "fmea":
        if args.demo or not args.input:
            modes = demo_fmea_data()
        else:
            with open(args.input, "r", encoding="utf-8") as f:
                modes = json.load(f)
        results = run_fmea_analysis(modes)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(format_fmea_markdown(results))

    elif args.subcommand == "tradeoff":
        if args.input:
            with open(args.input, "r", encoding="utf-8") as f:
                archetypes = json.load(f)
        else:
            archetypes = [
                {"name": "Serverless (Cloudflare Worker + R2)", "latency": "Ultra-Low (Edge <15ms)", "cost": "$0 / 100% Free Tier", "quality": "Stateless, High Availability", "niche": "Front-facing APIs & static media"},
                {"name": "Managed DB (Azure Flexible PG B1ms)", "latency": "Low (~20ms intra-region)", "cost": "$0 (750h free/mo)", "quality": "Full ACID, pgvector RAG", "niche": "Primary relational taxonomy"},
                {"name": "Heavy Background Worker (VM2 Python)", "latency": "Batch (seconds to min)", "cost": "$0 (Azure 0-IP Tunnel)", "quality": "Unconstrained CPU/Disk pipeline", "niche": "Long-running ingestion"}
            ]
        print(generate_trilemma_matrix(archetypes))
    else:
        # If no subcommand, print demo MCDA
        print("Executing default MCDA Score Demonstration:\n")
        data = demo_mcda_data()
        result = run_mcda_analysis(data)
        print(format_mcda_markdown(result))


if __name__ == "__main__":
    main()
