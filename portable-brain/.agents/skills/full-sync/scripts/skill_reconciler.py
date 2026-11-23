#!/usr/bin/env python3
"""
Universal Skill Synchronizer & Reconciler (`skill_reconciler.py`)
Part of the full-sync universal skill.

Implements robust bi-directional synchronization between:
  1. `<project>/.agents/skills/<skill_name>/` (Project-local active skills)
  2. `brain/project_skills/<project>/<skill_name>/` (Central Brain project skill archives)
  3. `brain/.agents/skills/<skill_name>/` (13 Universal Powerhouses)

Features:
- Merkle Tree SHA-256 Hashing with CRLF/LF normalization to prevent false diffs.
- Bi-directional sync: Project -> Brain backup & Brain -> Project hydration.
- Universal Promotion Gate with strict 13-Core-Skill invariant protection.
- State tracking via `brain/project_skills/.skill_sync_state.json`.
- Automatic catalog synchronization via `sync_catalog.py`.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

BRAIN_ROOT = Path(r"./")
BRAIN_UNIVERSAL_SKILLS_DIR = BRAIN_ROOT / ".agents" / "skills"
BRAIN_PROJECT_SKILLS_DIR = BRAIN_ROOT / "project_skills"
SYNC_STATE_FILE = BRAIN_PROJECT_SKILLS_DIR / ".skill_sync_state.json"

ALLOWED_UNIVERSAL_SKILLS: Set[str] = {
    "auto-skill",
    "browser-operator",
    "deep-thinking",
    "document-forge",
    "exhaustive-audit-and-repair",
    "external-resource",
    "full-sync",
    "hermes-agent-core",
    "internal-tools",
    "offload",
    "rea",
    "ui-design-engine",
    "web-search-orchestrator",
}
ALLOWED_12_UNIVERSAL_SKILLS = ALLOWED_UNIVERSAL_SKILLS

IGNORED_DIRS: Set[str] = {"__pycache__", ".git", "node_modules", ".venv", ".pytest_cache", ".system_generated"}
IGNORED_SUFFIXES: Set[str] = {".pyc", ".pyo", ".tmp", ".bak", ".swp"}


class SkillScope(str, Enum):
    PROJECT = "project"
    UNIVERSAL = "universal"


class SyncAction(str, Enum):
    NO_OP = "NO_OP"
    BACKUP_TO_BRAIN = "BACKUP_TO_BRAIN"
    HYDRATE_TO_PROJECT = "HYDRATE_TO_PROJECT"
    PROMOTE_UNIVERSAL_UPDATE = "PROMOTE_UNIVERSAL_UPDATE"
    STAGE_UNIVERSAL_CANDIDATE = "STAGE_UNIVERSAL_CANDIDATE"
    CONFLICT_RESOLVED = "CONFLICT_RESOLVED"


@dataclass
class SkillMetadata:
    name: str
    description: str
    scope: SkillScope = SkillScope.PROJECT
    target_universal_skill: Optional[str] = None
    triggers: List[str] = field(default_factory=list)
    raw_frontmatter: Dict[str, str] = field(default_factory=dict)


@dataclass
class SkillManifest:
    project_slug: str
    skill_name: str
    root_path: Path
    tree_sha256: str
    max_mtime: float
    file_hashes: Dict[str, str]  # relative POSIX path -> sha256
    metadata: SkillMetadata


@dataclass
class SyncResult:
    project_slug: str
    skill_name: str
    action: SyncAction
    files_copied: int = 0
    files_removed: int = 0
    notes: str = ""


class SkillTreeHasher:
    @staticmethod
    def hash_file(file_path: Path) -> str:
        try:
            raw_bytes = file_path.read_bytes()
            # Normalize CRLF to LF on text files to prevent line-ending churn across environments
            text_norm = raw_bytes.decode("utf-8").replace("\r\n", "\n").encode("utf-8")
            return hashlib.sha256(text_norm).hexdigest()
        except UnicodeDecodeError:
            return hashlib.sha256(raw_bytes).hexdigest()

    @classmethod
    def compute_manifest(cls, project_slug: str, skill_dir: Path) -> SkillManifest:
        file_hashes: Dict[str, str] = {}
        max_mtime = 0.0
        tree_hasher = hashlib.sha256()

        if skill_dir.exists() and skill_dir.is_dir():
            for file_path in sorted(skill_dir.rglob("*")):
                if not file_path.is_file():
                    continue
                if any(part in IGNORED_DIRS for part in file_path.parts):
                    continue
                if file_path.suffix.lower() in IGNORED_SUFFIXES:
                    continue

                rel_posix = file_path.relative_to(skill_dir).as_posix()
                f_hash = cls.hash_file(file_path)
                file_hashes[rel_posix] = f_hash
                max_mtime = max(max_mtime, file_path.stat().st_mtime)
                tree_hasher.update(f"{rel_posix}:{f_hash}\n".encode("utf-8"))

        metadata = cls.parse_frontmatter(skill_dir / "SKILL.md")
        return SkillManifest(
            project_slug=project_slug,
            skill_name=skill_dir.name,
            root_path=skill_dir,
            tree_sha256=tree_hasher.hexdigest(),
            max_mtime=max_mtime,
            file_hashes=file_hashes,
            metadata=metadata,
        )

    @staticmethod
    def parse_frontmatter(skill_md_path: Path) -> SkillMetadata:
        if not skill_md_path.exists():
            return SkillMetadata(name=skill_md_path.parent.name, description="")

        try:
            content = skill_md_path.read_text(encoding="utf-8", errors="replace")
            meta = SkillMetadata(name=skill_md_path.parent.name, description="")
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    lines = parts[1].splitlines()
                    for line in lines:
                        if ":" in line:
                            k, v = line.split(":", 1)
                            k, v = k.strip().lower(), v.strip().strip('"\'')
                            meta.raw_frontmatter[k] = v
                            if k == "name" and line == line.lstrip():
                                meta.name = v
                            elif k == "description":
                                meta.description = v
                            elif k in ("scope", "type"):
                                if "universal" in v.lower():
                                    meta.scope = SkillScope.UNIVERSAL
                            elif k == "target_universal_skill":
                                meta.target_universal_skill = v
            return meta
        except Exception:
            return SkillMetadata(name=skill_md_path.parent.name, description="")


class SkillReconciler:
    def __init__(self, brain_root: Path = BRAIN_ROOT, dry_run: bool = False, allow_new_universal: bool = False):
        self.brain_root = brain_root.resolve()
        self.dry_run = dry_run
        self.allow_new_universal = allow_new_universal
        self.brain_project_skills_dir = self.brain_root / "project_skills"
        self.brain_universal_skills_dir = self.brain_root / ".agents" / "skills"
        self.sync_state_file = self.brain_project_skills_dir / ".skill_sync_state.json"
        self.sync_state = self._load_sync_state()

    def _load_sync_state(self) -> Dict[str, Dict[str, str]]:
        if self.sync_state_file.exists():
            try:
                return json.loads(self.sync_state_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_sync_state(self):
        if not self.dry_run:
            self.brain_project_skills_dir.mkdir(parents=True, exist_ok=True)
            self.sync_state_file.write_text(json.dumps(self.sync_state, indent=2), encoding="utf-8")

    def discover_projects(self) -> Dict[str, Path]:
        """Discovers all active project roots from project_map.md and standard filesystem directories."""
        projects: Dict[str, Path] = {}

        # 1. Read registered projects from brain/project_map.md
        proj_map = self.brain_root / "project_map.md"
        if proj_map.exists():
            for line in proj_map.read_text(encoding="utf-8").splitlines():
                if "|" in line and ("C:\\" in line or "C:/" in line or "D:\\" in line or "D:/" in line):
                    parts = [p.strip() for p in line.split("|")]
                    for part in parts:
                        if part.startswith("`") and ("Desktop" in part or "PROJECTS" in part or "appwrite" in part):
                            raw = part.strip("`")
                            p = Path(raw)
                            if p.exists() and p.is_dir() and p != self.brain_root:
                                projects[p.name] = p

        # 2. Add standard known locations
        candidates = [
            Path(r"C:\Users\User\Desktop\flh-one"),
            Path(r"C:\Users\User\Desktop\PJCT\hi"),
            Path(r"C:\Users\User\Desktop\PJCT\AWAKEN1"),
            Path(r"C:\Users\User\Desktop\appwrite\flh-music"),
            Path(r"C:\Users\User\Desktop\PJCT\custom_tools"),
            Path(r"C:\Users\User\Desktop\PJCT\mineserver"),
            Path(r"C:\Users\User\Desktop\PJCT\cult_game"),
            Path(r"<PROJECTS_ROOT>\PKREA"),
        ]
        for c in candidates:
            if c.exists() and c.is_dir():
                projects[c.name] = c

        # Scan PJCT subdirectories
        pjct_dir = Path(r"C:\Users\User\Desktop\PJCT")
        if pjct_dir.exists() and pjct_dir.is_dir():
            for sub in pjct_dir.iterdir():
                if sub.is_dir() and not sub.name.startswith("."):
                    projects[sub.name] = sub

        return projects

    def sync_directory_delta(self, src: Path, dst: Path, src_manifest: SkillManifest, dst_manifest: SkillManifest) -> Tuple[int, int]:
        """Performs delta copy from src to dst, copying only differing or new files and removing obsolete ones."""
        if self.dry_run:
            files_to_copy = [k for k, h in src_manifest.file_hashes.items() if dst_manifest.file_hashes.get(k) != h]
            files_to_del = [k for k in dst_manifest.file_hashes.keys() if k not in src_manifest.file_hashes]
            return len(files_to_copy), len(files_to_del)

        dst.mkdir(parents=True, exist_ok=True)
        copied = 0
        deleted = 0

        # Copy new or changed files
        for rel_posix, s_hash in src_manifest.file_hashes.items():
            if dst_manifest.file_hashes.get(rel_posix) != s_hash:
                s_path = src / Path(rel_posix)
                d_path = dst / Path(rel_posix)
                d_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(s_path, d_path)
                copied += 1

        # Delete removed files in dst
        for rel_posix in dst_manifest.file_hashes.keys():
            if rel_posix not in src_manifest.file_hashes:
                d_path = dst / Path(rel_posix)
                if d_path.exists() and d_path.is_file():
                    try:
                        d_path.unlink()
                        deleted += 1
                    except Exception:
                        pass

        # Cleanup empty directories in dst
        for root, dirs, files in os.walk(dst, topdown=False):
            for d in dirs:
                dir_path = Path(root) / d
                if not any(dir_path.iterdir()):
                    try:
                        dir_path.rmdir()
                    except Exception:
                        pass

        return copied, deleted

    def reconcile_project_skills(self, project_slug: str, project_root: Path) -> List[SyncResult]:
        results: List[SyncResult] = []
        project_skills_dir = project_root / ".agents" / "skills"
        brain_proj_dir = self.brain_project_skills_dir / project_slug

        project_skills: Set[str] = set()
        if project_skills_dir.exists() and project_skills_dir.is_dir():
            project_skills = {d.name for d in project_skills_dir.iterdir() if d.is_dir()}

        brain_skills: Set[str] = set()
        if brain_proj_dir.exists() and brain_proj_dir.is_dir():
            brain_skills = {d.name for d in brain_proj_dir.iterdir() if d.is_dir() and not d.name.startswith(".")}

        all_skills = sorted(project_skills | brain_skills)
        if not all_skills:
            return results

        if project_slug not in self.sync_state:
            self.sync_state[project_slug] = {}

        for skill_name in all_skills:
            p_skill_dir = project_skills_dir / skill_name
            b_skill_dir = brain_proj_dir / skill_name
            names = {
                skill_name.casefold(),
                SkillTreeHasher.parse_frontmatter(p_skill_dir / "SKILL.md").name.casefold(),
                SkillTreeHasher.parse_frontmatter(b_skill_dir / "SKILL.md").name.casefold(),
            }
            if names & ALLOWED_UNIVERSAL_SKILLS:
                continue

            p_manifest = SkillTreeHasher.compute_manifest(project_slug, p_skill_dir)
            b_manifest = SkillTreeHasher.compute_manifest(project_slug, b_skill_dir)

            last_known_hash = self.sync_state[project_slug].get(skill_name, "")

            # 1. Check if skill is identical in both locations
            if p_skill_dir.exists() and b_skill_dir.exists() and p_manifest.tree_sha256 == b_manifest.tree_sha256:
                self.sync_state[project_slug][skill_name] = p_manifest.tree_sha256
                results.append(SyncResult(
                    project_slug=project_slug,
                    skill_name=skill_name,
                    action=SyncAction.NO_OP,
                    notes="Hash match. 100% in sync."
                ))
                continue

            # 2. Skill exists ONLY in project -> Backup to Brain
            if p_skill_dir.exists() and not b_skill_dir.exists():
                copied, deleted = self.sync_directory_delta(p_skill_dir, b_skill_dir, p_manifest, b_manifest)
                self.sync_state[project_slug][skill_name] = p_manifest.tree_sha256
                results.append(SyncResult(
                    project_slug=project_slug,
                    skill_name=skill_name,
                    action=SyncAction.BACKUP_TO_BRAIN,
                    files_copied=copied,
                    files_removed=deleted,
                    notes=f"Backed up new skill from {project_slug} to brain/project_skills/{project_slug}/{skill_name}"
                ))

                # Check Universal Promotion Gate
                self.evaluate_universal_promotion(p_manifest, results)
                continue

            # 3. Skill exists ONLY in Brain -> Hydrate down to project
            if not p_skill_dir.exists() and b_skill_dir.exists():
                copied, deleted = self.sync_directory_delta(b_skill_dir, p_skill_dir, b_manifest, p_manifest)
                self.sync_state[project_slug][skill_name] = b_manifest.tree_sha256
                results.append(SyncResult(
                    project_slug=project_slug,
                    skill_name=skill_name,
                    action=SyncAction.HYDRATE_TO_PROJECT,
                    files_copied=copied,
                    files_removed=deleted,
                    notes=f"Hydrated missing project skill from brain to {project_slug}/.agents/skills/{skill_name}"
                ))
                continue

            # 4. Exists in both but hashes differ
            if p_manifest.tree_sha256 != b_manifest.tree_sha256:
                # Compare mtimes and last known hash
                if b_manifest.tree_sha256 == last_known_hash:
                    # Project changed -> Backup to Brain
                    copied, deleted = self.sync_directory_delta(p_skill_dir, b_skill_dir, p_manifest, b_manifest)
                    self.sync_state[project_slug][skill_name] = p_manifest.tree_sha256
                    results.append(SyncResult(
                        project_slug=project_slug,
                        skill_name=skill_name,
                        action=SyncAction.BACKUP_TO_BRAIN,
                        files_copied=copied,
                        files_removed=deleted,
                        notes="Project modified since last sync. Updated brain backup."
                    ))
                elif p_manifest.tree_sha256 == last_known_hash:
                    # Brain changed -> Hydrate down to Project
                    copied, deleted = self.sync_directory_delta(b_skill_dir, p_skill_dir, b_manifest, p_manifest)
                    self.sync_state[project_slug][skill_name] = b_manifest.tree_sha256
                    results.append(SyncResult(
                        project_slug=project_slug,
                        skill_name=skill_name,
                        action=SyncAction.HYDRATE_TO_PROJECT,
                        files_copied=copied,
                        files_removed=deleted,
                        notes="Brain modified since last sync. Updated project copy."
                    ))
                else:
                    # Both changed or first run with diffs -> Favor newer mtime
                    if p_manifest.max_mtime >= b_manifest.max_mtime:
                        copied, deleted = self.sync_directory_delta(p_skill_dir, b_skill_dir, p_manifest, b_manifest)
                        self.sync_state[project_slug][skill_name] = p_manifest.tree_sha256
                        results.append(SyncResult(
                            project_slug=project_slug,
                            skill_name=skill_name,
                            action=SyncAction.BACKUP_TO_BRAIN,
                            files_copied=copied,
                            files_removed=deleted,
                            notes="Project has newer timestamp. Overwrote brain backup."
                        ))
                    else:
                        copied, deleted = self.sync_directory_delta(b_skill_dir, p_skill_dir, b_manifest, p_manifest)
                        self.sync_state[project_slug][skill_name] = b_manifest.tree_sha256
                        results.append(SyncResult(
                            project_slug=project_slug,
                            skill_name=skill_name,
                            action=SyncAction.HYDRATE_TO_PROJECT,
                            files_copied=copied,
                            files_removed=deleted,
                            notes="Brain backup has newer timestamp. Updated project copy."
                        ))

                self.evaluate_universal_promotion(p_manifest, results)

        return results

    def evaluate_universal_promotion(self, manifest: SkillManifest, results: List[SyncResult]):
        """Evaluates whether a skill created in a project should be promoted to Universal Skills."""
        skill_name = manifest.skill_name

        if {skill_name.casefold(), manifest.metadata.name.casefold()} & ALLOWED_UNIVERSAL_SKILLS:
            return

        # If it declares target_universal_skill
        if manifest.metadata.target_universal_skill in ALLOWED_UNIVERSAL_SKILLS:
            target = manifest.metadata.target_universal_skill
            target_dir = self.brain_universal_skills_dir / target
            # Sync scripts/ or references/ as sub-modules
            for sub in ["scripts", "references"]:
                src_sub = manifest.root_path / sub
                if src_sub.exists() and src_sub.is_dir():
                    dst_sub = target_dir / sub
                    for item in src_sub.iterdir():
                        if item.is_file():
                            d_item = dst_sub / item.name
                            if not d_item.exists() or SkillTreeHasher.hash_file(item) != SkillTreeHasher.hash_file(d_item):
                                if not self.dry_run:
                                    dst_sub.mkdir(parents=True, exist_ok=True)
                                    shutil.copy2(item, d_item)
                                results.append(SyncResult(
                                    project_slug=manifest.project_slug,
                                    skill_name=skill_name,
                                    action=SyncAction.PROMOTE_UNIVERSAL_UPDATE,
                                    files_copied=1,
                                    notes=f"Promoted {item.name} into Universal Skill {target}/{sub}/"
                                ))
            return

        # If marked universal but is a net-new skill
        if manifest.metadata.scope == SkillScope.UNIVERSAL:
            candidate_dir = self.brain_project_skills_dir / "_universal_candidates" / skill_name
            if self.allow_new_universal:
                # Explicit override to expand universal skills
                target_dir = self.brain_universal_skills_dir / skill_name
                u_manifest = SkillTreeHasher.compute_manifest("brain_universal", target_dir)
                copied, deleted = self.sync_directory_delta(manifest.root_path, target_dir, manifest, u_manifest)
                results.append(SyncResult(
                    project_slug=manifest.project_slug,
                    skill_name=skill_name,
                    action=SyncAction.PROMOTE_UNIVERSAL_UPDATE,
                    files_copied=copied,
                    notes=f"Promoted net-new universal powerhouse {skill_name} into brain/.agents/skills/"
                ))
            else:
                # Stage in candidates to preserve the universal skill cap.
                if not candidate_dir.exists() and not self.dry_run:
                    candidate_dir.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(manifest.root_path, candidate_dir, dirs_exist_ok=True)
                results.append(SyncResult(
                    project_slug=manifest.project_slug,
                    skill_name=skill_name,
                    action=SyncAction.STAGE_UNIVERSAL_CANDIDATE,
                    notes=f"Staged in brain/project_skills/_universal_candidates/{skill_name} (13-core invariant protected)"
                ))

    def run_all(self, target_project: Optional[Path] = None) -> List[SyncResult]:
        projects = {target_project.name: target_project} if target_project else self.discover_projects()
        all_results: List[SyncResult] = []

        print(f"\n[SkillReconciler] Scanning & Synchronizing Skills across {len(projects)} Project(s)...")
        for slug, path in projects.items():
            if not path.exists():
                continue
            res = self.reconcile_project_skills(slug, path)
            all_results.extend(res)

        self._save_sync_state()

        # Trigger auto-skill catalog sync if any changes were made
        mutations = [r for r in all_results if r.action != SyncAction.NO_OP]
        if mutations and self.dry_run:
            print(f"[SkillReconciler] [Dry Run] Would apply {len(mutations)} change(s) and regenerate the Auto-Skill Catalog.")
        elif mutations:
            print(f"[SkillReconciler] {len(mutations)} skill modification(s) executed. Regenerating Auto-Skill Catalog...")
            self.trigger_catalog_sync()
        else:
            print("[SkillReconciler] All project and universal skills are 100% synchronized. Zero disk mutations required.")

        stale_refs = check_stale_skill_refs(self.brain_root, list(projects.values()))
        if stale_refs:
            print(f"[SkillReconciler] ⚠️ Detected {len(stale_refs)} [STALE_REF] path(s):")
            for item in stale_refs[:20]:
                print(f"  {item['tag']} {item['missing_ref']} in {item['source']}")

        return all_results

    def trigger_catalog_sync(self) -> bool:
        if self.dry_run:
            return True
        sync_script = self.brain_universal_skills_dir / "auto-skill" / "scripts" / "sync_catalog.py"
        if not sync_script.exists():
            return False
        try:
            res = subprocess.run([sys.executable, str(sync_script)], capture_output=True, text=True, cwd=str(self.brain_root))
            print("  " + res.stdout.strip())
            return res.returncode == 0
        except Exception as e:
            print(f"  [!] Failed to run sync_catalog.py: {e}")
            return False


AUTO_SYNC_BEGIN = "<!-- BEGIN AUTO-SYNC -->"
AUTO_SYNC_END = "<!-- END AUTO-SYNC -->"
REL_REF_RE = re.compile(r"`((?:scripts|references|argon_bridge|templates|examples)/[A-Za-z0-9_.\-/]+\.(?:py|md|json|bat|ps1|sh|yaml|yml|ts|js))`")


def sync_project_skill_overlay(project_root: Path, skill_name: str, generated_block: str, dry_run: bool = False) -> Tuple[Path, bool]:
    """Updates ONLY the fenced <!-- BEGIN AUTO-SYNC --> block inside <project>/.agents/skill_overlays/<skill>.md."""
    overlay_dir = Path(project_root) / ".agents" / "skill_overlays"
    overlay_path = overlay_dir / f"{skill_name}.md"
    fenced = f"{AUTO_SYNC_BEGIN}\n{generated_block.strip()}\n{AUTO_SYNC_END}"

    if overlay_path.is_file():
        existing = overlay_path.read_text(encoding="utf-8", errors="replace")
        if AUTO_SYNC_BEGIN in existing and AUTO_SYNC_END in existing:
            before, rest = existing.split(AUTO_SYNC_BEGIN, 1)
            _, after = rest.split(AUTO_SYNC_END, 1)
            updated = f"{before}{fenced}{after}"
        else:
            updated = existing.rstrip() + "\n\n" + fenced + "\n"
        changed = (updated.replace("\r\n", "\n") != existing.replace("\r\n", "\n"))
    else:
        updated = (
            f"# Project Skill Overlay :: {skill_name} ({Path(project_root).name})\n\n"
            f"Add project-specific notes outside the AUTO-SYNC fence below.\n\n"
            f"{fenced}\n"
        )
        changed = True

    if changed and not dry_run:
        overlay_dir.mkdir(parents=True, exist_ok=True)
        overlay_path.write_text(updated, encoding="utf-8")
    return overlay_path, changed


def check_stale_skill_refs(brain_root: Path = BRAIN_ROOT, project_roots: Optional[List[Path]] = None) -> List[Dict[str, str]]:
    """Checks all universal SKILL.md files and project overlays for dead relative script/reference paths."""
    stale: List[Dict[str, str]] = []
    skills_dir = Path(brain_root) / ".agents" / "skills"
    if skills_dir.is_dir():
        for skill_dir in sorted(skills_dir.iterdir()):
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.is_file():
                continue
            txt = skill_md.read_text(encoding="utf-8", errors="replace")
            for m in REL_REF_RE.finditer(txt):
                rel = m.group(1)
                if not (skill_dir / rel).exists():
                    stale.append({"source": str(skill_md), "missing_ref": rel, "tag": "[STALE_REF]"})

    for proj in (project_roots or []):
        ov_dir = Path(proj) / ".agents" / "skill_overlays"
        if not ov_dir.is_dir():
            continue
        for ov_file in sorted(ov_dir.glob("*.md")):
            txt = ov_file.read_text(encoding="utf-8", errors="replace")
            for m in REL_REF_RE.finditer(txt):
                rel = m.group(1)
                if not (Path(proj) / rel).exists() and not (skills_dir / ov_file.stem / rel).exists():
                    stale.append({"source": str(ov_file), "missing_ref": rel, "tag": "[STALE_REF]"})
    return stale


def main():
    parser = argparse.ArgumentParser(description="Universal Skill Synchronizer & Reconciler")
    parser.add_argument("--project", type=Path, default=None, help="Target specific project path")
    parser.add_argument("--dry-run", action="store_true", help="Audit diffs without writing to disk")
    parser.add_argument("--allow-new-universal", action="store_true", help="Allow promoting beyond 13 universal powerhouses")

    args = parser.parse_args()
    reconciler = SkillReconciler(dry_run=args.dry_run, allow_new_universal=args.allow_new_universal)
    results = reconciler.run_all(args.project)

    mutations = [r for r in results if r.action != SyncAction.NO_OP]
    print(f"\n=== SKILL RECONCILIATION SUMMARY: {len(mutations)} ACTION(S) ===")
    for m in mutations:
        print(f"[{m.action.value}] {m.project_slug} :: {m.skill_name} (+{m.files_copied}/-{m.files_removed}) - {m.notes}")


if __name__ == "__main__":
    main()
