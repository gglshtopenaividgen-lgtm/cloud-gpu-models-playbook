#!/usr/bin/env python3
"""
Structural AST Audit Engine (structural_ast_audit.py)
======================================================
Part of the exhaustive-audit-and-repair universal skill.

Performs static structural AST auditing against codebases to detect recurring
anti-patterns, security violations, and mobile ergonomic issues.

Execution Modes:
1. Native `ast-grep` (sg scan): If `sg` binary is found on PATH, delegates to
   ast-grep using `references/ast-grep-rules.yml`.
2. Python AST & Structural Fallback: If `sg` is unavailable, executes a high-speed,
   zero-dependency Python AST parse + structural tokenized scan across Python,
   TypeScript, JavaScript, PowerShell, and Markdown files.

Anti-Patterns Audited:
- CRITICAL: Subagent TypeName='DeepCoder' or 'DeepInvestigator' (1s crash defect)
- CRITICAL: Hardcoded API tokens, GitHub tokens, AWS keys, private credentials
- HIGH: Windows PowerShell '&&' chaining syntax hazards
- HIGH: Mobile touch targets < 44px on interactive elements (JSX/TSX/HTML)
- HIGH: Mobile horizontal overflow: fixed width > 375px without responsive prefix
- MEDIUM: Hardcoded localhost / 127.0.0.1 outside bridge & test infrastructure
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

DEFAULT_RULES_PATH = (
    Path(__file__).parent.parent / "references" / "ast-grep-rules.yml"
)

# Known files exempt from localhost warnings (e.g. bridge daemons, test configs)
EXEMPT_LOCALHOST_FILES = {
    "server.py",
    "consult_argon.py",
    "gemini_brain_driver.py",
    "profile_lock_manager.py",
    "aistudio_subagent.py",
    "browser_driver.py",
}


@dataclass
class Finding:
    file: str
    line: int
    column: int
    rule_id: str
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    message: str
    snippet: str


class FallbackStructuralScanner:
    """Zero-dependency structural scanner using Python ast and regex tokenization."""

    SECRET_PATTERNS = [
        (re.compile(r"""(?:sk_live|sk_test)_[0-9a-zA-Z]{24,}"""), "Stripe Secret Key"),
        (re.compile(r"""ghp_[0-9a-zA-Z]{36}"""), "GitHub Personal Access Token"),
        (re.compile(r"""AKIA[0-9A-Z]{16}"""), "AWS Access Key ID"),
        (re.compile(r"""-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"""), "Private Key Block"),
        (re.compile(r"""AIzaSy[0-9A-Za-z-_]{33}"""), "Google API Key"),
    ]

    DEEPCODER_PATTERN = re.compile(
        r"""(?:TypeName\s*[:=]\s*["'](?:DeepCoder|DeepInvestigator)["'])|(?:invoke_subagent\([^)]*["'](?:DeepCoder|DeepInvestigator)["'])""",
        re.IGNORECASE,
    )

    POWERSHELL_AND_PATTERN = re.compile(r"""(?:\bGet-\w+|\bSet-\w+|\bSelect-\w+|python|npm|npx|node)\s+.*?\s+&&\s+""")

    TOUCH_TARGET_PATTERN = re.compile(
        r"""<(?:button|a|input|Link)\b[^>]*className=["'][^"']*\b(h-[1-9]|h-10|min-h-\[(?:1[0-9]|2[0-9]|3[0-9]|4[0-3])px\])\b[^"']*["']""",
        re.IGNORECASE,
    )

    OVERFLOW_PATTERN = re.compile(
        r"""\b(?:w|min-w)-\[(?:3[8-9][0-9]|[4-9][0-9]{2}|[1-9][0-9]{3,})px\]\b"""
    )

    LOCALHOST_PATTERN = re.compile(
        r"""https?://(?:localhost|127\.0\.0\.1)(?::\d+)?""",
        re.IGNORECASE,
    )

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.findings: List[Finding] = []

    def scan_path(self, target: Path) -> List[Finding]:
        if target.is_file():
            self._scan_file(target)
        elif target.is_dir():
            for p in target.rglob("*"):
                # Skip version control, caches, node_modules, dist
                if any(part in p.parts for part in [".git", "__pycache__", "node_modules", ".next", "dist", "build", "ver_backup"]):
                    continue
                if p.is_file() and p.suffix.lower() in {
                    ".py", ".ts", ".tsx", ".js", ".jsx", ".ps1", ".sh", ".json", ".yml", ".yaml", ".md"
                }:
                    self._scan_file(p)
        return self.findings

    def _scan_file(self, file_path: Path) -> None:
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return

        lines = content.splitlines()
        rel_path = str(file_path.relative_to(self.root_dir) if file_path.is_relative_to(self.root_dir) else file_path)

        # 1. Python AST Scan for Python files
        if file_path.suffix.lower() == ".py":
            self._scan_python_ast(file_path, content, rel_path)

        # 2. Line-by-line Structural Regex Scan
        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped:
                continue

            # Check Defective Subagents
            # For Python files, rely cleanly on AST inspection (_scan_python_ast) to prevent false positives in docstrings/warnings.
            # For non-Python files, check regex but skip comments and explicit warning phrasing.
            if file_path.suffix.lower() != ".py":
                low_line = stripped.lower()
                is_comment = stripped.startswith(("#", "//", "*", "/*"))
                has_warning_phrase = any(
                    phrase in low_line
                    for phrase in (
                        "never invoke",
                        "ban-deepcoder",
                        "banned subagent",
                        "strictly prohibited",
                        "defective subagents",
                        "defect guard",
                    )
                )
                if not is_comment and not has_warning_phrase:
                    dc_match = self.DEEPCODER_PATTERN.search(line)
                    if dc_match:
                        self.findings.append(Finding(
                            file=rel_path,
                            line=idx,
                            column=dc_match.start() + 1,
                            rule_id="ban-deepcoder-subagent",
                            severity="CRITICAL",
                            message="Banned subagent TypeName='DeepCoder' or 'DeepInvestigator' causes 1s crash. Use TypeName='self' or 'research'.",
                            snippet=line.strip()[:100],
                        ))

            # Check Hardcoded Secrets
            for pat, sec_name in self.SECRET_PATTERNS:
                sec_match = pat.search(line)
                if sec_match:
                    # Ignore comment examples or mock keys
                    if "example" in line.lower() or "your_" in line.lower() or "<" in line:
                        continue
                    self.findings.append(Finding(
                        file=rel_path,
                        line=idx,
                        column=sec_match.start() + 1,
                        rule_id="hardcoded-secrets-tokens",
                        severity="CRITICAL",
                        message=f"Hardcoded credential detected ({sec_name}). Move to environment variables.",
                        snippet=line.strip()[:60] + "...",
                    ))

            # Check Windows PowerShell && chaining
            if file_path.suffix.lower() in {".ps1", ".py", ".md", ".sh"}:
                if "powershell" in content.lower() or file_path.suffix.lower() == ".ps1":
                    and_match = self.POWERSHELL_AND_PATTERN.search(line)
                    if and_match:
                        self.findings.append(Finding(
                            file=rel_path,
                            line=idx,
                            column=and_match.start() + 1,
                            rule_id="ban-windows-powershell-double-ampersand",
                            severity="HIGH",
                            message="Windows PowerShell '&&' chaining hazard. Use ';' or split commands.",
                            snippet=line.strip()[:100],
                        ))

            # Check Mobile Touch Target (< 44px)
            if file_path.suffix.lower() in {".tsx", ".jsx", ".html"}:
                tt_match = self.TOUCH_TARGET_PATTERN.search(line)
                if tt_match:
                    violating_class = tt_match.group(1)
                    if "min-h-[44px]" not in line and "min-h-[48px]" not in line:
                        self.findings.append(Finding(
                            file=rel_path,
                            line=idx,
                            column=tt_match.start() + 1,
                            rule_id="mobile-touch-target-min-44px",
                            severity="HIGH",
                            message=f"Interactive touch target ({violating_class}) is under 44px. Add 'min-h-[44px]'.",
                            snippet=line.strip()[:100],
                        ))

            # Check Mobile Viewport Overflow (> 375px)
            if file_path.suffix.lower() in {".tsx", ".jsx", ".html"}:
                ov_match = self.OVERFLOW_PATTERN.search(line)
                if ov_match:
                    # Allow responsive prefixes like md:w-[500px] or lg:min-w-[400px]
                    prefix_match = re.search(r"""\b(?:sm|md|lg|xl|2xl):""" + re.escape(ov_match.group(0)), line)
                    if not prefix_match:
                        self.findings.append(Finding(
                            file=rel_path,
                            line=idx,
                            column=ov_match.start() + 1,
                            rule_id="mobile-viewport-overflow",
                            severity="HIGH",
                            message=f"Fixed width '{ov_match.group(0)}' exceeds 375px mobile viewport without responsive prefix.",
                            snippet=line.strip()[:100],
                        ))

            # Check Hardcoded Localhost URLs
            if file_path.name not in EXEMPT_LOCALHOST_FILES and not file_path.name.startswith("test_"):
                lh_match = self.LOCALHOST_PATTERN.search(line)
                if lh_match and not line.strip().startswith("#") and not line.strip().startswith("//"):
                    self.findings.append(Finding(
                        file=rel_path,
                        line=idx,
                        column=lh_match.start() + 1,
                        rule_id="hardcoded-localhost-urls",
                        severity="MEDIUM",
                        message=f"Hardcoded loopback URL '{lh_match.group(0)}'. Use configuration or environment variables.",
                        snippet=line.strip()[:100],
                    ))

    def _scan_python_ast(self, file_path: Path, content: str, rel_path: str) -> None:
        """Parses Python AST for deep structural function calls and keyword arguments."""
        try:
            tree = ast.parse(content, filename=str(file_path))
        except SyntaxError:
            return

        for node in ast.walk(tree):
            # Check function calls for invoke_subagent(..., TypeName="DeepCoder")
            if isinstance(node, ast.Call):
                func_name = ""
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    func_name = node.func.attr

                if func_name in ("invoke_subagent", "spawn_subagent", "add_agent"):
                    for kw in node.keywords:
                        if kw.arg in ("TypeName", "type_name", "subagent_type"):
                            if isinstance(kw.value, ast.Constant) and str(kw.value.value) in ("DeepCoder", "DeepInvestigator"):
                                self.findings.append(Finding(
                                    file=rel_path,
                                    line=node.lineno,
                                    column=node.col_offset,
                                    rule_id="ban-deepcoder-subagent",
                                    severity="CRITICAL",
                                    message=f"AST call to {func_name} with forbidden subagent '{kw.value.value}'. Use 'self' or 'research'.",
                                    snippet=f"{func_name}(..., TypeName='{kw.value.value}')",
                                ))
                    for arg in node.args:
                        if isinstance(arg, ast.Constant) and str(arg.value) in ("DeepCoder", "DeepInvestigator"):
                            self.findings.append(Finding(
                                file=rel_path,
                                line=node.lineno,
                                column=node.col_offset,
                                rule_id="ban-deepcoder-subagent",
                                severity="CRITICAL",
                                message=f"AST call to {func_name} with forbidden subagent '{arg.value}'. Use 'self' or 'research'.",
                                snippet=f"{func_name}('{arg.value}', ...)",
                            ))


def run_ast_grep_scan(target_dir: Path, rules_path: Path) -> Optional[List[Finding]]:
    """Runs ast-grep CLI binary (sg) if available."""
    sg_bin = shutil.which("sg") or shutil.which("ast-grep")
    if not sg_bin:
        return None

    if not rules_path.exists():
        return None

    try:
        cmd = [sg_bin, "scan", "--rule", str(rules_path), "--json", str(target_dir)]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode not in (0, 1):
            return None

        data = json.loads(result.stdout or "[]")
        findings: List[Finding] = []
        for item in data:
            rule_id = item.get("ruleId", "ast-grep-finding")
            sev = "HIGH"
            if "deepcoder" in rule_id or "secret" in rule_id:
                sev = "CRITICAL"
            elif "localhost" in rule_id:
                sev = "MEDIUM"

            findings.append(Finding(
                file=item.get("file", ""),
                line=item.get("range", {}).get("start", {}).get("line", 0) + 1,
                column=item.get("range", {}).get("start", {}).get("column", 0) + 1,
                rule_id=rule_id,
                severity=sev,
                message=item.get("message", "Rule violation"),
                snippet=item.get("text", "")[:100],
            ))
        return findings
    except Exception:
        return None


def format_table(findings: List[Finding]) -> str:
    if not findings:
        return "✅ [Structural AST Audit] No structural violations detected! Codebase clean."

    lines = [
        "| Severity | File : Line | Rule ID | Message & Snippet |",
        "|:---|:---|:---|:---|",
    ]
    for f in findings:
        sev_badge = {
            "CRITICAL": "🛑 **CRITICAL**",
            "HIGH": "⚠️ **HIGH**",
            "MEDIUM": "⚡ **MEDIUM**",
            "LOW": "ℹ️ **LOW**",
        }.get(f.severity, f.severity)
        loc = f"`{f.file}:{f.line}`"
        msg = f"{f.message}<br>`{f.snippet}`"
        lines.append(f"| {sev_badge} | {loc} | `{f.rule_id}` | {msg} |")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Structural AST Code Auditor (ast-grep + Python AST engine)"
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Target directory or file path to audit (default: current directory)",
    )
    parser.add_argument(
        "--rules",
        "-r",
        default=str(DEFAULT_RULES_PATH),
        help="Path to ast-grep rules YAML file",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["table", "json", "markdown"],
        default="table",
        help="Output report format",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Optional path to write the output report",
    )
    parser.add_argument(
        "--fail-on-violation",
        action="store_true",
        help="Exit with code 1 if CRITICAL or HIGH findings exist",
    )
    args = parser.parse_args()

    target_path = Path(args.target).resolve()
    rules_path = Path(args.rules).resolve()

    if not target_path.exists():
        print(f"Error: Target path does not exist: {target_path}", file=sys.stderr)
        return 2

    # Attempt ast-grep execution first
    findings = run_ast_grep_scan(target_path, rules_path)
    engine_name = "ast-grep (sg binary)"

    # Fallback to Python AST + Structural Scanner
    if findings is None:
        scanner = FallbackStructuralScanner(root_dir=target_path if target_path.is_dir() else target_path.parent)
        findings = scanner.scan_path(target_path)
        engine_name = "Native Python AST + Structural Scanner (Zero-Dependency Fallback)"

    # Report Output
    if args.format == "json":
        output_str = json.dumps(
            {
                "engine": engine_name,
                "target": str(target_path),
                "total_findings": len(findings),
                "findings": [asdict(f) for f in findings],
            },
            indent=2,
        )
    else:
        output_str = f"# Structural AST Audit Report\n\n"
        output_str += f"- **Target**: `{target_path}`\n"
        output_str += f"- **Engine**: `{engine_name}`\n"
        output_str += f"- **Total Findings**: `{len(findings)}`\n\n"
        output_str += format_table(findings)

    if args.output:
        out_p = Path(args.output).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(output_str, encoding="utf-8")
        print(f"[+] Audit report written to: {out_p}")
    else:
        print(output_str)

    has_blocking = any(f.severity in ("CRITICAL", "HIGH") for f in findings)
    if args.fail_on_violation and has_blocking:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
