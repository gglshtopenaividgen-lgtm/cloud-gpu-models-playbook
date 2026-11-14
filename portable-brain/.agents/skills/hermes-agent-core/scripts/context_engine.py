#!/usr/bin/env python3
"""
ContextEngine: Progressive Context Compactor
Implements AST-aware structural pruning, tool output deduplication, and invariant preservation for long-horizon agent workflows.
"""

import ast
import json
import re
from typing import Any, Dict, List, Set, Tuple


class ContextEngine:
    def __init__(self, token_budget: int = 160000, target_reduction: float = 0.75):
        self.token_budget = token_budget
        self.target_reduction = target_reduction
        self.hard_invariants: Dict[str, Any] = {}

    def audit_tokens(self, messages: List[Dict[str, Any]]) -> int:
        raw_chars = sum(len(str(m.get("content", ""))) for m in messages)
        return raw_chars // 4

    def extract_and_lock_invariants(self, system_prompt: str, user_instructions: str) -> None:
        patterns = [
            r"(never\s+use\s+[^\.\n]+)",
            r"(do\s+not\s+[^\.\n]+)",
            r"(must\s+strictly\s+[^\.\n]+)",
            r"([A-Z0-9_]+_POLICY\s*:\s*[^\.\n]+)",
            r"(port\s*=\s*\d+)",
        ]
        combined = f"{system_prompt}\n{user_instructions}"
        for p in patterns:
            matches = re.findall(p, combined, re.IGNORECASE)
            for m in matches:
                key = m.strip().split()[0].upper()
                self.hard_invariants[key] = m.strip()

    def prune_python_ast(self, code_str: str) -> str:
        try:
            tree = ast.parse(code_str)
        except SyntaxError:
            return code_str

        class SignatureTransformer(ast.NodeTransformer):
            def visit_FunctionDef(self, node):
                docstring = ast.get_docstring(node)
                new_body = []
                if docstring:
                    new_body.append(ast.Expr(value=ast.Constant(value=docstring)))
                new_body.append(ast.Pass())
                node.body = new_body
                return node

            def visit_AsyncFunctionDef(self, node):
                return self.visit_FunctionDef(node)

        pruned_tree = SignatureTransformer().visit(tree)
        ast.fix_missing_locations(pruned_tree)
        return ast.unparse(pruned_tree)

    def prune_tool_outputs(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen_reads: Set[str] = set()
        sanitized = []

        for msg in reversed(messages):
            if msg.get("role") in ("tool", "system") or msg.get("source") == "SYSTEM":
                content = str(msg.get("content", ""))

                file_match = re.search(r"(?:Reading file|File Path):\s*[`\"]?([\w\.\/\:\\]+)", content)
                if file_match:
                    file_path = file_match.group(1)
                    if file_path in seen_reads:
                        msg = {
                            **msg,
                            "content": f"[Tool Output Pruned: Superseded by newer read of {file_path}]"
                        }
                    else:
                        seen_reads.add(file_path)

                if len(content) > 1200:
                    head = content[:300]
                    tail = content[-300:]
                    msg = {
                        **msg,
                        "content": f"{head}\n\n[... {len(content) - 600} characters omitted by ContextEngine ...]\n\n{tail}"
                    }
            sanitized.append(msg)
        return list(reversed(sanitized))

    def compact(
        self, messages: List[Dict[str, Any]], system_prompt: str, recency_window: int = 8
    ) -> Tuple[List[Dict[str, Any]], str]:
        first_content = messages[0].get("content", "") if messages else ""
        self.extract_and_lock_invariants(system_prompt, first_content)
        initial_tokens = self.audit_tokens(messages)

        if initial_tokens < (self.token_budget * 0.75):
            return messages, "NO_COMPACTION_REQUIRED"

        if len(messages) <= recency_window:
            return messages, "TRANSCRIPT_TOO_SHORT_FOR_WINDOW"

        historical_messages = messages[:-recency_window]
        recency_buffer = messages[-recency_window:]

        filtered_history = self.prune_tool_outputs(historical_messages)

        for msg in filtered_history:
            content = msg.get("content", "")
            code_blocks = re.findall(r"```python(.*?)```", content, re.DOTALL)
            for block in code_blocks:
                pruned_block = self.prune_python_ast(block)
                content = content.replace(block, f"\n{pruned_block}\n")
            msg["content"] = content

        condensed_summary = {
            "epoch_turns_compacted": len(historical_messages),
            "enforced_invariants": self.hard_invariants,
            "operational_status": "Progressive compaction executed successfully.",
            "compacted_nodes_count": len(filtered_history)
        }

        distilled_message = {
            "role": "user",
            "content": (
                "### CONTEXT_ENGINE: PROGRESSIVE COMPACTION SUMMARY\n"
                f"```json\n{json.dumps(condensed_summary, indent=2)}\n```\n"
                "Continue execution honoring all preserved invariants."
            )
        }
        distilled_ack = {
            "role": "assistant",
            "content": "Compacted history acknowledged. All hard constraints and invariant parameters loaded into memory."
        }

        re_injected = [distilled_message, distilled_ack] + recency_buffer
        final_tokens = self.audit_tokens(re_injected)
        reduction_achieved = (initial_tokens - final_tokens) / initial_tokens if initial_tokens > 0 else 0
        status_report = (
            f"Compaction Complete: {initial_tokens} -> {final_tokens} tokens "
            f"({reduction_achieved:.1%} reduction). "
            f"Preserved {len(self.hard_invariants)} hard invariants."
        )
        return re_injected, status_report
