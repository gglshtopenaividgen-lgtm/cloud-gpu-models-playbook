#!/usr/bin/env python3
"""
Full-Sync Master Engine 3.0
Universal Multi-Agent Synchronizer across Central Brain & Projects.

Executes the upgraded 4-Pillar Synchronization Pipeline:
  1. Bi-directional Skill Reconciliation (skill_reconciler.py):
     - Discovers skills in all project workspaces.
     - Backs up new/modified project skills to `brain/project_skills/<project>/`.
     - Hydrates missing project skills down from Brain to projects.
     - Enforces the 12-Universal-Skill Cap Guard.
     - Automatically regenerates the central auto-skill catalog (sync_catalog.py).
  2. Universal Context Synthesis & Promotion (context_promoter.py):
     - Markdown AST block parsing for ideas.md, mistakes.md, constraints.md, resources.md.
     - Semantic heuristic classification: elevates universal invariants, cloud limits, and architectural decisions to Brain root ledgers.
     - Safe archiving of all project context to `brain/projects/<project>/`.
     - Monotonic size guard and SHA-256 signature deduplication.
  3. <VAULT_BACKUP_DIR> Sovereign Vault Synchronization (sync_to_d_agentic.py):
     - Mirrors all updated universal skills, project skills, rules, and context to the offline vault.
  4. Project Bootstrapping & Hermes Verification (bootstrap_hermes.py):
     - Ensures every project workspace has standard context suite, AGENTS.md, file_map.md, and Hermes DB.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

def _find_brain_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / ".agents").is_dir() and ((parent / "project_map.md").is_file() or (parent / "AGENTS.md").is_file()):
            return parent
    return Path(r"<BRAIN_ROOT>")

BRAIN_ROOT = _find_brain_root()
SCRIPTS_DIR = Path(__file__).resolve().parent

# Ensure full-sync scripts directory is in python path
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def run_command_clean(cmd: List[str], cwd: Path = BRAIN_ROOT) -> tuple[int, str]:
    try:
        res = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        return res.returncode, res.stdout.strip() or res.stderr.strip()
    except Exception as e:
        return 1, str(e)


def sync_skills(target_project: Optional[Path] = None, dry_run: bool = False, allow_new_universal: bool = False) -> bool:
    print("\n[Pillar 1/4] Bi-directional Skill Synchronization & Catalog Sync...")
    from skill_reconciler import SkillReconciler, SyncAction

    reconciler = SkillReconciler(brain_root=BRAIN_ROOT, dry_run=dry_run, allow_new_universal=allow_new_universal)
    results = reconciler.run_all(target_project)
    mutations = [r for r in results if r.action != SyncAction.NO_OP]

    print(f"  ✅ Skill Sync Completed: {len(results)} evaluated, {len(mutations)} action(s) taken.")
    for m in mutations[:10]:
        print(f"     [{m.action.value}] {m.project_slug} :: {m.skill_name} (+{m.files_copied}/-{m.files_removed})")
    if len(mutations) > 10:
        print(f"     ... and {len(mutations) - 10} more skill actions.")
    return True


def promote_and_reconcile_context(target_project: Optional[Path] = None, dry_run: bool = False) -> bool:
    print("\n[Pillar 2/4] Universal Context Synthesis, Promotion & Project Archiving...")
    from context_promoter import ContextPromoter

    promoter = ContextPromoter(brain_root=BRAIN_ROOT, dry_run=dry_run)
    summary = promoter.run_all(target_project)

    total_promoted = sum(
        res["promoted_ideas"] + res["promoted_mistakes"] + res["promoted_constraints"] + res["promoted_resources"]
        for res in summary.values()
    )
    total_archived = sum(res["archived_files"] for res in summary.values())

    print(f"  ✅ Context Synthesis Completed: {total_promoted} universal entry(ies) promoted, {total_archived} project file(s) archived.")

    # Commit any updates in Brain to Git
    if not dry_run:
        run_command_clean(["git", "add", "."], cwd=BRAIN_ROOT)
        code, git_status = run_command_clean(["git", "status", "--porcelain"], cwd=BRAIN_ROOT)
        if git_status:
            run_command_clean(
                ["git", "commit", "-m", "chore(full-sync): auto-sync project skills and universal context"],
                cwd=BRAIN_ROOT
            )
            print("  ✅ Central Brain Git updated and committed.")
        else:
            print("  ℹ️ Central Brain Git working tree is clean.")

    return True


def sync_sovereign_vault(dry_run: bool = False) -> bool:
    print("\n[Pillar 3/4] Synchronizing <VAULT_BACKUP_DIR> Sovereign Vault...")
    if dry_run:
        print("  ℹ️ [Dry Run] Skipping <VAULT_BACKUP_DIR> vault mirror.")
        return True

    sync_script = BRAIN_ROOT / "scripts" / "sync_to_d_agentic.py"
    if not sync_script.exists():
        print(f"  ⚠️ sync_to_d_agentic.py not found at {sync_script}")
        return False

    code, out = run_command_clean([sys.executable, str(sync_script)])
    print(f"  {out}")
    return code == 0


def check_and_bootstrap_projects(target_project: Optional[Path] = None, dry_run: bool = False) -> bool:
    print("\n[Pillar 4/4] Checking and Bootstrapping Project Suites & Hermes...")
    from skill_reconciler import SkillReconciler
    reconciler = SkillReconciler(BRAIN_ROOT)
    projects = [target_project] if target_project else list(reconciler.discover_projects().values())

    bootstrap_script = BRAIN_ROOT / "scripts" / "bootstrap_hermes.py"
    overall_ok = True

    for p in projects:
        if not p.exists():
            continue

        needs_bootstrap = False
        reasons = []

        if not (p / ".hermes" / "project_memory.db").exists():
            needs_bootstrap = True
            reasons.append("Missing .hermes/project_memory.db")
        if not (p / "file_map.md").exists() and not (p / "context" / "file_map.md").exists():
            needs_bootstrap = True
            reasons.append("Missing file_map.md")
        if not (p / "AGENTS.md").exists():
            needs_bootstrap = True
            reasons.append("Missing AGENTS.md")

        if not needs_bootstrap:
            print(f"  ✅ {p.name}: Fully configured.")
            continue

        if dry_run:
            print(f"  ℹ️ [Dry Run] {p.name} needs bootstrapping: {', '.join(reasons)}")
            continue

        print(f"  ⚠️ {p.name} needs bootstrapping ({', '.join(reasons)})")
        if bootstrap_script.exists():
            code, out = run_command_clean([
                sys.executable,
                str(bootstrap_script),
                "--workspace", str(p),
                "--brain", str(BRAIN_ROOT)
            ])
            if code != 0:
                overall_ok = False
                print(f"  [!] Bootstrap notice for {p.name}: {out}")

    return overall_ok


def run_full_sync(target_project: Optional[Path] = None, dry_run: bool = False, allow_new_universal: bool = False):
    start_time = time.time()
    print("==================================================")
    print("   FULL-SYNC 3.0: UNIVERSAL AGENT SYNCHRONIZER    ")
    print("==================================================")
    if dry_run:
        print("⚡ MODE: AUDIT & DRY RUN (ZERO DISK WRITES)")
    if target_project:
        print(f"🎯 Target Project Workspace: {target_project}")

    # 1. Bi-directional Skill Sync
    s1 = sync_skills(target_project, dry_run=dry_run, allow_new_universal=allow_new_universal)

    # 2. Context Synthesis & Promotion
    s2 = promote_and_reconcile_context(target_project, dry_run=dry_run)

    # 3. Sovereign Vault Sync (<VAULT_BACKUP_DIR>)
    s3 = sync_sovereign_vault(dry_run=dry_run)

    # 4. Project Bootstrapping
    s4 = check_and_bootstrap_projects(target_project, dry_run=dry_run)

    elapsed = time.time() - start_time
    print("\n==================================================")
    print(f"  Full-Sync 3.0 Completed in {elapsed:.2f}s")
    print(f"  - Skill Synchronization:     {'✅ SUCCESS' if s1 else '❌ FAILED'}")
    print(f"  - Context Synthesis:         {'✅ SUCCESS' if s2 else '❌ FAILED'}")
    print(f"  - Sovereign Vault (D:\\):     {'✅ SUCCESS' if s3 else '❌ FAILED'}")
    print(f"  - Project Bootstrap Status:  {'✅ SUCCESS' if s4 else '❌ FAILED'}")
    print("==================================================")


def main():
    parser = argparse.ArgumentParser(description="Full-Sync 3.0 Universal Synchronizer")
    parser.add_argument("--project", type=Path, default=None, help="Target specific project workspace")
    parser.add_argument("--dry-run", action="store_true", help="Audit diffs and promotions without modifying disk")
    parser.add_argument("--skills-only", action="store_true", help="Sync only skills and catalog")
    parser.add_argument("--context-only", action="store_true", help="Synthesize and promote context only")
    parser.add_argument("--vault-only", action="store_true", help="Sync <VAULT_BACKUP_DIR> vault only")
    parser.add_argument("--allow-new-universal", action="store_true", help="Allow promoting beyond the 12 core universal skills")

    args = parser.parse_args()

    if args.skills_only:
        sync_skills(args.project, dry_run=args.dry_run, allow_new_universal=args.allow_new_universal)
    elif args.context_only:
        promote_and_reconcile_context(args.project, dry_run=args.dry_run)
    elif args.vault_only:
        sync_sovereign_vault(dry_run=args.dry_run)
    else:
        run_full_sync(args.project, dry_run=args.dry_run, allow_new_universal=args.allow_new_universal)


if __name__ == "__main__":
    main()
