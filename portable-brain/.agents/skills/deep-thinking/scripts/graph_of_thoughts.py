#!/usr/bin/env python3
"""
Graph-of-Thoughts (GoT) Cognitive Reasoning Engine
Part of the deep-thinking universal powerhouse.
Inspired by ETH Zurich's Graph-of-Thoughts (spcl/graph-of-thoughts) and Princeton's Tree-of-Thoughts.

Enables non-linear, multi-perspective agent reasoning:
1. Thought Generation & Branching (Tree-of-Thoughts exploration).
2. Thought Aggregation & Synthesis (combining distinct complementary ideas).
3. Thought Refinement & Critique (iterative self-correction).
4. Multi-Criteria Scoring & Pareto Frontier Selection.
5. Mermaid Flowchart DAG export for visual artifact rendering.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Set, Tuple


class OperationType(str, Enum):
    GENERATE = "GENERATE"
    AGGREGATE = "AGGREGATE"
    REFINE = "REFINE"
    BACKTRACK = "BACKTRACK"
    ROOT = "ROOT"


@dataclass
class ThoughtNode:
    id: str
    text: str
    operation: OperationType
    parent_ids: List[str] = field(default_factory=list)
    child_ids: List[str] = field(default_factory=list)
    depth: int = 0
    scores: Dict[str, float] = field(default_factory=dict)  # e.g. feasibility, performance, cost, risk
    overall_score: float = 0.0
    status: str = "ACTIVE"  # ACTIVE, PRUNED, PARETO_OPTIMAL, SELECTED
    critique_notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def compute_overall_score(self, weights: Optional[Dict[str, float]] = None) -> float:
        if not self.scores:
            return self.overall_score
        if not weights:
            # Equal weight default
            self.overall_score = sum(self.scores.values()) / len(self.scores)
        else:
            total_w = sum(weights.get(k, 1.0) for k in self.scores)
            weighted_sum = sum(v * weights.get(k, 1.0) for k, v in self.scores.items())
            self.overall_score = weighted_sum / total_w if total_w > 0 else 0.0
        return self.overall_score


class GraphOfThoughts:
    """
    Manages a directed acyclic graph (DAG) of thoughts, enabling multi-path exploration,
    aggregation of divergent ideas, pruning of suboptimal thoughts, and synthesis.
    """

    def __init__(self, problem_statement: str):
        self.problem_statement = problem_statement
        self.nodes: Dict[str, ThoughtNode] = {}
        self.node_counter = 0

        # Create root node
        root_node = self._create_node(
            text=f"Problem: {problem_statement}",
            operation=OperationType.ROOT,
            parent_ids=[],
            depth=0,
        )
        self.root_id = root_node.id

    def _create_node(
        self,
        text: str,
        operation: OperationType,
        parent_ids: List[str],
        depth: int,
        scores: Optional[Dict[str, float]] = None,
        critique: str = "",
    ) -> ThoughtNode:
        self.node_counter += 1
        node_id = f"T{self.node_counter:03d}"
        node = ThoughtNode(
            id=node_id,
            text=text,
            operation=operation,
            parent_ids=parent_ids,
            depth=depth,
            scores=scores or {},
            critique_notes=critique,
        )
        node.compute_overall_score()
        self.nodes[node_id] = node

        # Update parents
        for pid in parent_ids:
            if pid in self.nodes and node_id not in self.nodes[pid].child_ids:
                self.nodes[pid].child_ids.append(node_id)

        return node

    def generate(self, parent_id: str, candidate_texts: List[str]) -> List[ThoughtNode]:
        """Branches multiple candidate thoughts from an existing parent node."""
        if parent_id not in self.nodes:
            raise KeyError(f"Parent node {parent_id} not found.")

        parent = self.nodes[parent_id]
        new_nodes = []
        for text in candidate_texts:
            node = self._create_node(
                text=text,
                operation=OperationType.GENERATE,
                parent_ids=[parent_id],
                depth=parent.depth + 1,
            )
            new_nodes.append(node)
        return new_nodes

    def aggregate(self, parent_ids: List[str], synthesized_text: str) -> ThoughtNode:
        """Aggregates multiple divergent thoughts into a combined synergistic thought."""
        for pid in parent_ids:
            if pid not in self.nodes:
                raise KeyError(f"Parent node {pid} not found.")

        max_depth = max(self.nodes[pid].depth for pid in parent_ids)
        node = self._create_node(
            text=synthesized_text,
            operation=OperationType.AGGREGATE,
            parent_ids=parent_ids,
            depth=max_depth + 1,
        )
        return node

    def refine(self, node_id: str, critique: str, improved_text: str) -> ThoughtNode:
        """Refines a thought node by addressing specific critiques."""
        if node_id not in self.nodes:
            raise KeyError(f"Target node {node_id} not found.")

        target = self.nodes[node_id]
        refined = self._create_node(
            text=improved_text,
            operation=OperationType.REFINE,
            parent_ids=[node_id],
            depth=target.depth + 1,
            critique=critique,
        )
        return refined

    def score_node(self, node_id: str, scores: Dict[str, float], weights: Optional[Dict[str, float]] = None) -> float:
        """Applies multi-criteria scores (0-10) to a thought node."""
        if node_id not in self.nodes:
            raise KeyError(f"Node {node_id} not found.")
        node = self.nodes[node_id]
        node.scores.update(scores)
        return node.compute_overall_score(weights)

    def prune_suboptimal(self, threshold_score: float = 5.0) -> List[str]:
        """Prunes nodes whose overall score is strictly below the threshold."""
        pruned_ids = []
        for nid, node in self.nodes.items():
            if node.operation != OperationType.ROOT and node.overall_score < threshold_score and node.scores:
                node.status = "PRUNED"
                pruned_ids.append(nid)
        return pruned_ids

    def find_pareto_frontier(self, dim1: str = "feasibility", dim2: str = "performance") -> List[ThoughtNode]:
        """
        Finds the Pareto-optimal frontier of thoughts maximizing two dimensions
        (e.g. feasibility vs performance).
        """
        candidates = [n for n in self.nodes.values() if n.status != "PRUNED" and dim1 in n.scores and dim2 in n.scores]
        pareto: List[ThoughtNode] = []

        for p in candidates:
            is_dominated = False
            for other in candidates:
                if other.id == p.id:
                    continue
                # other dominates p if other is >= in all and strictly > in at least one
                if (other.scores[dim1] >= p.scores[dim1] and other.scores[dim2] >= p.scores[dim2]) and (
                    other.scores[dim1] > p.scores[dim1] or other.scores[dim2] > p.scores[dim2]
                ):
                    is_dominated = True
                    break
            if not is_dominated:
                p.status = "PARETO_OPTIMAL"
                pareto.append(p)

        return pareto

    def export_mermaid(self) -> str:
        """Generates a Mermaid flowchart diagram visualizing the entire reasoning DAG."""
        lines = ["flowchart TD"]

        # Styles
        lines.append("    classDef rootStyle fill:#1e1b4b,stroke:#818cf8,stroke-width:2px,color:#fff;")
        lines.append("    classDef genStyle fill:#0f172a,stroke:#38bdf8,stroke-width:1px,color:#fff;")
        lines.append("    classDef aggStyle fill:#14532d,stroke:#4ade80,stroke-width:2px,color:#fff;")
        lines.append("    classDef refStyle fill:#701a75,stroke:#f472b6,stroke-width:1px,color:#fff;")
        lines.append("    classDef pruneStyle fill:#334155,stroke:#64748b,stroke-width:1px,stroke-dasharray: 5 5,color:#94a3b8;")
        lines.append("    classDef paretoStyle fill:#854d0e,stroke:#facc15,stroke-width:3px,color:#fff;")

        for nid, node in self.nodes.items():
            label = f"<b>{node.id}</b> [{node.operation.value}]<br/>"
            clean_text = node.text[:55].replace('"', "'") + ("..." if len(node.text) > 55 else "")
            label += clean_text
            if node.scores:
                label += f"<br/>Score: <b>{node.overall_score:.1f}</b>"

            lines.append(f'    {nid}["{label}"]')

            # Apply style class
            if node.status == "PARETO_OPTIMAL":
                lines.append(f"    class {nid} paretoStyle;")
            elif node.status == "PRUNED":
                lines.append(f"    class {nid} pruneStyle;")
            elif node.operation == OperationType.ROOT:
                lines.append(f"    class {nid} rootStyle;")
            elif node.operation == OperationType.AGGREGATE:
                lines.append(f"    class {nid} aggStyle;")
            elif node.operation == OperationType.REFINE:
                lines.append(f"    class {nid} refStyle;")
            else:
                lines.append(f"    class {nid} genStyle;")

            for child_id in node.child_ids:
                lines.append(f"    {nid} --> {child_id}")

        return "\n".join(lines)

    def export_json(self) -> str:
        data = {
            "problem": self.problem_statement,
            "nodes": {
                nid: {
                    "id": n.id,
                    "text": n.text,
                    "operation": n.operation.value,
                    "depth": n.depth,
                    "parent_ids": n.parent_ids,
                    "child_ids": n.child_ids,
                    "scores": n.scores,
                    "overall_score": round(n.overall_score, 2),
                    "status": n.status,
                    "critique": n.critique_notes,
                }
                for nid, n in self.nodes.items()
            }
        }
        return json.dumps(data, indent=2)


def demo_sample_run():
    print("[*] Running Graph-of-Thoughts (GoT) Architectural Reasoning Demo...")
    problem = "Architect a high-concurrency background audio transcoding engine on 100% Free Tier"
    got = GraphOfThoughts(problem)

    # 1. Branch 3 candidate approaches
    branches = got.generate(got.root_id, [
        "Approach A: WebAssembly ffmpeg in client browser (Zero cloud compute cost, heavy client CPU)",
        "Approach B: Cloudflare Workers + WebAssembly ffmpeg edge functions (Sub-30s limits)",
        "Approach C: Ephemeral Azure VM-2 Python Celery worker via Cloudflare Tunnel (Free B1ms, isolated)",
    ])

    got.score_node(branches[0].id, {"feasibility": 8.0, "performance": 6.5, "cost": 10.0, "risk": 4.0})
    got.score_node(branches[1].id, {"feasibility": 5.0, "performance": 8.0, "cost": 9.5, "risk": 8.0})
    got.score_node(branches[2].id, {"feasibility": 9.0, "performance": 8.5, "cost": 9.0, "risk": 3.0})

    # 2. Refine Approach A
    refined_a = got.refine(
        branches[0].id,
        critique="Client browser crashes on large files (>100MB). Needs chunked streaming.",
        improved_text="Approach A2: Client WebAssembly ffmpeg with chunked ArrayBuffer streaming + WebWorker pool.",
    )
    got.score_node(refined_a.id, {"feasibility": 8.5, "performance": 8.0, "cost": 10.0, "risk": 3.5})

    # 3. Aggregate A2 + C (Hybrid Client-Cloud Transcoding)
    hybrid = got.aggregate(
        [refined_a.id, branches[2].id],
        synthesized_text="Approach D (Hybrid Synergistic): Client WebWorker Wasm for quick previews (<10MB); Azure VM-2 queue for bulk high-res audio.",
    )
    got.score_node(hybrid.id, {"feasibility": 9.5, "performance": 9.5, "cost": 9.5, "risk": 2.0})

    # 4. Find Pareto frontier
    pareto = got.find_pareto_frontier("feasibility", "performance")
    print(f"\n[+] Pareto Optimal Thoughts: {[p.id + ': ' + p.text[:40] for p in pareto]}")

    print("\n--- MERMAID FLOWCHART DIAGRAM ---")
    print(got.export_mermaid())


if __name__ == "__main__":
    demo_sample_run()
