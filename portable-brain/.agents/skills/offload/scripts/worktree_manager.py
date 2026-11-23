#!/usr/bin/env python3
"""
Local Git Worktree & Branch Isolation Manager (`worktree_manager.py`)

Provides Windows-safe, sibling-directory Git worktree lifecycle management for
isolated multi-agent execution under `offload`:
1. Resolves native Windows `git.exe` (never Cygwin/WSL git unintentionally).
2. Allocates worktrees strictly outside the repository in a sibling `.worktrees`
   root: `<repo_root.parent>/.worktrees/<repo_name>/<worker_id>/<task_slug>`.
3. Enforces sanitized `agent/<worker_id>/<slug>` branch naming.
4. Safely hydrates ignored local configs listed in `.worktreeinclude` while
   blocking `.git` and `..` path traversal.
5. Unlinks Windows NTFS junctions / reparse points BEFORE `git worktree remove`
   so shared targets (e.g., `node_modules`, `.venv`) are never deleted.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# Windows NTFS FILE_ATTRIBUTE_REPARSE_POINT bitmask
FILE_ATTRIBUTE_REPARSE_POINT = 0x400

# Ensure UTF-8 console output on Windows PowerShell / cp1252 terminals
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


class WorktreeError(RuntimeError):
    """Raised when a worktree operation or validation check fails."""


def _is_unwanted_windows_git(path_str: str) -> bool:
    """Return True if a Windows git path belongs to Cygwin, WSL, or MSYS usr/bin."""
    norm = path_str.replace("/", "\\").lower()
    disallowed_markers = (
        "\\cygwin",
        "\\wsl",
        "\\system32\\bash",
        "\\windowsapps\\",
        "\\usr\\bin\\git",
    )
    return any(marker in norm for marker in disallowed_markers)


def resolve_git_exe() -> str:
    """Resolve native Windows git.exe (falling back cleanly, avoiding Cygwin/WSL)."""
    candidate = shutil.which("git")
    if os.name == "nt":
        if candidate and not _is_unwanted_windows_git(candidate) and Path(candidate).is_file():
            return str(Path(candidate).resolve())

        fallbacks: List[Path] = [
            Path(r"C:\Program Files\Git\cmd\git.exe"),
            Path(r"C:\Program Files (x86)\Git\cmd\git.exe"),
        ]
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            fallbacks.append(Path(local_app_data) / "Programs" / "Git" / "cmd" / "git.exe")

        for fb in fallbacks:
            if fb.is_file():
                return str(fb.resolve())
        raise WorktreeError(
            "Unable to locate native Windows git.exe. Checked PATH and standard Git for Windows paths."
        )

    if candidate and Path(candidate).is_file():
        return candidate
    raise WorktreeError("Unable to locate git executable on PATH.")


def run_git(
    args: Sequence[str],
    cwd: Path,
    *,
    check: bool = True,
    git_exe: Optional[str] = None,
) -> subprocess.CompletedProcess[str]:
    """Run a git command in `cwd` using the resolved git executable."""
    exe = git_exe or resolve_git_exe()
    cmd = [exe, "-C", str(cwd), *args]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise WorktreeError(f"git {' '.join(args)} failed (rc={proc.returncode}): {detail}")
    return proc


def sanitize_token(raw: str, label: str = "token") -> str:
    """Sanitize an identifier into lowercase `[a-z0-9_-]`."""
    cleaned = re.sub(r"[^a-z0-9_-]+", "-", raw.strip().lower())
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-_")
    if not cleaned:
        raise WorktreeError(f"Invalid {label}: {raw!r} produces an empty sanitized token.")
    return cleaned


def get_repo_root(repo: str | Path, git_exe: Optional[str] = None) -> Path:
    """Return the resolved top-level directory of the Git repository."""
    repo_path = Path(repo).resolve()
    if not repo_path.exists():
        raise WorktreeError(f"Repository path does not exist: {repo_path}")
    proc = run_git(["rev-parse", "--show-toplevel"], repo_path, git_exe=git_exe)
    return Path(proc.stdout.strip()).resolve()


def discover_repo_root_from_worktree(wt_path: Path, git_exe: Optional[str] = None) -> Path:
    """Discover the main repository root starting from an existing worktree path."""
    proc = run_git(
        ["rev-parse", "--path-format=absolute", "--git-common-dir"],
        wt_path,
        check=False,
        git_exe=git_exe,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        common_dir = Path(proc.stdout.strip()).resolve()
        if common_dir.name == ".git":
            return common_dir.parent.resolve()
    proc_rel = run_git(["rev-parse", "--git-common-dir"], wt_path, git_exe=git_exe)
    common_rel = Path(proc_rel.stdout.strip())
    common_dir = common_rel.resolve() if common_rel.is_absolute() else (wt_path / common_rel).resolve()
    if common_dir.name == ".git":
        return common_dir.parent.resolve()
    return get_repo_root(wt_path, git_exe=git_exe)


def compute_worktrees_base(
    repo_root: Path,
    worktrees_root: Optional[str | Path] = None,
) -> Path:
    """Compute the external `.worktrees` base directory (never inside `repo_root`)."""
    base = Path(worktrees_root).resolve() if worktrees_root else (repo_root.parent / ".worktrees").resolve()
    if base == repo_root or base.is_relative_to(repo_root):
        raise WorktreeError(
            f"Worktrees root {base} must be strictly external to repository {repo_root}."
        )
    return base


def compute_worker_root(
    repo_root: Path,
    worker_id: str,
    worktrees_root: Optional[str | Path] = None,
) -> Path:
    """Compute `<worktrees_base>/<repo_name>/<sanitized_worker_id>`."""
    base = compute_worktrees_base(repo_root, worktrees_root)
    return base / repo_root.name / sanitize_token(worker_id, "worker")


def compute_worktree_path(
    repo_root: Path,
    worker_id: str,
    task_slug: str,
    worktrees_root: Optional[str | Path] = None,
) -> Path:
    """Compute the external worktree path for a worker and task slug."""
    worker_root = compute_worker_root(repo_root, worker_id, worktrees_root)
    wt_path = (worker_root / sanitize_token(task_slug, "task")).resolve()
    if wt_path == repo_root or wt_path.is_relative_to(repo_root):
        raise WorktreeError(f"Refusing worktree path inside repository: {wt_path}")
    return wt_path


def compute_branch_name(worker_id: str, task_slug: str) -> str:
    """Compute canonical branch name `agent/<worker_id>/<slug>`."""
    w = sanitize_token(worker_id, "worker")
    s = sanitize_token(task_slug, "task")
    return f"agent/{w}/{s}"


def _is_unsafe_include_pattern(pattern: str) -> bool:
    """Validate that a `.worktreeinclude` line is relative and never touches `.git` or `..`."""
    if not pattern:
        return True
    normalized = pattern.replace("\\", "/").strip()
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        return True
    if Path(normalized).is_absolute():
        return True
    parts = [p for p in normalized.split("/") if p and p != "."]
    if not parts:
        return True
    if ".." in parts or ".git" in parts:
        return True
    return False


def _copy_if_safe(src: Path, repo_root: Path, wt_path: Path, copied: set[str]) -> None:
    """Copy a single file from `repo_root` to `wt_path` after containment verification."""
    try:
        resolved = src.resolve()
    except OSError:
        return
    if not resolved.is_file() or not resolved.is_relative_to(repo_root):
        return
    rel = resolved.relative_to(repo_root)
    if ".git" in rel.parts or ".." in rel.parts:
        return
    dst = wt_path / rel
    if dst.resolve(strict=False) == resolved:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(resolved, dst)
    copied.add(rel.as_posix())


def hydrate_worktree_include(repo_root: Path, wt_path: Path) -> List[str]:
    """Copy safe matching entries from `<repo_root>/.worktreeinclude` into `wt_path`."""
    include_file = repo_root / ".worktreeinclude"
    if not include_file.is_file():
        return []

    copied: set[str] = set()
    raw_lines = include_file.read_text(encoding="utf-8", errors="replace").splitlines()
    for raw_line in raw_lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if _is_unsafe_include_pattern(line):
            continue
        pattern = line.replace("\\", "/")
        while pattern.startswith("./"):
            pattern = pattern[2:]
        if _is_unsafe_include_pattern(pattern):
            continue

        for match in repo_root.glob(pattern):
            if match.is_file():
                _copy_if_safe(match, repo_root, wt_path, copied)
            elif match.is_dir():
                try:
                    resolved_dir = match.resolve()
                except OSError:
                    continue
                if not resolved_dir.is_relative_to(repo_root):
                    continue
                if ".git" in resolved_dir.relative_to(repo_root).parts:
                    continue
                for dirpath, dirs, files in os.walk(resolved_dir, topdown=True, followlinks=False):
                    dirs[:] = [
                        d for d in dirs
                        if d != ".git" and not os.path.islink(Path(dirpath) / d)
                    ]
                    for fname in files:
                        _copy_if_safe(Path(dirpath) / fname, repo_root, wt_path, copied)
    return sorted(copied)


def _is_reparse_or_link(path: Path) -> tuple[bool, bool]:
    """Return `(is_symlink, is_ntfs_reparse_point)` using lstat (no dereference)."""
    is_link = os.path.islink(path)
    is_reparse = False
    try:
        st = os.lstat(path)
        attrs = getattr(st, "st_file_attributes", 0)
        is_reparse = bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)
    except OSError:
        pass
    return is_link, is_reparse


def find_ntfs_junctions(root_path: Path) -> List[str]:
    """Read-only scan returning symlinks and Windows NTFS reparse points inside `root_path`."""
    if not root_path.exists():
        return []
    found: List[str] = []
    for dirpath, dirs, files in os.walk(root_path, topdown=True, followlinks=False):
        for d in list(dirs):
            p = Path(dirpath) / d
            is_link, is_reparse = _is_reparse_or_link(p)
            if is_link or is_reparse:
                found.append(str(p))
                dirs.remove(d)
        for f in files:
            p = Path(dirpath) / f
            if os.path.islink(p):
                found.append(str(p))
    return found


def _unlink_single_junction_or_symlink(path: Path, is_link: bool, is_reparse: bool) -> None:
    """Remove only the junction/symlink pointer itself without touching its target."""
    if os.name == "nt" and is_reparse and not is_link:
        proc = subprocess.run(
            ["cmd", "/c", "rmdir", str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            raise WorktreeError(f"Failed to unlink NTFS junction {path}: {detail}")
        return

    try:
        os.unlink(path)
    except OSError:
        if os.name == "nt":
            proc = subprocess.run(
                ["cmd", "/c", "rmdir", str(path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if proc.returncode != 0:
                os.rmdir(path)
        else:
            os.rmdir(path)


def unlink_ntfs_junctions(path: Path) -> List[str]:
    """
    Walk `path` top-down without following links, unlink any symlinks or Windows
    NTFS reparse points (junctions), and prune traversal into them so shared
    target directories (e.g. `node_modules`, `.venv`) remain 100% intact.
    """
    root_path = Path(path)
    if not root_path.exists():
        return []

    removed: List[str] = []
    for dirpath, dirs, files in os.walk(root_path, topdown=True, followlinks=False):
        for d in list(dirs):
            child = Path(dirpath) / d
            is_link, is_reparse = _is_reparse_or_link(child)
            if is_link or is_reparse:
                dirs.remove(d)
                _unlink_single_junction_or_symlink(child, is_link, is_reparse)
                removed.append(str(child))
        for f in files:
            child = Path(dirpath) / f
            if os.path.islink(child):
                os.unlink(child)
                removed.append(str(child))
    return removed


def cleanup_empty_worktree_dirs(
    base_dir: Path,
    *,
    repo_name: Optional[str] = None,
) -> List[str]:
    """Remove empty directories under `<worktrees_base>/<repo_name>` bottom-up safely."""
    target = base_dir / repo_name if repo_name else base_dir
    if not target.exists():
        return []

    removed: List[str] = []
    for dirpath, dirs, files in os.walk(target, topdown=False, followlinks=False):
        current = Path(dirpath)
        is_link, is_reparse = _is_reparse_or_link(current)
        if is_link or is_reparse:
            continue
        try:
            if not any(current.iterdir()):
                current.rmdir()
                removed.append(str(current))
        except OSError:
            pass

    for ancestor in (target, base_dir):
        if ancestor.exists():
            is_link, is_reparse = _is_reparse_or_link(ancestor)
            if not is_link and not is_reparse:
                try:
                    if not any(ancestor.iterdir()):
                        ancestor.rmdir()
                        removed.append(str(ancestor))
                except OSError:
                    pass
    return removed


def parse_worktree_list(porcelain_output: str) -> List[Dict[str, Any]]:
    """Parse `git worktree list --porcelain` output into structured dicts."""
    entries: List[Dict[str, Any]] = []
    current: Dict[str, Any] = {}
    for line in porcelain_output.splitlines():
        if not line.strip():
            if current:
                entries.append(current)
                current = {}
            continue
        key, _, val = line.partition(" ")
        if key == "worktree":
            current["path"] = str(Path(val).resolve()) if Path(val).exists() else val
        elif key == "HEAD":
            current["head"] = val.strip()
        elif key == "branch":
            current["branch"] = val.strip().removeprefix("refs/heads/")
        elif key in ("bare", "detached", "locked", "prunable"):
            current[key] = val.strip() if val else True
        else:
            current[key] = val.strip() if val else True
    if current:
        entries.append(current)
    return entries


@dataclass
class WorktreeTarget:
    """Resolved repository root, worktree path, and optional branch name."""

    repo_root: Path
    wt_path: Path
    branch: Optional[str]


def _resolve_target(args: argparse.Namespace, git_exe: str) -> WorktreeTarget:
    """Resolve WorktreeTarget from either `--path` or `--repo/--worker/--task`."""
    if getattr(args, "path", None):
        wt_path = Path(args.path).resolve()
        repo_root = (
            get_repo_root(args.repo, git_exe=git_exe)
            if getattr(args, "repo", None)
            else discover_repo_root_from_worktree(wt_path, git_exe=git_exe)
        )
        branch: Optional[str] = None
        if wt_path.exists():
            proc = run_git(["rev-parse", "--abbrev-ref", "HEAD"], wt_path, check=False, git_exe=git_exe)
            if proc.returncode == 0:
                branch = proc.stdout.strip()
        return WorktreeTarget(repo_root=repo_root, wt_path=wt_path, branch=branch)

    if not (getattr(args, "repo", None) and getattr(args, "worker", None) and getattr(args, "task", None)):
        raise WorktreeError("Provide either --path or all of --repo, --worker, and --task.")

    repo_root = get_repo_root(args.repo, git_exe=git_exe)
    wt_path = compute_worktree_path(
        repo_root,
        args.worker,
        args.task,
        worktrees_root=getattr(args, "worktrees_root", None),
    )
    branch = compute_branch_name(args.worker, args.task)
    return WorktreeTarget(repo_root=repo_root, wt_path=wt_path, branch=branch)


def _run_verify_cmd(wt_path: Path, command: str) -> Dict[str, Any]:
    """Execute a verification command inside `wt_path` and return telemetry."""
    if not wt_path.is_dir():
        raise WorktreeError(f"Worktree directory does not exist: {wt_path}")
    t0 = time.monotonic()
    proc = subprocess.run(
        command,
        shell=True,
        cwd=str(wt_path),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    duration = round(time.monotonic() - t0, 3)
    return {
        "command": command,
        "cwd": str(wt_path),
        "returncode": proc.returncode,
        "passed": proc.returncode == 0,
        "duration_s": duration,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def _remove_worktree_internal(
    repo_root: Path,
    wt_path: Path,
    *,
    force: bool = False,
    worktrees_root: Optional[str | Path] = None,
    git_exe: str,
) -> Dict[str, Any]:
    """Unlink NTFS junctions, remove git worktree, prune, and clean empty dirs."""
    unlinked = unlink_ntfs_junctions(wt_path)
    remove_args = ["worktree", "remove"]
    if force:
        remove_args.append("--force")
    remove_args.append(str(wt_path))
    run_git(remove_args, repo_root, git_exe=git_exe)
    run_git(["worktree", "prune"], repo_root, git_exe=git_exe)
    base = compute_worktrees_base(repo_root, worktrees_root)
    cleaned_dirs = cleanup_empty_worktree_dirs(base, repo_name=repo_root.name)
    return {
        "unlinked_junctions": unlinked,
        "cleaned_dirs": cleaned_dirs,
    }


def cmd_create(args: argparse.Namespace) -> Dict[str, Any]:
    git_exe = resolve_git_exe()
    repo_root = get_repo_root(args.repo, git_exe=git_exe)
    wt_path = compute_worktree_path(
        repo_root,
        args.worker,
        args.task,
        worktrees_root=args.worktrees_root,
    )
    branch = compute_branch_name(args.worker, args.task)
    if wt_path.exists():
        raise WorktreeError(f"Target worktree path already exists: {wt_path}")

    wt_path.parent.mkdir(parents=True, exist_ok=True)
    run_git(
        ["worktree", "add", "-b", branch, str(wt_path), args.base],
        repo_root,
        git_exe=git_exe,
    )
    run_git(["config", "core.fileMode", "false"], wt_path, git_exe=git_exe)
    run_git(["config", "core.longpaths", "true"], wt_path, git_exe=git_exe)
    hydrated = hydrate_worktree_include(repo_root, wt_path)

    return {
        "ok": True,
        "action": "create",
        "git_exe": git_exe,
        "repo_root": str(repo_root),
        "worktree_path": str(wt_path),
        "branch": branch,
        "base": args.base,
        "hydrated_files": hydrated,
    }


def cmd_list(args: argparse.Namespace) -> Dict[str, Any]:
    git_exe = resolve_git_exe()
    repo_root = get_repo_root(args.repo, git_exe=git_exe)
    proc = run_git(["worktree", "list", "--porcelain"], repo_root, git_exe=git_exe)
    return {
        "ok": True,
        "action": "list",
        "repo_root": str(repo_root),
        "worktrees": parse_worktree_list(proc.stdout),
    }


def cmd_status(args: argparse.Namespace) -> Dict[str, Any]:
    git_exe = resolve_git_exe()
    target = _resolve_target(args, git_exe)
    exists = target.wt_path.is_dir()
    if not exists:
        return {
            "ok": True,
            "action": "status",
            "exists": False,
            "repo_root": str(target.repo_root),
            "worktree_path": str(target.wt_path),
            "branch": target.branch,
        }

    head = run_git(["rev-parse", "HEAD"], target.wt_path, git_exe=git_exe).stdout.strip()
    branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], target.wt_path, git_exe=git_exe).stdout.strip()
    porcelain = run_git(["status", "--porcelain"], target.wt_path, git_exe=git_exe).stdout.splitlines()
    junctions = find_ntfs_junctions(target.wt_path)
    return {
        "ok": True,
        "action": "status",
        "exists": True,
        "repo_root": str(target.repo_root),
        "worktree_path": str(target.wt_path),
        "branch": branch,
        "head": head,
        "dirty": bool(porcelain),
        "changed_files": porcelain,
        "junctions": junctions,
    }


def cmd_verify(args: argparse.Namespace) -> Dict[str, Any]:
    wt_path = Path(args.path).resolve()
    result = _run_verify_cmd(wt_path, args.cmd)
    return {
        "ok": result["passed"],
        "action": "verify",
        **result,
    }


def cmd_merge(args: argparse.Namespace) -> Dict[str, Any]:
    git_exe = resolve_git_exe()
    repo_root = get_repo_root(args.repo, git_exe=git_exe)
    wt_path = compute_worktree_path(
        repo_root,
        args.worker,
        args.task,
        worktrees_root=args.worktrees_root,
    )
    branch = compute_branch_name(args.worker, args.task)

    if not wt_path.is_dir():
        raise WorktreeError(f"Worktree does not exist: {wt_path}")

    verify_result: Optional[Dict[str, Any]] = None
    if args.verify_cmd:
        verify_result = _run_verify_cmd(wt_path, args.verify_cmd)
        if not verify_result["passed"]:
            raise WorktreeError(
                f"Verification command failed (rc={verify_result['returncode']}): "
                f"{(verify_result['stderr'] or verify_result['stdout']).strip()}"
            )

    dirty_wt = run_git(["status", "--porcelain"], wt_path, git_exe=git_exe).stdout.strip()
    if dirty_wt:
        raise WorktreeError(f"Refusing to merge dirty worktree {wt_path}:\n{dirty_wt}")

    dirty_repo = run_git(["status", "--porcelain"], repo_root, git_exe=git_exe).stdout.strip()
    if dirty_repo:
        raise WorktreeError(f"Refusing to merge into dirty repository {repo_root}:\n{dirty_repo}")

    rebase_proc = run_git(["rebase", args.into], wt_path, check=False, git_exe=git_exe)
    if rebase_proc.returncode != 0:
        run_git(["rebase", "--abort"], wt_path, check=False, git_exe=git_exe)
        detail = (rebase_proc.stderr or rebase_proc.stdout or "").strip()
        raise WorktreeError(f"Rebase of {branch} onto {args.into} failed: {detail}")

    current_main_branch = run_git(
        ["rev-parse", "--abbrev-ref", "HEAD"], repo_root, git_exe=git_exe
    ).stdout.strip()
    if current_main_branch != args.into:
        run_git(["checkout", args.into], repo_root, git_exe=git_exe)

    run_git(["merge", "--ff-only", branch], repo_root, git_exe=git_exe)

    teardown_info: Dict[str, Any] = {}
    if not args.keep:
        teardown_info = _remove_worktree_internal(
            repo_root,
            wt_path,
            force=False,
            worktrees_root=args.worktrees_root,
            git_exe=git_exe,
        )
        run_git(["branch", "-d", branch], repo_root, git_exe=git_exe)

    return {
        "ok": True,
        "action": "merge",
        "repo_root": str(repo_root),
        "worktree_path": str(wt_path),
        "branch": branch,
        "into": args.into,
        "kept": bool(args.keep),
        "verify": verify_result,
        **teardown_info,
    }


def cmd_remove(args: argparse.Namespace) -> Dict[str, Any]:
    git_exe = resolve_git_exe()
    target = _resolve_target(args, git_exe)
    if not target.wt_path.exists():
        run_git(["worktree", "prune"], target.repo_root, git_exe=git_exe)
        return {
            "ok": True,
            "action": "remove",
            "repo_root": str(target.repo_root),
            "worktree_path": str(target.wt_path),
            "already_missing": True,
        }

    teardown_info = _remove_worktree_internal(
        target.repo_root,
        target.wt_path,
        force=bool(args.force),
        worktrees_root=getattr(args, "worktrees_root", None),
        git_exe=git_exe,
    )
    return {
        "ok": True,
        "action": "remove",
        "repo_root": str(target.repo_root),
        "worktree_path": str(target.wt_path),
        **teardown_info,
    }


def cmd_prune(args: argparse.Namespace) -> Dict[str, Any]:
    git_exe = resolve_git_exe()
    repo_root = get_repo_root(args.repo, git_exe=git_exe)
    run_git(["worktree", "prune"], repo_root, git_exe=git_exe)
    base = compute_worktrees_base(repo_root, args.worktrees_root)
    cleaned_dirs = cleanup_empty_worktree_dirs(base, repo_name=repo_root.name)
    return {
        "ok": True,
        "action": "prune",
        "repo_root": str(repo_root),
        "worktrees_base": str(base),
        "cleaned_dirs": cleaned_dirs,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Local Git Worktree & Branch Isolation Manager for offload."
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_create = sub.add_parser("create", help="Create an isolated sibling worktree and agent branch.")
    p_create.add_argument("--repo", required=True, help="Path inside the target Git repository.")
    p_create.add_argument("--worker", required=True, help="Worker identifier.")
    p_create.add_argument("--task", required=True, help="Task slug.")
    p_create.add_argument("--base", default="HEAD", help="Base ref/commit (default: HEAD).")
    p_create.add_argument("--worktrees-root", default=None, help="Optional override for .worktrees root.")
    p_create.set_defaults(func=cmd_create)

    p_list = sub.add_parser("list", help="List active worktrees for a repository.")
    p_list.add_argument("--repo", required=True, help="Path inside the target Git repository.")
    p_list.set_defaults(func=cmd_list)

    p_status = sub.add_parser("status", help="Inspect worktree cleanliness, branch, and junctions.")
    p_status.add_argument("--repo", help="Path inside the target Git repository.")
    p_status.add_argument("--worker", help="Worker identifier.")
    p_status.add_argument("--task", help="Task slug.")
    p_status.add_argument("--path", help="Direct path to an existing worktree.")
    p_status.add_argument("--worktrees-root", default=None, help="Optional override for .worktrees root.")
    p_status.set_defaults(func=cmd_status)

    p_verify = sub.add_parser("verify", help="Run a verification command inside a worktree.")
    p_verify.add_argument("--path", required=True, help="Path to the worktree.")
    p_verify.add_argument("--cmd", required=True, help="Verification command to run.")
    p_verify.set_defaults(func=cmd_verify)

    p_merge = sub.add_parser("merge", help="Verify, rebase, fast-forward merge, and clean up worktree.")
    p_merge.add_argument("--repo", required=True, help="Path inside the target Git repository.")
    p_merge.add_argument("--worker", required=True, help="Worker identifier.")
    p_merge.add_argument("--task", required=True, help="Task slug.")
    p_merge.add_argument("--into", default="main", help="Target branch to rebase onto and ff-merge into.")
    p_merge.add_argument("--verify-cmd", default=None, help="Optional verification command run before merge.")
    p_merge.add_argument("--keep", action="store_true", help="Keep worktree and branch after merging.")
    p_merge.add_argument("--worktrees-root", default=None, help="Optional override for .worktrees root.")
    p_merge.set_defaults(func=cmd_merge)

    p_remove = sub.add_parser("remove", help="Junction-safe teardown of a worktree.")
    p_remove.add_argument("--repo", help="Path inside the target Git repository.")
    p_remove.add_argument("--worker", help="Worker identifier.")
    p_remove.add_argument("--task", help="Task slug.")
    p_remove.add_argument("--path", help="Direct path to an existing worktree.")
    p_remove.add_argument("--force", action="store_true", help="Pass --force to git worktree remove.")
    p_remove.add_argument("--worktrees-root", default=None, help="Optional override for .worktrees root.")
    p_remove.set_defaults(func=cmd_remove)

    p_prune = sub.add_parser("prune", help="Prune stale git worktrees and empty .worktrees directories.")
    p_prune.add_argument("--repo", required=True, help="Path inside the target Git repository.")
    p_prune.add_argument("--worktrees-root", default=None, help="Optional override for .worktrees root.")
    p_prune.set_defaults(func=cmd_prune)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = args.func(args)
        print(json.dumps(payload, indent=2))
        return 0 if payload.get("ok", True) else int(payload.get("returncode", 1) or 1)
    except WorktreeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
