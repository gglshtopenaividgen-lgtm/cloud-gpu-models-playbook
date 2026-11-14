#!/usr/bin/env python3
"""
Automated Skill Integrity & Quality Benchmark Engine
Part of the auto-skill universal powerhouse.

Audits skills across Central Brain and project directories:
1. Validates SKILL.md frontmatter (name, description brevity & token economy, scope indicators).
2. Performs Python AST syntax validation on all scripts in scripts/ (zero broken scripts).
3. Verifies internal reference file integrity (no dangling broken markdown links).
4. Computes automated Skill Quality Score (0-100) and outputs markdown report.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Tuple


def find_brain_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / ".agents").is_dir() and ((parent / "project_map.md").is_file() or (parent / "AGENTS.md").is_file()):
            return parent
    return Path(r"<BRAIN_ROOT>")


BRAIN_ROOT = find_brain_root()


@dataclass
class SkillAuditResult:
    name: str
    path: Path
    scope: str
    frontmatter_valid: bool
    description_length: int
    scripts_checked: int
    scripts_passed: int
    references_checked: int
    references_passed: int
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    score: float = 100.0


def benchmark_single_skill(skill_dir: Path) -> Optional[SkillAuditResult]:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return None

    name = skill_dir.name
    scope = "Universal" if ".agents/skills" in str(skill_md).replace("\\", "/") else "Project-Specific"
    content = skill_md.read_text(encoding="utf-8", errors="replace")

    errors: List[str] = []
    warnings: List[str] = []
    penalty = 0.0

    # 1. Frontmatter check
    frontmatter_valid = False
    desc_len = 0
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            frontmatter_valid = True
            raw_yaml = parts[1]
            if "name:" not in raw_yaml:
                errors.append("Frontmatter missing 'name' field.")
                penalty += 20.0
            desc_match = re.search(r"^description:\s*(?:>-\s*)?(.+?)(?=\n[a-zA-Z_-]+:|\Z)", raw_yaml, re.DOTALL | re.MULTILINE)
            if desc_match:
                clean_desc = re.sub(r"\s+", " ", desc_match.group(1)).strip().strip("\"'")
                desc_len = len(clean_desc)
                if desc_len < 20:
                    warnings.append(f"Description too short ({desc_len} chars); insufficient context for auto-routing.")
                    penalty += 10.0
                elif desc_len > 350:
                    warnings.append(f"Description lengthy ({desc_len} chars); causes system prompt token bloat.")
                    penalty += 5.0
            else:
                errors.append("Frontmatter missing 'description' field.")
                penalty += 20.0
    else:
        errors.append("SKILL.md missing standard YAML frontmatter.")
        penalty += 30.0

    # 2. Scripts compilation check
    scripts_dir = skill_dir / "scripts"
    scripts_checked = 0
    scripts_passed = 0
    if scripts_dir.exists() and scripts_dir.is_dir():
        for py_file in scripts_dir.glob("*.py"):
            scripts_checked += 1
            try:
                code = py_file.read_text(encoding="utf-8", errors="replace")
                ast.parse(code, filename=str(py_file))
                scripts_passed += 1
            except SyntaxError as e:
                errors.append(f"Script syntax error in {py_file.name}:{e.lineno}: {e.msg}")
                penalty += 25.0
            except Exception as e:
                warnings.append(f"Script inspection issue in {py_file.name}: {e}")
                penalty += 5.0

    # 3. References check
    refs_dir = skill_dir / "references"
    refs_checked = 0
    refs_passed = 0
    if refs_dir.exists() and refs_dir.is_dir():
        for ref_file in refs_dir.glob("*.md"):
            refs_checked += 1
            if ref_file.stat().st_size > 50:
                refs_passed += 1
            else:
                warnings.append(f"Reference file {ref_file.name} is nearly empty.")
                penalty += 5.0

    # 4. Check for dangling local markdown links in SKILL.md
    for link_match in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", content):
        link_target = link_match.group(2)
        if link_target.startswith(("#", "http://", "https://", "mailto:", "file://", "file:///")):
            continue
        # Check local relative path
        target_path = (skill_dir / link_target).resolve()
        if not target_path.exists():
            warnings.append(f"Dangling link in SKILL.md: '{link_target}' not found.")
            penalty += 5.0

    final_score = max(0.0, 100.0 - penalty)

    return SkillAuditResult(
        name=name,
        path=skill_md,
        scope=scope,
        frontmatter_valid=frontmatter_valid,
        description_length=desc_len,
        scripts_checked=scripts_checked,
        scripts_passed=scripts_passed,
        references_checked=refs_checked,
        references_passed=refs_passed,
        errors=errors,
        warnings=warnings,
        score=final_score,
    )


def run_benchmark(universal_only: bool = False) -> List[SkillAuditResult]:
    skills_to_audit: List[Path] = []

    # 1. Universal skills
    universal_dir = BRAIN_ROOT / ".agents" / "skills"
    if universal_dir.exists():
        for d in universal_dir.iterdir():
            if d.is_dir() and (d / "SKILL.md").exists():
                skills_to_audit.append(d)

    # 2. Project skills (if not universal_only)
    if not universal_only:
        proj_skills_dir = BRAIN_ROOT / "project_skills"
        if proj_skills_dir.exists():
            for proj_d in proj_skills_dir.iterdir():
                if proj_d.is_dir():
                    for s in proj_d.iterdir():
                        if s.is_dir() and (s / "SKILL.md").exists():
                            skills_to_audit.append(s)

    results = []
    for skill_path in skills_to_audit:
        res = benchmark_single_skill(skill_path)
        if res:
            results.append(res)

    return results


def format_markdown_report(results: List[SkillAuditResult]) -> str:
    total = len(results)
    avg_score = sum(r.score for r in results) / total if total > 0 else 0.0
    perfect = sum(1 for r in results if r.score == 100.0)
    with_errors = sum(1 for r in results if r.errors)

    md = f"""# Skill Suite Quality & Integrity Benchmark Report

- **Total Skills Evaluated**: `{total}`
- **Average Quality Score**: **`{avg_score:.1f} / 100`**
- **100% Perfect Skills**: `{perfect}`
- **Skills with Errors**: `{'🔴 ' + str(with_errors) if with_errors > 0 else '🟢 ZERO'}`

| Skill Name | Scope | Quality Score | Scripts Passed | References | Status |
|---|---|---|---|---|---|
"""
    for r in sorted(results, key=lambda x: (x.scope != "Universal", -x.score, x.name)):
        status_badge = "🟢 PERFECT" if r.score >= 95 else ("🟡 PASS" if r.score >= 80 else "🔴 ATTENTION")
        script_stat = f"{r.scripts_passed}/{r.scripts_checked}" if r.scripts_checked > 0 else "—"
        ref_stat = f"{r.references_passed}/{r.references_checked}" if r.references_checked > 0 else "—"
        md += f"| **`{r.name}`** | `{r.scope}` | **`{r.score:.0f}`** | `{script_stat}` | `{ref_stat}` | {status_badge} |\n"

    # Detail issues if any
    issues_found = [r for r in results if r.errors or r.warnings]
    if issues_found:
        md += "\n## Identified Discrepancies & Recommendations\n\n"
        for r in issues_found:
            md += f"### `{r.name}` ({r.scope}) — Score: `{r.score:.0f}`\n"
            for err in r.errors:
                md += f"- 🔴 **Error**: {err}\n"
            for w in r.warnings:
                md += f"- ⚠️ **Warning**: {w}\n"
            md += "\n"

    return md


def main():
    parser = argparse.ArgumentParser(description="Skill Integrity Benchmark Engine")
    parser.add_argument("--universal", action="store_true", help="Audit universal skills only")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--output", type=str, default=None, help="Save report to file")
    args = parser.parse_args()

    results = run_benchmark(universal_only=args.universal)

    if args.format == "json":
        report_text = json.dumps([r.__dict__ for r in results], default=str, indent=2)
    else:
        report_text = format_markdown_report(results)

    if args.output:
        out_p = Path(args.output)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(report_text, encoding="utf-8")
        print(f"[+] Benchmark report saved to: {out_p}")
    else:
        print(report_text)


if __name__ == "__main__":
    main()
