#!/usr/bin/env python3
"""
Universal Context Synthesizer & Promoter (`context_promoter.py`)
Part of the full-sync universal skill.

Replaces crude substring matching with:
1. Section-aware Markdown AST parser for ideas.md, mistakes.md, constraints.md, resources.md.
2. Semantic Heuristic Classifier (Universal vs Project-Local).
3. Persistent SHA-256 signature deduplicator and title existence check to eliminate redundant writes.
4. Canonical formatting standard for brain root ledgers.
5. Monotonic Anti-Wipe Guard with atomic file replacement.
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

BRAIN_ROOT = Path(r"./")
STATE_FILE = BRAIN_ROOT / "projects" / ".context_promotion_state.json"

# Keywords that indicate cross-project / universal architectural relevance
UNIVERSAL_INDICATORS: Dict[str, float] = {
    "subagent": 2.5,
    "deepcoder": 3.0,
    "deepinvestigator": 3.0,
    "language_server": 2.5,
    "typename='self'": 3.0,
    "typename='research'": 3.0,
    "auto-skill": 2.0,
    "full-sync": 2.0,
    "hermes": 2.0,
    "free tier": 2.5,
    "azure": 1.8,
    "postgresql": 1.8,
    "standard_b1ms": 2.5,
    "supabase": 1.8,
    "cloudflare": 1.8,
    "r2": 1.8,
    "tunnel": 1.8,
    "aws lambda": 2.0,
    "ipv4": 2.0,
    "quota": 2.0,
    "billing": 2.0,
    "credits": 2.0,
    "gemini": 1.8,
    "argon": 2.0,
    "vertex ai": 2.0,
    "model garden": 2.0,
    "touch target": 2.0,
    "44px": 2.0,
    "anti-slop": 2.0,
    "glassmorphism": 1.5,
    "viewport": 1.8,
    "375px": 2.0,
    "crfl": 1.5,
    "crlf": 1.5,
    "powershell": 1.5,
    "npx": 1.8,
    "timeout": 1.5,
    "memory leak": 2.0,
    "race condition": 2.0,
    "rate limit": 1.8,
    "429": 1.8,
    "500": 1.5,
    "524": 1.8,
    "api_router": 2.0,
    "pay-per-token": 2.0,
    "serverless": 1.8,
    "falsification": 2.0,
    "merkle": 2.0,
    "got": 1.8,
    "graph of thoughts": 2.0,
    "tot": 1.8,
    "tree of thoughts": 1.8,
    "logicot": 2.0,
}

# Keywords that indicate hyper-local component / page-specific minutiae
LOCAL_INDICATORS: Dict[str, float] = {
    "padding": -2.0,
    "margin": -2.0,
    "z-index": -2.0,
    "navbar": -1.5,
    "footer": -1.5,
    "button color": -2.0,
    "rounded-": -2.0,
    "bg-slate": -2.0,
    "text-xs": -1.5,
    "div": -1.5,
    "span": -1.5,
    "typo": -2.0,
    "spelling": -2.0,
    "page.tsx": -1.5,
    "layout.tsx": -1.5,
    "slider": -1.2,
    "quest": -2.5,
    "sprite": -2.5,
    "texture": -2.5,
    "dialogue": -2.0,
    "npc": -1.8,
    "audio track": -1.8,
    "playlist": -1.8,
}


class ContextCategory(str, Enum):
    IDEAS = "ideas.md"
    MISTAKES = "mistakes.md"
    CONSTRAINTS = "constraints.md"
    RESOURCES = "resources.md"


@dataclass
class MarkdownBlock:
    project_slug: str
    source_file: str
    title: str
    raw_body: str
    header_level: int = 3
    is_decision: bool = False
    is_mistake: bool = False
    rationale: str = ""
    root_cause: str = ""
    prevention: str = ""
    sig_hash: str = ""
    title_hash: str = ""
    score: float = 0.0


class MarkdownASTParser:
    @staticmethod
    def compute_sig_hash(title: str, body: str) -> str:
        norm = re.sub(r"\s+", " ", f"{title.lower()} {body.lower()}").strip()
        return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def compute_title_hash(title: str) -> str:
        clean = re.sub(r"[^a-zA-Z0-9]", "", title.lower())
        return hashlib.sha256(clean.encode("utf-8")).hexdigest()[:16]

    @classmethod
    def parse_blocks(cls, project_slug: str, filename: str, content: str) -> List[MarkdownBlock]:
        blocks: List[MarkdownBlock] = []
        lines = content.splitlines()
        current_title = ""
        current_body_lines: List[str] = []
        current_level = 3

        def commit_block():
            nonlocal current_title, current_body_lines, current_level
            if current_title and current_body_lines:
                body = "\n".join(current_body_lines).strip()
                if body and not current_title.startswith("[INIT]"):
                    block = MarkdownBlock(
                        project_slug=project_slug,
                        source_file=filename,
                        title=current_title,
                        raw_body=body,
                        header_level=current_level,
                        sig_hash=cls.compute_sig_hash(current_title, body),
                        title_hash=cls.compute_title_hash(current_title)
                    )
                    cls._extract_fields(block)
                    blocks.append(block)
            current_title = ""
            current_body_lines = []

        for line in lines:
            sline = line.strip()
            if sline.startswith("### ") or sline.startswith("## "):
                commit_block()
                current_level = 3 if sline.startswith("### ") else 2
                raw_title = sline.lstrip("#").strip()
                cleaned = re.sub(r"^(Decision|Mistake\s*/\s*Anti-Pattern)\s*\[.*?\]\s*(\(.*?\))?:?\s*", "", raw_title, flags=re.IGNORECASE)
                current_title = cleaned or raw_title
            elif (sline.startswith("- **") or sline.startswith("- [")) and len(sline) > 15:
                if not current_title:
                    commit_block()
                    m = re.match(r"^-\s*(\*\*|\[)(.*?)(\*\*|\]):?\s*(.*)$", sline)
                    if m:
                        current_title = m.group(2).strip()
                        current_body_lines.append(m.group(4).strip())
                    else:
                        current_title = sline[:50]
                        current_body_lines.append(sline[50:].strip())
                else:
                    current_body_lines.append(line)
            else:
                if current_title:
                    current_body_lines.append(line)

        commit_block()
        return blocks

    @staticmethod
    def _extract_fields(block: MarkdownBlock):
        body = block.raw_body
        r_match = re.search(r"-\s*\*\*Rationale\s*(&\s*Impact)?\*\*:\s*(.*?)(?=\n-|\Z)", body, re.IGNORECASE | re.DOTALL)
        if r_match:
            block.rationale = r_match.group(2).strip()

        rc_match = re.search(r"-\s*\*\*Root\s*Cause\*\*:\s*(.*?)(?=\n-|\Z)", body, re.IGNORECASE | re.DOTALL)
        if rc_match:
            block.root_cause = rc_match.group(1).strip()

        p_match = re.search(r"-\s*\*\*Prevention\s*(&\s*Invariant)?\*\*:\s*(.*?)(?=\n-|\Z)", body, re.IGNORECASE | re.DOTALL)
        if p_match:
            block.prevention = p_match.group(2).strip()


class UniversalClassifier:
    @staticmethod
    def score_block(block: MarkdownBlock) -> float:
        text = f"{block.title} {block.raw_body}".lower()
        score = 0.0

        for kw, weight in UNIVERSAL_INDICATORS.items():
            if kw in text:
                score += weight

        for kw, weight in LOCAL_INDICATORS.items():
            if kw in text:
                score += weight

        block.score = score
        return score

    @classmethod
    def is_universal(cls, block: MarkdownBlock) -> bool:
        scope = re.search(
            r"(?im)^\s*(?:-\s+)?\*{0,2}scope\*{0,2}\s*:\s*\*{0,2}(universal|cross-project|project-local|local)\*{0,2}\s*$",
            block.raw_body,
        )
        if scope:
            return scope.group(1).casefold() in {"universal", "cross-project"}
        return bool(re.match(r"(?i)^\[(?:universal|cross-project)\]\s+", block.title))


class ContextPromoter:
    def __init__(self, brain_root: Path = BRAIN_ROOT, dry_run: bool = False):
        self.brain_root = brain_root.resolve()
        self.dry_run = dry_run
        self.state_file = self.brain_root / "projects" / STATE_FILE.name
        self.known_signatures: Set[str] = self._load_signatures()

    def _load_signatures(self) -> Set[str]:
        sigs: Set[str] = set()
        if self.state_file.exists():
            try:
                loaded = json.loads(self.state_file.read_text(encoding="utf-8"))
                if isinstance(loaded, list):
                    sigs.update(loaded)
            except (OSError, ValueError):
                pass
        return sigs

    def _save_signatures(self):
        if not self.dry_run:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.state_file.with_suffix(".tmp")
            temp_path.write_text(json.dumps(sorted(self.known_signatures), indent=2), encoding="utf-8")
            os.replace(temp_path, self.state_file)

    def archive_to_project_brain(self, project_slug: str, filename: str, content: str):
        if self.dry_run:
            return
        dst_dir = self.brain_root / "projects" / project_slug
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst_file = dst_dir / filename
        dst_file.write_text(content, encoding="utf-8")

    def promote_block_to_brain(self, block: MarkdownBlock, category: ContextCategory) -> bool:
        if not UniversalClassifier.is_universal(block):
            return False

        brain_target = self.brain_root / category.value
        if not brain_target.exists():
            return False

        signature = f"v2:{block.project_slug.casefold()}:{category.value}:{block.sig_hash}"
        marker = f"<!-- context-promotion {signature} -->"
        old_content = brain_target.read_text(encoding="utf-8", errors="replace")
        if signature in self.known_signatures or marker in old_content:
            return False

        today = datetime.datetime.now().strftime("%Y-%m-%d")
        now_time = datetime.datetime.now().strftime("%H:%M:%S IST")

        if category == ContextCategory.IDEAS:
            formatted = f"\n### Decision [{today}] ({block.project_slug.upper()}): {block.title}\n"
            if block.rationale:
                formatted += f"- **Rationale & Impact**: {block.rationale}\n"
            else:
                formatted += f"- **Rationale & Impact**: {block.raw_body}\n"
            formatted += f"- **Committed At**: {now_time}\n"
        elif category == ContextCategory.MISTAKES:
            formatted = f"\n### Mistake / Anti-Pattern [{today}] ({block.project_slug.upper()}): {block.title}\n"
            if block.root_cause:
                formatted += f"- **Root Cause**: {block.root_cause}\n"
            if block.prevention:
                formatted += f"- **Prevention & Invariant**: {block.prevention}\n"
            if not block.root_cause and not block.prevention:
                formatted += f"- **Failure Analysis**: {block.raw_body}\n"
        elif category == ContextCategory.CONSTRAINTS:
            formatted = f"\n### [{block.project_slug.upper()}] Universal Invariant: {block.title}\n"
            formatted += f"{block.raw_body}\n"
        elif category == ContextCategory.RESOURCES:
            formatted = f"\n### [{block.project_slug.upper()}] Service Infrastructure: {block.title}\n"
            formatted += f"{block.raw_body}\n"
        else:
            formatted = f"\n## [{block.project_slug.upper()} Synced: {today}]\n{block.title}\n{block.raw_body}\n"

        new_content = old_content + formatted + f"{marker}\n"

        # Monotonic Anti-Wipe Guard
        if len(new_content.encode("utf-8")) < len(old_content.encode("utf-8")):
            print(f"[!] Anti-Wipe Guard triggered for {category.value}! Aborting write.")
            return False

        if not self.dry_run:
            tmp_target = brain_target.with_suffix(".tmp")
            tmp_target.write_text(new_content, encoding="utf-8")
            replaced = False
            for attempt in range(5):
                try:
                    os.replace(tmp_target, brain_target)
                    replaced = True
                    break
                except PermissionError:
                    time.sleep(0.3)
            if not replaced:
                raise OSError(f"Could not atomically replace {brain_target}")

        self.known_signatures.add(signature)
        return True

    def process_project(self, project_slug: str, project_path: Path) -> Dict[str, int]:
        counts = {"promoted_ideas": 0, "promoted_mistakes": 0, "promoted_constraints": 0, "promoted_resources": 0, "archived_files": 0}
        c_dir = project_path / "context"
        if not c_dir.exists():
            c_dir = project_path

        files_to_check = {
            "ideas.md": ContextCategory.IDEAS,
            "mistakes.md": ContextCategory.MISTAKES,
            "constraints.md": ContextCategory.CONSTRAINTS,
            "resources.md": ContextCategory.RESOURCES,
        }

        for fname, category in files_to_check.items():
            f_path = c_dir / fname
            if not f_path.exists():
                f_path = project_path / fname
            if not f_path.exists():
                continue

            content = f_path.read_text(encoding="utf-8", errors="replace")
            self.archive_to_project_brain(project_slug, fname, content)
            counts["archived_files"] += 1

            blocks = MarkdownASTParser.parse_blocks(project_slug, fname, content)
            for b in blocks:
                if self.promote_block_to_brain(b, category):
                    counts[f"promoted_{category.value.removesuffix('.md')}"] += 1

        return counts

    def run_all(self, target_project: Optional[Path] = None) -> Dict[str, Dict[str, int]]:
        from skill_reconciler import SkillReconciler
        reconciler = SkillReconciler(self.brain_root)
        projects = {target_project.name: target_project} if target_project else reconciler.discover_projects()

        print(f"\n[ContextPromoter] Scanning & Synthesizing Context across {len(projects)} Project(s)...")
        summary = {}

        total_promoted = 0
        for slug, p_path in projects.items():
            if not p_path.exists():
                continue
            res = self.process_project(slug, p_path)
            summary[slug] = res
            promoted_in_proj = res["promoted_ideas"] + res["promoted_mistakes"] + res["promoted_constraints"] + res["promoted_resources"]
            total_promoted += promoted_in_proj
            if promoted_in_proj > 0:
                print(f"  [+] {slug}: Promoted {promoted_in_proj} universal entry(ies) (Ideas: {res['promoted_ideas']}, Mistakes: {res['promoted_mistakes']}, Constraints: {res['promoted_constraints']}, Resources: {res['promoted_resources']})")
            else:
                print(f"  [-] {slug}: All entries already in Brain or project-local ({res['archived_files']} files archived).")

        self._save_signatures()
        print(f"[ContextPromoter] Context promotion complete. Total universal entries promoted to Brain: {total_promoted}")
        return summary


def main():
    parser = argparse.ArgumentParser(description="Universal Context Synthesizer & Promoter")
    parser.add_argument("--project", type=Path, default=None, help="Target specific project path")
    parser.add_argument("--dry-run", action="store_true", help="Audit promotions without modifying brain files")

    args = parser.parse_args()
    promoter = ContextPromoter(dry_run=args.dry_run)
    promoter.run_all(args.project)


if __name__ == "__main__":
    main()
