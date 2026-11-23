#!/usr/bin/env python3
"""
Offload Message Board & Cross-Instance Antigravity Orchestration Engine (`offload_manager.py`)

Enables a primary Antigravity Orchestrator session to delegate tasks, multi-agent subagents,
and swarms to a secondary Antigravity CLI worker running in the target project directory.

Key Guarantees:
1. Co-Folder Workspace Disambiguation: When `brain` is co-attached alongside a project folder
   (e.g., `hi/` + `brain/`), resolution strictly selects `<project>/offload/`. `brain/offload/`
   is selected ONLY when targeting `brain` directly.
2. Frictionless Skill Injection: Automatically embeds `auto-skill/SKILL.md` and resolves exact
   absolute `SKILL.md` paths for requested skills (no slash command typing required).
3. Two-Way Status Bar & Zero-Token Listener: Maintains live Orchestrator <-> CLI Worker
   heartbeats in `status.json` and `BOARD.md`, and provides a blocking `worker-listen` command
   that wakes the CLI agent only when work arrives.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import datetime
import json
import os
import re
import socket
import sys
import threading
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure UTF-8 console output on Windows PowerShell / cp1252 terminals
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _to_host_path(raw: Any, target_os: Optional[str] = None) -> Path:
    """Translate file:// URIs and Windows/WSL paths (C:\\... <-> /mnt/<drive>/...) cleanly for the host OS."""
    s = str(raw).strip().strip("\"'")
    if s.lower().startswith("file://"):
        s = urllib.parse.unquote(s)
        s = re.sub(r"^file://(?:localhost)?", "", s, flags=re.IGNORECASE)
        m_win = re.match(r"^/([A-Za-z]:[/\\]?.*)$", s)
        if m_win:
            s = m_win.group(1)

    eff_os = target_os or os.name
    if eff_os == "posix":
        m = re.match(r"^([A-Za-z]):[/\\]*(.*)$", s)
        if m:
            drive, rest = m.group(1).lower(), m.group(2).replace("\\", "/").lstrip("/")
            mnt_base = Path(f"/mnt/{drive}")
            if target_os == "posix" or mnt_base.exists():
                return Path(f"/mnt/{drive}/{rest}") if rest else mnt_base
    elif eff_os == "nt":
        m = re.match(r"^/mnt/([A-Za-z])(?:/(.*))?$", s)
        if m:
            drive = m.group(1).upper()
            rest = (m.group(2) or "").replace("/", "\\").lstrip("\\")
            return Path(f"{drive}:\\{rest}") if rest else Path(f"{drive}:\\")
    return Path(s)


def _to_wsl_path(path: Any) -> str:
    """Convert a Windows drive path (C:\\...) into its WSL /mnt/<drive>/... equivalent."""
    s = str(path).strip().strip("\"'")
    m = re.match(r"^([A-Za-z]):[/\\]*(.*)$", s)
    if m:
        drive = m.group(1).lower()
        rest = m.group(2).replace("\\", "/").lstrip("/")
        return f"/mnt/{drive}/{rest}" if rest else f"/mnt/{drive}"
    return s.replace("\\", "/")


def _find_brain_root() -> Path:
    """Locate the Central Brain root directory."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / ".agents").is_dir() and (parent / "project_map.md").is_file():
            return parent
    cand = _to_host_path(r"./")
    if cand.is_dir():
        return cand
    return Path(r"./")


def _to_display_path(path: Any) -> str:
    """Convert POSIX /mnt/<drive>/... paths back to canonical Windows <DRIVE>:\\... for display in IDEs & markdowns."""
    s = str(path).strip()
    m = re.match(r"^/mnt/([a-zA-Z])(?:/(.*))?$", s)
    if m:
        drive = m.group(1).upper()
        rest = (m.group(2) or "").replace("/", "\\").lstrip("\\")
        return f"{drive}:\\{rest}" if rest else f"{drive}:\\"
    return s


def _infer_host_home(brain_root: Path) -> Path:
    """Resolve Windows host home even inside WSL with custom HOME=.agy_pro2."""
    if os.name == "posix":
        parts = brain_root.resolve().parts
        if len(parts) >= 5 and parts[1] == "mnt" and parts[3].lower() == "users":
            cand = Path("/") / parts[1] / parts[2] / parts[3] / parts[4]
            if cand.is_dir():
                return cand
    return Path.home()


BRAIN_ROOT = _find_brain_root().resolve()
USER_HOME = _infer_host_home(BRAIN_ROOT)
BUILTIN_SKILLS_DIR = USER_HOME / ".gemini" / "antigravity" / "builtin" / "skills"
CONFIG_SKILLS_DIR = USER_HOME / ".gemini" / "config" / "skills"
BRAIN_UNIVERSAL_SKILLS_DIR = BRAIN_ROOT / ".agents" / "skills"
AUTO_SKILL_MD = BRAIN_UNIVERSAL_SKILLS_DIR / "auto-skill" / "SKILL.md"
SELECT_SKILL_PY = BRAIN_UNIVERSAL_SKILLS_DIR / "auto-skill" / "scripts" / "select_skill.py"
SKILL_REGISTRY_JSON = BRAIN_UNIVERSAL_SKILLS_DIR / "auto-skill" / "references" / "skill_registry.json"

WORKER_LISTEN_TTL_SEC = 45.0
WORKER_BUSY_TTL_SEC = 900.0
ORCHESTRATOR_TTL_SEC = 600.0
MAIN_STALE_TTL_SEC = 300.0

AGENT_ROLE_PREFIXES: Dict[str, str] = {
    "main": "main",
    "worker": "worker",
    "collaborator": "collab",
}

SKILL_ALIASES: Dict[str, str] = {
    "teamwork": "native_swarm",
    "swarm": "native_swarm",
    "teamwork-preview": "native_swarm",
    "workflow": "run-workflow",
    "workflows": "run-workflow",
    "antigravity-guide": "antigravity_guide",
    "generative-ui": "generative_ui",
    "swarm-monitor": "swarm_monitor",
    "swarm-narrator": "swarm_narrator",
    "audit": "exhaustive-audit-and-repair",
    "search": "web-search-orchestrator",
    "deep-research": "deep-thinking",
    "hermes": "hermes-agent-core",
    "ui": "ui-design-engine",
    "docs": "document-forge",
    "sync": "full-sync",
}

PROJECT_ALIASES: Dict[str, str] = {
    "krpg": "AWAKEN1",
    "awaken": "AWAKEN1",
    "appwrite": "flh-music",
    "flh-one": "flh-one",
}


def _now_epoch() -> float:
    return time.time()


def _now_iso() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _format_age(seconds: Optional[float]) -> str:
    if seconds is None or seconds < 0:
        return "never"
    if seconds < 5:
        return "just now"
    if seconds < 60:
        return f"{int(seconds)}s ago"
    if seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s ago"
    return f"{int(seconds // 3600)}h {int((seconds % 3600) // 60)}m ago"


def atomic_write_text(target_path: Path, content: str) -> None:
    """Atomically write text using a unique temporary file and Windows-safe retry replace."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name = f".tmp.{target_path.name}.{os.getpid()}.{uuid.uuid4().hex[:6]}"
    tmp_path = target_path.parent / tmp_name
    try:
        tmp_path.write_text(content, encoding="utf-8")
        for attempt in range(6):
            try:
                _assert_offload_lock_owned()
                os.replace(tmp_path, target_path)
                return
            except OSError:
                if attempt == 5:
                    raise
                time.sleep(0.025 * (2 ** attempt))
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass


def atomic_write_json(target_path: Path, data: Dict[str, Any]) -> None:
    atomic_write_text(target_path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def safe_read_json(target_path: Path, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Read JSON with short retry in case another process is midway through an atomic replace."""
    for attempt in range(5):
        if not target_path.exists():
            return dict(default) if default is not None else {}
        try:
            return json.loads(target_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, PermissionError, OSError):
            time.sleep(0.02 * (attempt + 1))
    return dict(default) if default is not None else {}


_THREAD_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: Dict[str, threading.RLock] = {}
_LOCK_STATE = threading.local()


def _get_thread_lock(key: str) -> threading.RLock:
    with _THREAD_LOCKS_GUARD:
        lock = _THREAD_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _THREAD_LOCKS[key] = lock
        return lock


_OFFLOAD_LOCK_TTL = 30.0
_OFFLOAD_LOCK_DIR = ".offload.lock.d"
_OFFLOAD_LOCK_HOST = (socket.gethostname(), os.name)


def _lock_owner_alive(owner: Path) -> bool:
    """Check liveness only for owners in this host's OS process namespace."""
    try:
        data = json.loads(owner.read_text(encoding="utf-8"))
        if (data["host"], data["os"]) != _OFFLOAD_LOCK_HOST:
            return False
        pid = int(data["pid"])
        if pid <= 0:
            return False
        if os.name == "nt":
            import ctypes

            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.argtypes = (ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong)
            kernel.OpenProcess.restype = ctypes.c_void_p
            kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
            kernel.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_ulong)
            kernel.WaitForSingleObject.restype = ctypes.c_ulong
            handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
            if not handle:
                return ctypes.get_last_error() == 5  # Access denied is not proof of exit.
            try:
                return kernel.WaitForSingleObject(handle, 0) != 0
            finally:
                kernel.CloseHandle(handle)
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except (ValueError, KeyError, TypeError, OSError):
        return False


def _drop_lock_owner(owner: Path) -> None:
    # Only the process that removes this particular owner token may remove the
    # directory. Another contender may already have acquired a newer token.
    try:
        owner.unlink()
    except FileNotFoundError:
        return
    try:
        owner.parent.rmdir()
    except OSError:
        pass


def _reap_stale_lock(lock_dir: Path, ttl: float) -> None:
    try:
        owners = list(lock_dir.glob("owner.*.json"))
        if not owners:
            # A worker can die between mkdir and owner publication. rmdir only
            # removes empty directories; acquisition also verifies its identity.
            if time.time() - lock_dir.stat().st_mtime >= ttl:
                lock_dir.rmdir()
            return
        for owner in owners:
            observed = owner.stat()
            if time.time() - observed.st_mtime < ttl or _lock_owner_alive(owner):
                continue
            if owner.stat().st_mtime_ns == observed.st_mtime_ns:
                _drop_lock_owner(owner)
    except OSError:
        # Another process may have released or renewed the lock.
        return


def _acquire_directory_lock(lock_dir: Path, timeout: float) -> Path:
    deadline = time.monotonic() + max(0.0, timeout)
    delay = 0.01
    while True:
        try:
            os.mkdir(lock_dir)
        except FileExistsError:
            _reap_stale_lock(lock_dir, _OFFLOAD_LOCK_TTL)
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for offload lock: {lock_dir}") from None
            time.sleep(delay)
            delay = min(0.05, delay * 1.25)
            continue

        owner = lock_dir / f"owner.{uuid.uuid4().hex}.json"
        try:
            initial = lock_dir.stat()
            with owner.open("x", encoding="utf-8") as handle:
                json.dump({
                    "token": owner.stem.removeprefix("owner."),
                    "pid": os.getpid(),
                    "host": _OFFLOAD_LOCK_HOST[0],
                    "os": _OFFLOAD_LOCK_HOST[1],
                    "created_at": time.time(),
                }, handle)
                handle.flush()
                os.fsync(handle.fileno())
            current = lock_dir.stat()
            if not os.path.samestat(initial, current) or set(lock_dir.iterdir()) != {owner}:
                raise RuntimeError(f"Offload lock ownership changed during acquisition: {lock_dir}")
            return owner
        except BaseException:
            _drop_lock_owner(owner)
            raise


def _renew_directory_lock(owner: Path, stop: threading.Event) -> None:
    while not stop.wait(_OFFLOAD_LOCK_TTL / 3):
        try:
            os.utime(owner, None)
        except FileNotFoundError:
            return
        except OSError:
            # A transient Windows open can block this renewal; retry next tick.
            continue


def _assert_offload_lock_owned() -> None:
    for owner in getattr(_LOCK_STATE, "owners", {}).values():
        if not owner.is_file():
            raise RuntimeError(f"Lost offload lock ownership: {owner.parent}")


@contextmanager
def offload_lock(offload_dir: Path, timeout: float = 15.0):
    """Serialize board transactions across Windows and WSL with atomic mkdir."""
    offload_dir.mkdir(parents=True, exist_ok=True)
    lock_dir = offload_dir.resolve() / _OFFLOAD_LOCK_DIR
    key = os.path.normcase(str(lock_dir))
    thread_lock = _get_thread_lock(key)
    owners = getattr(_LOCK_STATE, "owners", None)
    if owners is None:
        owners = _LOCK_STATE.owners = {}

    with thread_lock:
        if key in owners:
            yield
            return

        owner = _acquire_directory_lock(lock_dir, timeout)
        stop = threading.Event()
        heartbeat = threading.Thread(target=_renew_directory_lock, args=(owner, stop), daemon=True)
        owners[key] = owner
        try:
            heartbeat.start()
            yield
        finally:
            stop.set()
            if heartbeat.ident is not None:
                heartbeat.join()
            owners.pop(key, None)
            _drop_lock_owner(owner)


def _load_status(offload_dir: Path, project_slug: str = "", project_root: Optional[Path] = None) -> Dict[str, Any]:
    """Read status.json with safe retry, default fallback, and V3 agents dict normalization."""
    status_path = offload_dir / "status.json"
    default_val = _default_status(project_slug, project_root or BRAIN_ROOT) if (project_slug and project_root) else {}
    data = safe_read_json(status_path, default_val)
    if not isinstance(data, dict):
        data = dict(default_val)
    if not isinstance(data.get("agents"), dict):
        data["agents"] = {}
    return data


def _save_status(offload_dir: Path, status_data: Dict[str, Any]) -> None:
    """Atomically write status.json under Windows-safe replace."""
    status_path = offload_dir / "status.json"
    atomic_write_json(status_path, status_data)


def discover_all_targets(include_brain: bool = True) -> Dict[str, Path]:
    """Discover all registered project workspaces from skill_reconciler / project_map.md plus brain."""
    projects: Dict[str, Path] = {}

    # Try SkillReconciler first for exact parity with full-sync
    reconciler_dir = BRAIN_UNIVERSAL_SKILLS_DIR / "full-sync" / "scripts"
    if reconciler_dir.is_dir():
        if str(reconciler_dir) not in sys.path:
            sys.path.insert(0, str(reconciler_dir))
        try:
            from skill_reconciler import SkillReconciler  # type: ignore

            projects.update(SkillReconciler(brain_root=BRAIN_ROOT).discover_projects())
        except Exception:
            pass

    # Fallback / supplement directly from project_map.md
    proj_map = BRAIN_ROOT / "project_map.md"
    if proj_map.is_file():
        for line in proj_map.read_text(encoding="utf-8", errors="replace").splitlines():
            if "|" not in line:
                continue
            for part in line.split("|"):
                cleaned = part.strip()
                if cleaned.startswith("`") and cleaned.endswith("`"):
                    raw = cleaned.strip("`").strip()
                    if any(drive in raw for drive in ("C:\\", "C:/", "D:\\", "D:/")):
                        p = _to_host_path(raw)
                        if p.exists() and p.is_dir():
                            try:
                                resolved = p.resolve()
                            except Exception:
                                resolved = p
                            if resolved != BRAIN_ROOT:
                                projects.setdefault(resolved.name, resolved)

    # Normalize paths
    normalized: Dict[str, Path] = {}
    for slug, path in projects.items():
        p_norm = _to_host_path(path) if os.name == "posix" else path
        try:
            normalized[slug] = p_norm.resolve()
        except Exception:
            normalized[slug] = p_norm

    if include_brain:
        normalized["brain"] = BRAIN_ROOT

    return normalized


def _is_within_or_equal(child: Path, parent: Path) -> bool:
    try:
        c_res = child.resolve()
        p_res = parent.resolve()
        c_res.relative_to(p_res)
        return True
    except ValueError:
        c_str = str(child.resolve())
        p_str = str(parent.resolve())
        if os.name == "nt" or (c_str.startswith("/mnt/") and p_str.startswith("/mnt/")):
            try:
                Path(c_str.lower()).relative_to(Path(p_str.lower()))
                return True
            except ValueError:
                return False
        return False


def _is_container_or_root(p: Path) -> bool:
    try:
        resolved = p.resolve()
    except Exception:
        resolved = p
    if resolved.parent == resolved:
        return True
    name_low = resolved.name.lower()
    if name_low in ("desktop", "pjct", "users", "home", "mnt"):
        return True
    if resolved in (Path.home(), USER_HOME):
        return True
    return False


def _match_path_to_project(candidate_path: Path, projects: Dict[str, Path]) -> Optional[Tuple[str, Path]]:
    """Map an arbitrary filesystem path to the best matching non-brain project or brain."""
    try:
        resolved = candidate_path.resolve()
    except Exception:
        resolved = candidate_path

    # Longest-prefix match among non-brain registered projects
    best_match: Optional[Tuple[int, str, Path]] = None
    for slug, root in projects.items():
        if slug.lower() == "brain" or root.resolve() == BRAIN_ROOT:
            continue
        if _is_within_or_equal(resolved, root):
            depth = len(root.parts)
            if best_match is None or depth > best_match[0]:
                best_match = (depth, slug, root)

    if best_match:
        return best_match[1], best_match[2]

    if _is_within_or_equal(resolved, BRAIN_ROOT):
        return "brain", BRAIN_ROOT

    return None


def resolve_target_project(
    project_arg: Optional[str] = None,
    workspaces_arg: Optional[str] = None,
    cwd: Optional[Path] = None,
) -> Tuple[str, Path]:
    """
    Resolve target project enforcing the Co-Folder Workspace Disambiguation Invariant:
    - If `--project` explicitly targets a project or `brain`, honor it.
    - If `--workspaces` (or AGY_WORKSPACES) contains both `<project>` and `brain`,
      strictly select `<project>` and ignore the `brain` co-folder.
    - Only select `brain` if `brain` is the sole workspace or explicitly requested.
    """
    projects = discover_all_targets(include_brain=True)
    lower_lookup = {slug.lower(): (slug, path) for slug, path in projects.items()}

    # 1. Explicit --project flag
    if project_arg and project_arg.strip():
        raw = project_arg.strip().strip("\"'")
        low = raw.lower()
        if low == "brain":
            return "brain", BRAIN_ROOT
        if low in lower_lookup:
            return lower_lookup[low]
        if low in PROJECT_ALIASES and PROJECT_ALIASES[low].lower() in lower_lookup:
            return lower_lookup[PROJECT_ALIASES[low].lower()]

        p = _to_host_path(raw)
        if p.exists() and p.is_dir():
            matched = _match_path_to_project(p, projects)
            if matched:
                return matched
            if not _is_container_or_root(p):
                try:
                    res_p = p.resolve()
                except Exception:
                    res_p = p
                return res_p.name, res_p

        raise ValueError(
            f"Unknown project '{project_arg}'. Available targets: {', '.join(sorted(projects.keys()))}"
        )

    # 2. Multi-workspace co-folder list (--workspaces or AGY_WORKSPACES)
    ws_raw = workspaces_arg or os.environ.get("AGY_WORKSPACES", "")
    if ws_raw.strip():
        tokens = [t.strip().strip("\"'") for t in re.split(r"[;,]+", ws_raw) if t.strip()]
        non_brain_matches: List[Tuple[str, Path]] = []
        has_brain = False
        for tok in tokens:
            tok_path = _to_host_path(tok)
            matched = _match_path_to_project(tok_path, projects)
            if not matched:
                tok_low = tok.lower()
                if tok_low in lower_lookup:
                    matched = lower_lookup[tok_low]
                elif tok_path.exists() and tok_path.is_dir():
                    if _is_within_or_equal(tok_path, BRAIN_ROOT):
                        matched = ("brain", BRAIN_ROOT)
                    elif not _is_container_or_root(tok_path):
                        try:
                            res_tok = tok_path.resolve()
                        except Exception:
                            res_tok = tok_path
                        matched = (res_tok.name, res_tok)
            if matched:
                if matched[0].lower() == "brain" or matched[1].resolve() == BRAIN_ROOT:
                    has_brain = True
                else:
                    non_brain_matches.append(matched)

        if non_brain_matches:
            return non_brain_matches[0]
        if has_brain:
            return "brain", BRAIN_ROOT

    # 3. Inspect current working directory
    active_cwd = (cwd or Path.cwd()).resolve()
    matched = _match_path_to_project(active_cwd, projects)
    if matched:
        if matched[0].lower() == "brain" or matched[1].resolve() == BRAIN_ROOT:
            if not project_arg and not (workspaces_arg or os.environ.get("AGY_WORKSPACES", "").strip()):
                sys.stderr.write(
                    "[Co-Folder Guard] Resolved to 'brain' from CWD without --project/--workspaces. "
                    "If working in another project with brain attached, pass --workspaces \"<ws1>;<ws2>\" or --project <name>.\n"
                )
            return "brain", BRAIN_ROOT
        return matched

    if _is_within_or_equal(active_cwd, BRAIN_ROOT):
        if not project_arg and not (workspaces_arg or os.environ.get("AGY_WORKSPACES", "").strip()):
            sys.stderr.write(
                "[Co-Folder Guard] Resolved to 'brain' from CWD without --project/--workspaces. "
                "If working in another project with brain attached, pass --workspaces \"<ws1>;<ws2>\" or --project <name>.\n"
            )
        return "brain", BRAIN_ROOT

    # Otherwise walk up max 5 parents (stopping above Desktop/PJCT/home/root) for offload/ or .git/
    curr = active_cwd
    found_parent: Optional[Path] = None
    for _ in range(5):
        if _is_container_or_root(curr):
            break
        if (curr / "offload").is_dir() or (curr / ".git").is_dir():
            found_parent = curr
            break
        if curr.parent == curr:
            break
        curr = curr.parent

    if found_parent and not _is_container_or_root(found_parent):
        return found_parent.name, found_parent

    if not _is_container_or_root(active_cwd):
        return active_cwd.name, active_cwd

    return "brain", BRAIN_ROOT


def _collect_skill_entries(base_dir: Path, tier: str) -> List[Dict[str, str]]:
    """Scan a skill directory root for immediate `<skill>/SKILL.md` files."""
    entries: List[Dict[str, str]] = []
    if not base_dir.is_dir():
        return entries
    for sub in sorted(base_dir.iterdir(), key=lambda p: p.name.lower()):
        if not sub.is_dir():
            continue
        skill_md = sub / "SKILL.md"
        if skill_md.is_file():
            entries.append({
                "name": sub.name,
                "tier": tier,
                "path": str(skill_md.resolve()),
            })
    return entries


def discover_skill_catalog(project_root: Path, project_slug: str) -> Dict[str, List[Dict[str, str]]]:
    """Discover available PROJECT, UNIVERSAL, and BUILTIN SKILL.md paths on disk."""
    is_brain = project_root.resolve() == BRAIN_ROOT.resolve() or project_slug.lower() == "brain"
    if is_brain:
        project_entries: List[Dict[str, str]] = []
    else:
        project_entries = _collect_skill_entries(project_root / ".agents" / "skills", "PROJECT")
        # Include archived project skills in brain if not already present locally
        seen_proj = {e["name"].lower() for e in project_entries}
        for arch in _collect_skill_entries(BRAIN_ROOT / "project_skills" / project_slug, "PROJECT_ARCHIVE"):
            if arch["name"].lower() not in seen_proj:
                project_entries.append(arch)
                seen_proj.add(arch["name"].lower())

    universal_entries = _collect_skill_entries(BRAIN_UNIVERSAL_SKILLS_DIR, "UNIVERSAL")
    universal_names = {e["name"].lower() for e in universal_entries}

    # Builtin dir may mirror universal skills; surface unique built-ins cleanly
    builtin_entries = [
        e for e in _collect_skill_entries(BUILTIN_SKILLS_DIR, "BUILTIN")
        if e["name"].lower() not in universal_names
    ]
    config_entries = _collect_skill_entries(CONFIG_SKILLS_DIR, "GLOBAL_CONFIG")
    return {
        "project": project_entries,
        "universal": universal_entries,
        "builtin": builtin_entries,
        "config": config_entries,
    }


def resolve_skill_paths(
    skill_names: List[str],
    project_root: Path,
    project_slug: str,
    explicit_paths: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    """
    Resolve skill names and explicit SKILL.md file paths into tagged absolute paths.
    Always embeds `auto-skill/SKILL.md` first so the CLI worker can auto-route without slash commands.
    """
    resolved: List[Dict[str, str]] = []
    seen_keys: set[str] = set()

    # Load skill registry descriptions if available
    descriptions: Dict[str, str] = {}
    if SKILL_REGISTRY_JSON.is_file():
        try:
            for item in json.loads(SKILL_REGISTRY_JSON.read_text(encoding="utf-8")):
                if isinstance(item, dict) and item.get("name"):
                    descriptions[item["name"].lower()] = item.get("description", "")
        except Exception:
            pass

    plugins_root = USER_HOME / ".gemini" / "config" / "plugins"

    def _find_skill_md(req: str) -> Tuple[Optional[Path], str]:
        cleaned = req.strip().strip("\"'")
        # Allow passing explicit filesystem path directly
        if cleaned.lower().endswith(".md") or "\\" in cleaned or "/" in cleaned:
            p = _to_host_path(cleaned)
            if p.is_dir():
                p = p / "SKILL.md"
            if p.is_file():
                resolved_p = p.resolve()
                if _is_within_or_equal(resolved_p, BUILTIN_SKILLS_DIR):
                    tier = "BUILTIN"
                elif _is_within_or_equal(resolved_p, BRAIN_UNIVERSAL_SKILLS_DIR):
                    tier = "UNIVERSAL"
                elif _is_within_or_equal(resolved_p, project_root):
                    tier = "PROJECT"
                else:
                    tier = "EXPLICIT"
                return resolved_p, tier

        canonical = SKILL_ALIASES.get(cleaned.lower(), cleaned)
        candidates: List[Tuple[Path, str]] = [
            (project_root / ".agents" / "skills" / canonical / "SKILL.md", "PROJECT"),
            (project_root / ".agents" / "skills" / cleaned / "SKILL.md", "PROJECT"),
            (BRAIN_UNIVERSAL_SKILLS_DIR / canonical / "SKILL.md", "UNIVERSAL"),
            (BRAIN_UNIVERSAL_SKILLS_DIR / cleaned / "SKILL.md", "UNIVERSAL"),
            (BRAIN_ROOT / "project_skills" / project_slug / canonical / "SKILL.md", "PROJECT_ARCHIVE"),
            (BRAIN_ROOT / "project_skills" / project_slug / cleaned / "SKILL.md", "PROJECT_ARCHIVE"),
            (BUILTIN_SKILLS_DIR / canonical / "SKILL.md", "BUILTIN"),
            (BUILTIN_SKILLS_DIR / cleaned / "SKILL.md", "BUILTIN"),
            (CONFIG_SKILLS_DIR / canonical / "SKILL.md", "GLOBAL_CONFIG"),
            (CONFIG_SKILLS_DIR / cleaned / "SKILL.md", "GLOBAL_CONFIG"),
        ]
        if plugins_root.is_dir():
            for name_try in (canonical, cleaned):
                for p_match in plugins_root.glob(f"*/skills/{name_try}/SKILL.md"):
                    candidates.append((p_match, "PLUGIN"))

        for cand, tier in candidates:
            if cand.is_file():
                return cand.resolve(), tier
        return None, "UNRESOLVED"

    # Always force auto-skill first
    combined_requests = ["auto-skill"] + [s.strip().lstrip("/") for s in skill_names if s.strip()]
    for ep in (explicit_paths or []):
        if ep.strip():
            combined_requests.append(ep.strip())

    for req in combined_requests:
        skill_md, tier = _find_skill_md(req)
        dedupe_key = str(skill_md).lower() if skill_md else SKILL_ALIASES.get(req.lower(), req.lower())
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        skill_name = skill_md.parent.name if skill_md else req
        desc = descriptions.get(
            skill_name.lower(),
            descriptions.get(req.lower(), "Consult SKILL.md directly for instructions."),
        )
        resolved.append({
            "requested": req,
            "name": skill_name,
            "tier": tier,
            "path": str(skill_md) if skill_md else f"NOT_FOUND (search via select_skill.py '{req}')",
            "description": desc,
        })

    return resolved


def _default_status(project_slug: str, project_root: Path) -> Dict[str, Any]:
    return {
        "schema_version": 3,
        "project_name": project_slug,
        "project_root": _to_display_path(project_root),
        "updated_at": _now_iso(),
        "agents": {},
        "orchestrator": {
            "state": "IDLE",
            "last_seen_epoch": 0.0,
            "last_seen_iso": "never",
            "active_expectation": "NONE",
            "note": "No recent orchestrator ping",
        },
        "worker": {
            "state": "OFFLINE",
            "last_heartbeat_epoch": 0.0,
            "last_heartbeat_iso": "never",
            "pid": None,
            "active_task_id": None,
            "delegated_tasks": [],
            "note": "Waiting for Antigravity CLI worker to run worker-listen",
        },
    }


def normalize_agent_role(role: Optional[str]) -> str:
    """Normalize role aliases into canonical Offload V3 roles: main | worker | collaborator."""
    raw = str(role or "worker").strip().lower()
    if raw in ("main", "orchestrator", "orch", "primary"):
        return "main"
    if raw in ("collaborator", "collab", "peer"):
        return "collaborator"
    return "worker"


def sanitize_agent_id(agent_id: str) -> str:
    """Sanitize agent IDs to lowercase [a-z0-9_-]."""
    return re.sub(r"[^a-z0-9_-]+", "-", str(agent_id).strip().lower()).strip("-")


def _infer_role_from_agent_id(agent_id: str, default: str = "worker") -> str:
    low = sanitize_agent_id(agent_id)
    if low.startswith("main") or low.startswith("orch"):
        return "main"
    if low.startswith("collab") or low.startswith("peer"):
        return "collaborator"
    if low.startswith("worker"):
        return "worker"
    return normalize_agent_role(default)


def _normalize_target(target: Optional[str], default: str = "any") -> str:
    """Normalize task/message target ('any', 'all', 'role:<role>', or sanitized agent_id)."""
    raw = str(target or "").strip()
    if not raw:
        return default
    low = raw.lower()
    if low in ("any", "all", "*"):
        return low if low in ("any", "all") else default
    if low.startswith("role:"):
        req_role = normalize_agent_role(low[5:])
        return f"role:{req_role}"
    sanitized = sanitize_agent_id(raw)
    return sanitized or default


def _target_matches(target: Optional[str], agent_id: Optional[str], role: Optional[str] = None) -> bool:
    """Check whether a task or message target matches a given agent_id and role."""
    norm_target = _normalize_target(target, default="any")
    if norm_target in ("any", "all", "*"):
        return True
    norm_id = sanitize_agent_id(agent_id) if agent_id else ""
    if norm_target.startswith("role:"):
        req_role = normalize_agent_role(norm_target[5:])
        eff_role = normalize_agent_role(role) if role else (_infer_role_from_agent_id(norm_id) if norm_id else "")
        return bool(eff_role) and eff_role == req_role
    return bool(norm_id) and norm_id == norm_target


def _is_agent_entry_live(entry: Dict[str, Any], now: Optional[float] = None) -> bool:
    """Return True if an agent roster entry is currently live (not OFFLINE and within role/state TTL)."""
    ts = now if now is not None else _now_epoch()
    state = str(entry.get("state", "OFFLINE")).upper()
    if state == "OFFLINE":
        return False
    last_ep = float(entry.get("last_seen_epoch") or 0.0)
    if last_ep <= 0:
        return False
    age = max(0.0, ts - last_ep)
    role = normalize_agent_role(entry.get("role"))
    if state == "BUSY_EXECUTING":
        return age <= WORKER_BUSY_TTL_SEC
    if state == "ONLINE_LISTENING":
        return age <= WORKER_LISTEN_TTL_SEC
    if role == "main":
        return age <= MAIN_STALE_TTL_SEC
    return age <= MAIN_STALE_TTL_SEC


def _format_agent_badge(entry: Dict[str, Any], now: Optional[float] = None) -> Tuple[str, str, str]:
    """Compute (badge, short_label, age_str) for a single roster agent."""
    ts = now if now is not None else _now_epoch()
    state = str(entry.get("state", "OFFLINE")).upper()
    last_ep = float(entry.get("last_seen_epoch") or 0.0)
    age = (ts - last_ep) if last_ep > 0 else None
    age_str = _format_age(age)
    role = normalize_agent_role(entry.get("role"))
    tasks = entry.get("current_tasks") or []
    task_tag = f" [{tasks[0]}]" if tasks else ""

    if last_ep <= 0 or state == "OFFLINE":
        return ("🔴 OFFLINE", "OFFLINE", age_str)
    if state == "BUSY_EXECUTING":
        if age is not None and age <= WORKER_BUSY_TTL_SEC:
            return ("⚡ BUSY_EXECUTING", f"BUSY{task_tag} ({age_str})", age_str)
        return ("🟠 STALLED_BUSY", f"STALLED ({age_str})", age_str)
    if state == "ONLINE_LISTENING":
        if age is not None and age <= WORKER_LISTEN_TTL_SEC:
            return ("🟢 ONLINE_LISTENING", f"LISTENING ({age_str})", age_str)
        return ("🔴 OFFLINE_STALE", f"STALE ({age_str})", age_str)
    ttl = MAIN_STALE_TTL_SEC
    if age is not None and age <= ttl:
        if state == "WAITING_FOR_RESULT":
            return ("🟡 WAITING_FOR_RESULT", f"WAITING ({age_str})", age_str)
        if state == "IDLE":
            return ("⚪ IDLE", f"IDLE ({age_str})", age_str)
        return ("🟢 ONLINE", f"ONLINE ({age_str})", age_str)
    if role == "main":
        return ("⚪ IDLE_STALE", f"IDLE ({age_str})", age_str)
    return ("🔴 OFFLINE_STALE", f"STALE ({age_str})", age_str)


def allocate_agent_id(
    status: Dict[str, Any],
    role: str,
    requested_id: Optional[str] = None,
    pid: Optional[int] = None,
    now: Optional[float] = None,
) -> str:
    """
    Allocate or reuse a roster agent ID safely.
    - Prefix map: main -> main, worker -> worker, collaborator -> collab.
    - Uses sanitized `requested_id` if provided.
    - If omitted, reuses an existing entry matching `(role, pid)` if `pid` is provided.
    - Otherwise reuses the lowest stale/offline sequential slot of the same role, or allocates
      the next sequential slot (`worker-1`, `worker-2`, `collab-1`, `main-1`, ...).
    """
    norm_role = normalize_agent_role(role)
    prefix = AGENT_ROLE_PREFIXES[norm_role]
    if requested_id and str(requested_id).strip():
        cleaned = sanitize_agent_id(str(requested_id))
        if cleaned:
            return cleaned

    agents = status.get("agents")
    if not isinstance(agents, dict):
        agents = {}
    ts = now if now is not None else _now_epoch()

    if pid is not None:
        for existing_id, entry in sorted(agents.items()):
            if not isinstance(entry, dict):
                continue
            if normalize_agent_role(entry.get("role")) == norm_role and entry.get("pid") == pid:
                return existing_id

    idx = 1
    while True:
        candidate = f"{prefix}-{idx}"
        existing = agents.get(candidate)
        if existing is None:
            return candidate
        if isinstance(existing, dict):
            existing_role = normalize_agent_role(existing.get("role"))
            if existing_role == norm_role and not _is_agent_entry_live(existing, now=ts):
                return candidate
        idx += 1


def _upsert_agent_entry(
    status: Dict[str, Any],
    agent_id: str,
    role: str,
    state: str,
    host: Optional[str] = None,
    pid: Any = "__KEEP__",
    note: Optional[str] = None,
    add_task: Optional[str] = None,
    remove_task: Optional[str] = None,
    now_ep: Optional[float] = None,
    now_str: Optional[str] = None,
) -> Dict[str, Any]:
    """Create or update a single agent's entry inside `status['agents']` without clobbering peers."""
    agents = status.setdefault("agents", {})
    norm_id = sanitize_agent_id(agent_id) or agent_id
    norm_role = normalize_agent_role(role)
    ep = now_ep if now_ep is not None else _now_epoch()
    iso = now_str if now_str is not None else _now_iso()

    existing = agents.get(norm_id)
    if not isinstance(existing, dict):
        existing = {
            "agent_id": norm_id,
            "role": norm_role,
            "host": host or "cli",
            "pid": None,
            "state": state,
            "last_seen": iso,
            "last_seen_epoch": ep,
            "current_tasks": [],
            "note": "",
        }
        agents[norm_id] = existing

    existing["agent_id"] = norm_id
    existing["role"] = norm_role
    if host is not None and str(host).strip():
        existing["host"] = str(host).strip()
    elif not existing.get("host"):
        existing["host"] = "antigravity" if norm_role == "main" else "cli"

    if pid != "__KEEP__":
        existing["pid"] = pid
    elif state == "OFFLINE":
        existing["pid"] = None

    existing["state"] = state
    existing["last_seen"] = iso
    existing["last_seen_epoch"] = ep

    cur_tasks = list(existing.get("current_tasks") or [])
    if add_task and add_task not in cur_tasks:
        cur_tasks.append(add_task)
    if remove_task and remove_task in cur_tasks:
        cur_tasks = [t for t in cur_tasks if t != remove_task]
    existing["current_tasks"] = cur_tasks

    if note is not None:
        existing["note"] = note
    return existing


def _sync_legacy_mirrors(status: Dict[str, Any], now: Optional[float] = None) -> None:
    """Keep legacy top-level `orchestrator` and `worker` mirrors synchronized with `agents`."""
    ts = now if now is not None else _now_epoch()
    agents = status.get("agents")
    if not isinstance(agents, dict) or not agents:
        return

    mains = [
        e for e in agents.values()
        if isinstance(e, dict) and normalize_agent_role(e.get("role")) == "main"
    ]
    if mains:
        mains.sort(
            key=lambda e: (
                1 if _is_agent_entry_live(e, now=ts) else 0,
                1 if str(e.get("state", "")).upper() == "WAITING_FOR_RESULT" else 0,
                float(e.get("last_seen_epoch") or 0.0),
            ),
            reverse=True,
        )
        top_main = mains[0]
        orch = status.setdefault("orchestrator", {})
        orch["state"] = top_main.get("state", "IDLE")
        orch["last_seen_epoch"] = float(top_main.get("last_seen_epoch") or 0.0)
        orch["last_seen_iso"] = top_main.get("last_seen", "never")
        if top_main.get("note"):
            orch["note"] = top_main["note"]
        orch.setdefault("active_expectation", "NONE")

    workers = [
        e for e in agents.values()
        if isinstance(e, dict) and normalize_agent_role(e.get("role")) in ("worker", "collaborator")
    ]
    if workers:
        live_workers = [w for w in workers if _is_agent_entry_live(w, now=ts)]
        worker_mirror = status.setdefault("worker", {})
        worker_mirror.setdefault("delegated_tasks", [])
        if live_workers:
            def _worker_rank(e: Dict[str, Any]) -> Tuple[int, int, float]:
                st = str(e.get("state", "")).upper()
                st_prio = 3 if st == "ONLINE_LISTENING" else (2 if st == "BUSY_EXECUTING" else 1)
                role_prio = 1 if normalize_agent_role(e.get("role")) == "worker" else 0
                return (st_prio, role_prio, float(e.get("last_seen_epoch") or 0.0))

            live_workers.sort(key=_worker_rank, reverse=True)
            best = live_workers[0]
            cur_tasks = best.get("current_tasks") or []
            worker_mirror["state"] = best.get("state", "ONLINE_LISTENING")
            worker_mirror["last_heartbeat_epoch"] = float(best.get("last_seen_epoch") or 0.0)
            worker_mirror["last_heartbeat_iso"] = best.get("last_seen", "never")
            worker_mirror["pid"] = best.get("pid")
            worker_mirror["active_task_id"] = cur_tasks[0] if cur_tasks else None
            worker_mirror["note"] = best.get("note", "")
        else:
            workers.sort(key=lambda e: float(e.get("last_seen_epoch") or 0.0), reverse=True)
            latest = workers[0]
            worker_mirror["state"] = "OFFLINE"
            worker_mirror["last_heartbeat_epoch"] = float(latest.get("last_seen_epoch") or 0.0)
            worker_mirror["last_heartbeat_iso"] = latest.get("last_seen", "never")
            worker_mirror["pid"] = None
            worker_mirror["active_task_id"] = None
            worker_mirror["note"] = latest.get("note", "All workers offline")


def _compute_effective_presence(status: Dict[str, Any], now: Optional[float] = None) -> Dict[str, Any]:
    """Compute live display badges and staleness for Orchestrator, CLI Worker, and V3 Multi-Agent Roster."""
    ts = now if now is not None else _now_epoch()
    orch = status.get("orchestrator", {})
    worker = status.get("worker", {})

    # Orchestrator effective presence
    orch_raw_state = str(orch.get("state", "IDLE")).upper()
    orch_epoch = float(orch.get("last_seen_epoch") or 0.0)
    orch_age = (ts - orch_epoch) if orch_epoch > 0 else None
    if orch_epoch <= 0:
        orch_badge = "⚪ NOT_CONNECTED"
        orch_short = "IDLE (never)"
    elif orch_age is not None and orch_age <= ORCHESTRATOR_TTL_SEC:
        if orch_raw_state == "WAITING_FOR_RESULT":
            orch_badge = "🟡 WAITING_FOR_RESULT"
        else:
            orch_badge = "🟢 ONLINE"
        orch_short = f"{orch_raw_state} ({_format_age(orch_age)})"
    else:
        orch_badge = "⚪ IDLE_STALE"
        orch_short = f"IDLE ({_format_age(orch_age)})"

    # Worker effective presence
    w_raw_state = str(worker.get("state", "OFFLINE")).upper()
    w_epoch = float(worker.get("last_heartbeat_epoch") or 0.0)
    w_age = (ts - w_epoch) if w_epoch > 0 else None
    active_task = worker.get("active_task_id")
    delegated_tasks = worker.get("delegated_tasks") or []
    bg_suffix = f" [bg:{len(delegated_tasks)}]" if delegated_tasks else ""

    if w_epoch <= 0 or w_raw_state == "OFFLINE":
        w_badge = "🔴 OFFLINE"
        w_short = "OFFLINE"
    elif w_raw_state == "BUSY_EXECUTING":
        if w_age is not None and w_age <= WORKER_BUSY_TTL_SEC:
            w_badge = "⚡ BUSY_EXECUTING"
            w_short = f"BUSY [{active_task or '?'}]{bg_suffix} ({_format_age(w_age)})"
        else:
            w_badge = "🟠 STALLED_BUSY"
            w_short = f"STALLED ({_format_age(w_age)})"
    elif w_raw_state == "ONLINE_LISTENING":
        if w_age is not None and w_age <= WORKER_LISTEN_TTL_SEC:
            w_badge = f"🟢 ONLINE_LISTENING{bg_suffix}"
            w_short = f"LISTENING{bg_suffix} ({_format_age(w_age)})"
        else:
            w_badge = "🔴 OFFLINE_STALE"
            w_short = f"STALE ({_format_age(w_age)})"
    elif w_age is not None and w_age <= MAIN_STALE_TTL_SEC:
        w_badge = f"🟢 {w_raw_state}{bg_suffix}"
        w_short = f"{w_raw_state}{bg_suffix} ({_format_age(w_age)})"
    else:
        w_badge = "🔴 OFFLINE_STALE"
        w_short = f"STALE ({_format_age(w_age)})"

    agents_dict = status.get("agents") if isinstance(status.get("agents"), dict) else {}
    live_main = 0
    live_collab = 0
    live_worker = 0
    for entry in agents_dict.values():
        if not isinstance(entry, dict):
            continue
        if _is_agent_entry_live(entry, now=ts):
            r = normalize_agent_role(entry.get("role"))
            if r == "main":
                live_main += 1
            elif r == "collaborator":
                live_collab += 1
            else:
                live_worker += 1

    legacy_worker_live = (
        (w_raw_state == "BUSY_EXECUTING" and w_age is not None and w_age <= WORKER_BUSY_TTL_SEC)
        or (w_raw_state == "ONLINE_LISTENING" and w_age is not None and w_age <= WORKER_LISTEN_TTL_SEC)
        or (w_raw_state == "ONLINE" and w_age is not None and w_age <= MAIN_STALE_TTL_SEC)
    )

    return {
        "orchestrator_badge": orch_badge,
        "orchestrator_short": orch_short,
        "orchestrator_age_str": _format_age(orch_age),
        "orchestrator_is_live": (orch_age is not None and orch_age <= ORCHESTRATOR_TTL_SEC) or live_main > 0,
        "worker_badge": w_badge,
        "worker_short": w_short,
        "worker_age_str": _format_age(w_age),
        "delegated_count": len(delegated_tasks),
        "worker_is_live": legacy_worker_live or (live_worker + live_collab) > 0,
        "live_main_count": live_main,
        "live_collab_count": live_collab,
        "live_worker_count": live_worker,
        "total_agents_count": len(agents_dict),
    }


def _load_tasks(offload_dir: Path) -> List[Dict[str, Any]]:
    tasks_dir = offload_dir / "tasks"
    tasks: List[Dict[str, Any]] = []
    if not tasks_dir.is_dir():
        return tasks
    for jf in sorted(tasks_dir.glob("TASK-*.json"), reverse=True):
        data = safe_read_json(jf)
        if data and data.get("task_id"):
            data["_json_path"] = str(jf)
            tasks.append(data)
    return tasks


def _load_pending_questions(offload_dir: Path) -> List[Dict[str, Any]]:
    comms_dir = offload_dir / "comms"
    questions: List[Dict[str, Any]] = []
    if not comms_dir.is_dir():
        return questions
    for qf in sorted(comms_dir.glob("*.json")):
        data = safe_read_json(qf)
        if data and data.get("status") == "PENDING_ANSWER":
            questions.append(data)
    return questions


def _load_messages(offload_dir: Path) -> List[Dict[str, Any]]:
    """Read peer collaboration messages from `<offload_dir>/messages.jsonl`."""
    msg_path = offload_dir / "messages.jsonl"
    if not msg_path.is_file():
        return []
    messages: List[Dict[str, Any]] = []
    for attempt in range(4):
        try:
            raw_lines = msg_path.read_text(encoding="utf-8", errors="replace").splitlines()
            for line in raw_lines:
                line_s = line.strip()
                if not line_s:
                    continue
                try:
                    item = json.loads(line_s)
                    if isinstance(item, dict):
                        messages.append(item)
                except json.JSONDecodeError:
                    continue
            return messages
        except (PermissionError, OSError):
            time.sleep(0.02 * (attempt + 1))
    return messages


def post_message(
    offload_dir: Path,
    project_slug: str,
    project_root: Path,
    from_agent: str,
    to_target: str,
    message: str,
    file_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Atomically append a peer message to `messages.jsonl` and refresh BOARD.md."""
    sender = sanitize_agent_id(from_agent) or "main-1"
    target = _normalize_target(to_target, default="all")
    now_str = _now_iso()
    msg_obj: Dict[str, Any] = {
        "id": f"MSG-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}",
        "ts": now_str,
        "from": sender,
        "to": target,
        "message": message.strip(),
        "file": _to_display_path(file_path) if file_path else None,
    }
    msg_path = offload_dir / "messages.jsonl"
    with offload_lock(offload_dir):
        msg_path.parent.mkdir(parents=True, exist_ok=True)
        _assert_offload_lock_owned()
        with open(msg_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(msg_obj, ensure_ascii=False) + "\n")
            fh.flush()

        status = _load_status(offload_dir, project_slug, project_root)
        agents = status.get("agents") or {}
        if sender in agents and isinstance(agents[sender], dict):
            agents[sender]["last_seen"] = now_str
            agents[sender]["last_seen_epoch"] = _now_epoch()
            status["updated_at"] = now_str
            _save_status(offload_dir, status)
        atomic_write_text(offload_dir / "BOARD.md", render_board_markdown(project_slug, project_root, offload_dir))
    return msg_obj


def query_inbox(
    offload_dir: Path,
    for_agent: Optional[str] = None,
    role: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Return recent peer messages filtered for `for_agent` / `role` (or all if omitted)."""
    messages = _load_messages(offload_dir)
    if not for_agent and not role:
        return messages[-max(1, limit):] if limit > 0 else messages

    eff_id = sanitize_agent_id(for_agent) if for_agent else None
    eff_role = normalize_agent_role(role) if role else None
    if eff_id and not eff_role:
        status = safe_read_json(offload_dir / "status.json", {})
        agents = status.get("agents") if isinstance(status.get("agents"), dict) else {}
        if eff_id in agents and isinstance(agents[eff_id], dict) and agents[eff_id].get("role"):
            eff_role = normalize_agent_role(agents[eff_id]["role"])
        else:
            eff_role = _infer_role_from_agent_id(eff_id)

    matched = [m for m in messages if _target_matches(m.get("to", "all"), eff_id, eff_role)]
    return matched[-max(1, limit):] if limit > 0 else matched


def _sorted_roster_entries(status: Dict[str, Any], now: Optional[float] = None) -> List[Dict[str, Any]]:
    """Return roster entries sorted cleanly by role group (main -> collaborator -> worker), then ID."""
    agents = status.get("agents")
    if not isinstance(agents, dict):
        return []
    role_order = {"main": 0, "collaborator": 1, "worker": 2}
    entries = [e for e in agents.values() if isinstance(e, dict)]

    def _sort_key(e: Dict[str, Any]) -> Tuple[int, str]:
        r = normalize_agent_role(e.get("role"))
        aid = str(e.get("agent_id") or "")
        return (role_order.get(r, 9), aid)

    entries.sort(key=_sort_key)
    return entries


def render_board_markdown(project_slug: str, project_root: Path, offload_dir: Path) -> str:
    """Render the live BOARD.md with Multi-Agent Roster, Status Bar, active tasks, and peer messages."""
    now_ep = _now_epoch()
    status = _load_status(offload_dir, project_slug, project_root)
    presence = _compute_effective_presence(status, now=now_ep)
    orch = status.get("orchestrator", {})
    worker = status.get("worker", {})

    tasks = _load_tasks(offload_dir)
    pending = [t for t in tasks if t.get("status") == "PENDING"]
    in_progress = [t for t in tasks if t.get("status") == "IN_PROGRESS"]
    done = [t for t in tasks if t.get("status") in ("COMPLETED", "FAILED", "CANCELLED")]
    pending_questions = _load_pending_questions(offload_dir)
    recent_msgs = _load_messages(offload_dir)[-5:]

    q_suffix = f" | Questions: {len(pending_questions)}" if pending_questions else ""
    roster_strip = (
        f"[MAIN: {presence['live_main_count']} | COLLAB: {presence['live_collab_count']} | "
        f"WORKERS: {presence['live_worker_count']}] "
        f"[ORCH: {presence['orchestrator_short']}] <====> [WORKER: {presence['worker_short']}] | "
        f"Pending: {len(pending)} | In Progress: {len(in_progress)} | Completed: {len(done)}{q_suffix}"
    )

    disp_root = _to_display_path(project_root)
    disp_offload = _to_display_path(offload_dir)

    lines = [
        f"# OFFLOAD MESSAGE BOARD — `{project_slug}`",
        "",
        f"> **Target Project Root**: `{disp_root}`  ",
        f"> **Board Directory**: `{disp_offload}`  ",
        f"> **Worker Bootstrap Instructions**: Read [`INSTRUCTIONS.md`](./INSTRUCTIONS.md) | **Last Render**: `{_now_iso()}`",
        "",
        "## LIVE TWO-WAY STATUS BAR",
        "",
        "```text",
        roster_strip,
        "```",
        "",
        "## MULTI-AGENT ROSTER",
        "",
    ]

    roster = _sorted_roster_entries(status, now=now_ep)
    if roster:
        lines.extend([
            "| Agent ID | Role | Host | PID | Status | Last Seen | Active Tasks | Note |",
            "|---|---|---|---|---|---|---|---|",
        ])
        for entry in roster:
            badge, _, age_str = _format_agent_badge(entry, now=now_ep)
            aid = entry.get("agent_id", "?")
            role = normalize_agent_role(entry.get("role"))
            host = entry.get("host") or "—"
            pid_str = str(entry.get("pid")) if entry.get("pid") else "—"
            cur_tasks = entry.get("current_tasks") or []
            tasks_str = ", ".join(f"`{t}`" for t in cur_tasks) if cur_tasks else "IDLE"
            note = str(entry.get("note") or "").replace("|", "/").replace("\n", " ")
            lines.append(
                f"| **`{aid}`** | `{role}` | `{host}` | `{pid_str}` | `{badge}` | `{age_str}` | {tasks_str} | {note} |"
            )
    else:
        lines.extend([
            "| Endpoint | Status | Details / PID | Last Heartbeat / Seen | Active Work / Expectation |",
            "|---|---|---|---|---|",
            (
                f"| **Primary Orchestrator** | `{presence['orchestrator_badge']}` | "
                f"{orch.get('note', 'Ready')} | `{presence['orchestrator_age_str']}` | "
                f"`{orch.get('active_expectation', 'NONE')}` |"
            ),
            (
                f"| **Secondary CLI Worker** | `{presence['worker_badge']}` | "
                f"PID `{worker.get('pid') or '—'}` ({worker.get('note', '')}) | "
                f"`{presence['worker_age_str']}` | `{worker.get('active_task_id') or 'IDLE'}` |"
            ),
        ])

    lines.extend(["", "---", ""])
    if pending_questions:
        lines.extend(["## 🟡 Pending Orchestrator Questions (Action Required)", ""])
        for q in pending_questions:
            lines.append(
                f"- **`{q.get('task_id')}`** (from `{q.get('sender', 'subagent')}` at `{q.get('asked_at', '')}`): {q.get('question', '')}"
            )
        lines.extend(["", "---", ""])

    lines.extend(["## Pending & Active Task Queue", ""])
    active_list = in_progress + pending
    if not active_list:
        lines.append("_Queue empty. Waiting for Main/Collaborator agents to dispatch tasks via `/offload`._")
    else:
        lines.extend([
            "| Task ID | Status | Target | From / Owner | Mode | Title | Injected Skills | Created |",
            "|---|---|---|---|---|---|---|---|",
        ])
        for t in active_list:
            skills_str = ", ".join(f"`{s.get('name', '?')}`" for s in t.get("skills", []))
            tid = t["task_id"]
            tgt = t.get("target_agent", "any")
            frm = t.get("from_agent", "main-1")
            claimed_by = t.get("claimed_by")
            owner_str = f"`{frm}` -> `{claimed_by}`" if claimed_by else f"`{frm}`"
            lines.append(
                f"| [`{tid}`](./tasks/{tid}.md) | `{t.get('status')}` | `to={tgt}` | {owner_str} | "
                f"`{t.get('mode', 'standard')}` | {t.get('title', 'Untitled')} | {skills_str} | `{t.get('created_at', '')}` |"
            )

    if recent_msgs:
        lines.extend(["", "## Recent Peer Messages (Last 5)", ""])
        lines.extend([
            "| Time | From | To | Message | File |",
            "|---|---|---|---|---|",
        ])
        for m in recent_msgs:
            msg_text = str(m.get("message", "")).replace("|", "/").replace("\n", " ")
            f_str = f"`{m['file']}`" if m.get("file") else "—"
            lines.append(
                f"| `{m.get('ts', '')}` | `{m.get('from', '?')}` | `{m.get('to', 'all')}` | {msg_text} | {f_str} |"
            )

    lines.extend(["", "## Recent Completed / Closed Tasks", ""])
    if not done:
        lines.append("_No completed offloaded tasks recorded yet._")
    else:
        lines.extend([
            "| Task ID | Final Status | Owner | Title | Result Dossier | Completed At |",
            "|---|---|---|---|---|---|",
        ])
        for t in done[:15]:
            tid = t["task_id"]
            res_rel = f"./results/RESULT-{tid}.md"
            owner = t.get("claimed_by") or "worker"
            lines.append(
                f"| [`{tid}`](./tasks/{tid}.md) | `{t.get('status')}` | `{owner}` | "
                f"{t.get('title', 'Untitled')} | [`RESULT-{tid}.md`]({res_rel}) | `{t.get('completed_at', '—')}` |"
            )

    lines.append("")
    return "\n".join(lines)


def _generate_worker_instructions(project_slug: str, project_root: Path) -> str:
    """Generate the self-contained Offload V3 INSTRUCTIONS.md read by any joining worker, collaborator, or main agent."""
    proj_root_str = _to_display_path(project_root)
    auto_skill_path = _to_display_path(AUTO_SKILL_MD)
    select_skill_path = _to_display_path(SELECT_SKILL_PY)
    manager_path = _to_display_path(Path(__file__).resolve())

    is_brain_target = project_root.resolve() == BRAIN_ROOT.resolve() or project_slug.lower() == "brain"
    brain_warning = (
        "> [!WARNING] CO-FOLDER TRAP CHECK:\n"
        "> This message board is strictly for **Central Brain (`brain`) itself**!\n"
        "> If you are working on a project workspace (e.g. `flh-one`, `hi`, `AWAKEN1`, `mineserver`, etc.) with `brain/` co-attached,\n"
        "> do **NOT** listen or complete tasks on this board! Open `<project>/offload/INSTRUCTIONS.md` and listen on `<project>/offload/` instead.\n\n"
        if is_brain_target
        else ""
    )
    scope_note = (
        "This board is for **Central Brain (`brain`) itself**."
        if is_brain_target
        else (
            f"This board is strictly scoped to project **`{project_slug}`** (`{proj_root_str}`).\n"
            f"- Note: Even though `brain/` may be attached as a co-folder, all tasks here belong to `{project_slug}`, "
            f"and deliverables/temp scripts MUST go strictly to `{proj_root_str}\\temp_read\\`."
        )
    )
    context_file_list = (
        f"   - `{proj_root_str}\\project_map.md` and `{proj_root_str}\\file_map.md`\n"
        f"   - `{proj_root_str}\\constraints.md`\n"
        f"   - `{proj_root_str}\\mistakes.md`"
        if is_brain_target
        else (
            f"   - `{proj_root_str}\\file_map.md` (or `context\\file_map.md`)\n"
            f"   - `{proj_root_str}\\context\\constraints.md`\n"
            f"   - `{proj_root_str}\\context\\mistakes.md`"
        )
    )

    catalog = discover_skill_catalog(project_root, project_slug)
    proj_skill_lines = "\n".join(
        f"  - `{s['name']}`: `{_to_display_path(s['path'])}`" for s in catalog["project"]
    ) or "  - _(none registered in this project root yet; use Universal/Builtin paths below)_"
    univ_skill_lines = "\n".join(
        f"  - `{s['name']}`: `{_to_display_path(s['path'])}`" for s in catalog["universal"]
    )
    builtin_skill_lines = "\n".join(
        f"  - `{s['name']}`: `{_to_display_path(s['path'])}`" for s in catalog["builtin"]
    )

    return f"""# OFFLOAD V3 MULTI-AGENT BOARD INSTRUCTIONS — `{project_slug}`

{brain_warning}> **Read This First!** Offload V3 supports **Multi-Agent Rosters & Collaboration Meshes**:
> `1 main + N workers` (`main-1`, `worker-1`, `worker-2`, ...), **peer collaborators** (`collab-1`, `collab-2`, ...), and **mixed topologies** (e.g., Antigravity IDE + Codex + multiple AGY CLI workers).

## 1. Scope & Workspace Identity
{scope_note}

- **Offload Manager Script**: `{manager_path}`
- **Mandatory Auto-Skill Router**: `{auto_skill_path}`
- **Dynamic Skill Lookup CLI**: `python "{select_skill_path}" "<domain>" --project {project_slug}`
- **List All Project / Universal / Built-in `SKILL.md` Paths**: `python "{manager_path}" skills --project "{proj_root_str}"`
- **WSL / POSIX Path Note**: Windows paths (`C:\\...`) map directly to `/mnt/c/...` in WSL.
- If Windows-only dependencies or native scripts are needed, use `/mnt/c/Python314/python.exe`.

## 2. One-Line Join Commands (Auto-Assigned Roster IDs)

Do **NOT** poll `BOARD.md` in an LLM loop (that wastes tokens). Join directly with your role; IDs (`worker-1`, `worker-2`, `collab-1`, `main-1`) are auto-allocated atomically without colliding with live peers:

```powershell
# Join & listen as a Worker (auto-assigns worker-1, worker-2, ...)
python "{manager_path}" worker-listen --project "{proj_root_str}" --role worker --host cli

# Join & listen as a Collaborator peer (auto-assigns collab-1, collab-2, ...)
python "{manager_path}" worker-listen --project "{proj_root_str}" --role collaborator --host codex

# Register as a Main / Orchestrator agent (auto-assigns main-1, main-2, ...)
python "{manager_path}" join --project "{proj_root_str}" --role main --host antigravity
```

- Pass `--agent-id <custom_id>` only if you need a pinned ID; omit it for collision-free sequential auto-IDs.
- In Antigravity, pass `WaitMsBeforeAsync=10000` when launching `worker-listen` with `run_command` (reactive wakeup). In Codex, keep the turn active and wait on the shell session.
- To sign off cleanly: `python "{manager_path}" leave --project "{proj_root_str}" --agent-id "<AGENT_ID>"`

## 3. Targeted Dispatch & Peer Collaboration Mesh (`--to`, `post`, `inbox`)

- **Targeted Dispatch** (route work to everyone, a specific agent, or a role pool):
  ```powershell
  python "{manager_path}" dispatch --project "{proj_root_str}" --title "<title>" --prompt-file "<prompt.md>" --from main-1 --to any
  python "{manager_path}" dispatch --project "{proj_root_str}" --title "<title>" --prompt-file "<prompt.md>" --from main-1 --to worker-2
  python "{manager_path}" dispatch --project "{proj_root_str}" --title "<title>" --prompt-file "<prompt.md>" --from main-1 --to role:collaborator
  ```
- **Peer Messaging Bus (`messages.jsonl`)**:
  ```powershell
  # Post a message to all agents, a specific agent, or a role
  python "{manager_path}" post --project "{proj_root_str}" --from "<AGENT_ID>" --to "all|worker-2|role:collaborator" --message "<status or handoff note>" [--file "<path>"]

  # Check your filtered inbox (matches `all`, exact `<AGENT_ID>`, and `role:<your_role>`)
  python "{manager_path}" inbox --project "{proj_root_str}" --for "<AGENT_ID>" --limit 20
  ```

## 4. Cost-Optimal Smart Sizing & Non-Blocking Delegation Protocol

**Goal**: Zero wasted tokens, zero unnecessary agent sprawl, and instant readiness! Follow this exact decision matrix:

- **Tier 0 — Inline Quick Execution (`Mode: standard` & `<= 20s` / `1-3` files / quick log tail)**:
  Execute directly in your main loop -> call `worker-complete` -> re-run `worker-listen`. Do **NOT** spin up subagents for tiny quick tasks!
- **Tier 1 — Single Async Subagent (`Mode: subagents`, single focused heavy task `> 20s`)**:
  1. Spawn one background agent using the current host. Use `invoke_subagent` in Antigravity or `spawn_agent` in Codex.
  2. Pass all exact `SKILL.md` paths + instruction for the subagent to write a concise (`<=80` lines) summary to `{proj_root_str}\\temp_read\\result_<TASK_ID>.md` and call **`worker-complete --agent-id "<AGENT_ID>" --preserve-listening`** directly!
  3. Immediately run `worker-delegated --agent-id "<AGENT_ID>"` and re-launch **`worker-listen --agent-id "<AGENT_ID>"`** (`WaitMsBeforeAsync=10000`) so your slot stays `🟢 ONLINE_LISTENING` (READY)!
- **Tier 2 — Bounded Parallel Swarm (`Mode: swarm`, strictly for `3+` independent disjoint modules/angles)**:
  Spawn `2-4` parallel subagents or `native_swarm`, register `worker-delegated`, and re-launch `worker-listen` immediately. Never spawn multiple subagents touching overlapping files.

## 5. Direct Subagent <-> Orchestrator Channel (Zero Middleman Waste!)

Subagents spawned by any worker communicate **directly** with the Primary Orchestrator via `{manager_path}`:
- **Ask Orchestrator When Blocked / Ambiguous** (never guess with Flash!):
  ```powershell
  python "{manager_path}" worker-ask --project "{proj_root_str}" --task-id "<TASK_ID>" --agent-id "<AGENT_ID>" --question "<concise blocker or decision needed>" --wait --timeout 300
  ```
- **Deliver Final Result Directly**:
  ```powershell
  python "{manager_path}" worker-complete --project "{proj_root_str}" --task-id "<TASK_ID>" --claim-id "<CLAIM_ID>" --agent-id "<AGENT_ID>" --summary-file "{proj_root_str}\\temp_read\\result_<TASK_ID>.md" --artifacts "<comma_separated_paths>" --preserve-listening
  ```

## 6. Cross-Harness Skill Fallback & Exact `SKILL.md` Locations (3 Tiers)

If your harness (WSL AGY CLI, Codex, OpenCode, etc.) cannot auto-discover universal skills or use `/skill` slash commands:
1. Run `python "{manager_path}" skills --project "{proj_root_str}"` to print exact absolute `SKILL.md` paths (both Windows `C:\\...` and WSL `/mnt/c/...`).
2. Read `SKILL.md` directly from `C:\\Users\\Flh\\Desktop\\brain\\.agents\\skills\\<skill>\\SKILL.md` (or `./.agents/skills/<skill>/SKILL.md`).
3. Run bundled scripts directly by absolute path (append `< /dev/null` when invoking Windows `.exe` binaries from WSL).

### Tier A — Project-Specific Skills (`{project_slug}`)
{proj_skill_lines}

### Tier B — Universal Skills (`brain/.agents/skills/`)
{univ_skill_lines}

### Tier C — Built-in Antigravity Skills (`~/.gemini/antigravity/builtin/skills/`)
{builtin_skill_lines}

- Also check project context files first (if present):
{context_file_list}

## 7. Subagent & Swarm Defect Guard + Completion Handshake

- **CRITICAL DEFECT GUARD**: NEVER invoke `TypeName='DeepCoder'` or `TypeName='DeepInvestigator'` (missing `skill_search` runtime crash after 1s). Always use `TypeName='self'` or `TypeName='research'`.
- Write deliverables/scratch outputs into `{proj_root_str}\\temp_read\\`.
- Verify Proof-of-Work (`py_compile`, `tsc --noEmit`, `pytest`) before marking complete.
- Completion command (pass `--preserve-listening` when invoked by a background subagent while the main loop is in `worker-listen`):
```powershell
python "{manager_path}" worker-complete --project "{proj_root_str}" --task-id "<TASK_ID>" --claim-id "<CLAIM_ID>" --agent-id "<AGENT_ID>" --summary-file "{proj_root_str}\\temp_read\\result_<TASK_ID>.md" --artifacts "<comma_separated_paths>" --preserve-listening
```
"""


def _generate_offload_readme(project_slug: str, project_root: Path) -> str:
    manager_path = _to_display_path(Path(__file__).resolve())
    proj_root_str = _to_display_path(project_root)
    return f"""# `{project_slug}` Offload V3 Multi-Agent Message Board

- **`INSTRUCTIONS.md`**: Master operating manual for joining workers (`worker-X`), collaborators (`collab-X`), and main agents (`main-X`).
  > *"Read `offload/INSTRUCTIONS.md` and join the offload message board."*
- **`BOARD.md`**: Live Markdown dashboard featuring the **Multi-Agent Roster**, active task queue (with targets/owners), and recent peer messages.
- **`status.json`**: Machine-readable multi-agent roster (`agents`) + backward-compatible presence mirrors (`orchestrator`, `worker`).
- **`messages.jsonl`**: Append-only peer collaboration message bus (`post` / `inbox`).
- **`tasks/` & `results/`**: Atomic task payloads (`TASK-*.md` / `.json`) and completion receipts (`RESULT-*.md`).

## Quick CLI Commands
```powershell
# Join & listen as Worker (auto-assigns worker-1, worker-2, ...)
python "{manager_path}" worker-listen --project "{proj_root_str}" --role worker

# Join & listen as Collaborator (auto-assigns collab-1, collab-2, ...)
python "{manager_path}" worker-listen --project "{proj_root_str}" --role collaborator

# Register Main agent (auto-assigns main-1, main-2, ...)
python "{manager_path}" join --project "{proj_root_str}" --role main

# Check live Multi-Agent Roster & queue
python "{manager_path}" status --project "{proj_root_str}" --role none
```
"""


def ensure_offload_dir(project_slug: str, project_root: Path) -> Path:
    """Scaffold or refresh `<project>/offload/` while preserving existing tasks, results, comms, messages, and live status."""
    offload_dir = project_root / "offload"
    (offload_dir / "tasks").mkdir(parents=True, exist_ok=True)
    (offload_dir / "results").mkdir(parents=True, exist_ok=True)
    (offload_dir / "comms").mkdir(parents=True, exist_ok=True)

    gi_content = (
        "# Ignore ephemeral offload heartbeats, live renders, comms, messages, and task queues in Git\n"
        "status.json\n"
        "BOARD.md\n"
        "messages.jsonl\n"
        ".offload.lock\n"
        ".offload.lock.d/\n"
        "tasks/\n"
        "results/\n"
        "comms/\n"
        "!.gitignore\n"
        "!INSTRUCTIONS.md\n"
        "!README.md\n"
    )
    atomic_write_text(offload_dir / ".gitignore", gi_content)
    atomic_write_text(offload_dir / "INSTRUCTIONS.md", _generate_worker_instructions(project_slug, project_root))
    atomic_write_text(offload_dir / "README.md", _generate_offload_readme(project_slug, project_root))

    with offload_lock(offload_dir):
        status_path = offload_dir / "status.json"
        if not status_path.exists():
            _save_status(offload_dir, _default_status(project_slug, project_root))
        else:
            status = _load_status(offload_dir, project_slug, project_root)
            status.setdefault("project_name", project_slug)
            status["project_root"] = _to_display_path(project_root)
            status.setdefault("agents", {})
            _save_status(offload_dir, status)

        board_md = render_board_markdown(project_slug, project_root, offload_dir)
        atomic_write_text(offload_dir / "BOARD.md", board_md)
    return offload_dir


def update_presence(
    offload_dir: Path,
    project_slug: str,
    project_root: Path,
    role: str,
    state: str,
    note: Optional[str] = None,
    active_task_id: Optional[str] = None,
    active_expectation: Optional[str] = None,
    pid: Any = "__KEEP__",
    render_board: bool = True,
    agent_id: Optional[str] = None,
    host: Optional[str] = None,
    add_task: Optional[str] = None,
    remove_task: Optional[str] = None,
) -> Dict[str, Any]:
    """Update multi-agent roster presence and synchronized legacy mirrors, optionally re-rendering BOARD.md."""
    with offload_lock(offload_dir):
        status = _load_status(offload_dir, project_slug, project_root)
        now_ep = _now_epoch()
        now_str = _now_iso()
        norm_role = normalize_agent_role(role)

        if norm_role == "main":
            target_id = sanitize_agent_id(agent_id) if agent_id else "main-1"
            existing = status.get("agents", {}).get(target_id)
            effective_role = (
                normalize_agent_role(existing["role"])
                if isinstance(existing, dict) and existing.get("role")
                else "main"
            )
            _upsert_agent_entry(
                status,
                agent_id=target_id,
                role=effective_role,
                state=state,
                host=host or (existing.get("host") if isinstance(existing, dict) else "antigravity"),
                pid=pid,
                note=note,
                add_task=add_task,
                remove_task=remove_task,
                now_ep=now_ep,
                now_str=now_str,
            )
            orch = status.setdefault("orchestrator", {})
            orch["state"] = state
            orch["last_seen_epoch"] = now_ep
            orch["last_seen_iso"] = now_str
            if note is not None:
                orch["note"] = note
            if active_expectation is not None:
                orch["active_expectation"] = active_expectation
            _sync_legacy_mirrors(status, now=now_ep)
        else:
            if agent_id:
                target_id = sanitize_agent_id(agent_id)
                _upsert_agent_entry(
                    status,
                    agent_id=target_id,
                    role=norm_role,
                    state=state,
                    host=host,
                    pid=pid,
                    note=note,
                    add_task=add_task or (active_task_id if active_task_id and active_task_id != "__KEEP__" else None),
                    remove_task=remove_task,
                    now_ep=now_ep,
                    now_str=now_str,
                )
                if active_task_id is None:
                    # Explicitly clear current_tasks only when caller passed None (e.g. listening/offline)
                    if state == "OFFLINE":
                        status["agents"][target_id]["current_tasks"] = []
                _sync_legacy_mirrors(status, now=now_ep)
            else:
                # Legacy caller without explicit agent_id
                worker = status.setdefault("worker", {})
                worker["state"] = state
                worker["last_heartbeat_epoch"] = now_ep
                worker["last_heartbeat_iso"] = now_str
                if pid != "__KEEP__":
                    worker["pid"] = pid
                elif state == "OFFLINE":
                    worker["pid"] = None
                if note is not None:
                    worker["note"] = note
                if active_task_id != "__KEEP__":
                    worker["active_task_id"] = active_task_id

        status["updated_at"] = now_str
        _save_status(offload_dir, status)

        if render_board:
            atomic_write_text(offload_dir / "BOARD.md", render_board_markdown(project_slug, project_root, offload_dir))

        return status


def format_status_bar_terminal(project_slug: str, project_root: Path, offload_dir: Path) -> str:
    """Return a clean terminal readout of the Offload V3 Multi-Agent Roster, queue, and recent messages."""
    now_ep = _now_epoch()
    status = _load_status(offload_dir, project_slug, project_root)
    presence = _compute_effective_presence(status, now=now_ep)
    tasks = _load_tasks(offload_dir)
    pending = [t for t in tasks if t.get("status") == "PENDING"]
    in_progress = [t for t in tasks if t.get("status") == "IN_PROGRESS"]
    completed = [t for t in tasks if t.get("status") == "COMPLETED"]
    failed = [t for t in tasks if t.get("status") == "FAILED"]
    roster = _sorted_roster_entries(status, now=now_ep)
    recent_msgs = _load_messages(offload_dir)[-5:]

    disp_root = _to_display_path(project_root)
    lines = [
        "================================================================================",
        f" OFFLOAD V3 ROSTER & STATUS :: {project_slug} ({disp_root})",
        "--------------------------------------------------------------------------------",
        (
            f" Live Agents  : Main={presence['live_main_count']} | Collab={presence['live_collab_count']} | "
            f"Workers={presence['live_worker_count']} (Total registered: {presence['total_agents_count']})"
        ),
        (
            f" Legacy Sync  : Orch={presence['orchestrator_badge']} | "
            f"Worker={presence['worker_badge']}"
        ),
        f" Queue        : Pending={len(pending)} | In Progress={len(in_progress)} | Completed={len(completed)} | Failed={len(failed)}",
    ]

    if roster:
        lines.append("--------------------------------------------------------------------------------")
        lines.append(" Multi-Agent Roster:")
        for group_label, group_role in (("Main Agents", "main"), ("Collaborators", "collaborator"), ("Workers", "worker")):
            group_entries = [e for e in roster if normalize_agent_role(e.get("role")) == group_role]
            if not group_entries:
                continue
            lines.append(f"   [{group_label}]")
            for e in group_entries:
                badge, _, age_str = _format_agent_badge(e, now=now_ep)
                pid_str = str(e.get("pid")) if e.get("pid") else "—"
                cur_tasks = ", ".join(e.get("current_tasks") or []) or "IDLE"
                lines.append(
                    f"     - {e.get('agent_id', '?'):<12} ({e.get('host') or 'cli':<11}) | {badge:<20} | "
                    f"PID:{pid_str:<7} | Seen:{age_str:<10} | Tasks:{cur_tasks}"
                )

    lines.append("================================================================================")

    if pending:
        lines.append(" Pending Tasks:")
        for t in pending[:8]:
            tgt = t.get("target_agent", "any")
            frm = t.get("from_agent", "main-1")
            lines.append(f"   - {t['task_id']} [to={tgt} | from={frm} | {t.get('mode', 'standard')}]: {t.get('title')}")
    if in_progress:
        lines.append(" Active Tasks:")
        for t in in_progress[:8]:
            tgt = t.get("target_agent", "any")
            owner = t.get("claimed_by") or "worker"
            lines.append(f"   - {t['task_id']} [by={owner} | to={tgt} | {t.get('mode', 'standard')}]: {t.get('title')}")
    for q in _load_pending_questions(offload_dir)[:3]:
        lines.append(f" QUESTION PENDING [{q.get('task_id')}]: {q.get('question', '')[:100]}")
    if recent_msgs:
        lines.append(" Recent Peer Messages (last 5):")
        for m in recent_msgs:
            f_tag = f" [file: {m['file']}]" if m.get("file") else ""
            lines.append(f"   - [{m.get('ts', '')}] {m.get('from', '?')} -> {m.get('to', 'all')}: {m.get('message', '')}{f_tag}")
    return "\n".join(lines)


def _format_task_dossier(task: Dict[str, Any], project_slug: str, project_root: Path, offload_dir: Path) -> str:
    """Format the full self-contained Task Execution Dossier for TASK-<id>.md and worker-listen stdout."""
    manager_path = _to_display_path(Path(__file__).resolve())
    proj_root_str = _to_display_path(project_root)
    tid = task["task_id"]
    claim_flag = f'--claim-id "{task["claim_id"]}"' if task.get("claim_id") else ""
    claimed_by = task.get("claimed_by")
    agent_flag = f'--agent-id "{claimed_by}"' if claimed_by else ""
    from_agent = task.get("from_agent", "main-1")
    target_agent = task.get("target_agent", "any")
    mode = task.get("mode", "standard")
    inline_exec = bool(task.get("inline", False))
    result_draft = _to_display_path(project_root / "temp_read" / f"result_{tid}.md")

    non_blocking_guide = "" if inline_exec else (
        f"\n  - **STAY READY (NON-BLOCKING PROTOCOL)**: Do NOT block your main CLI loop executing this long task inline!\n"
        f"    1. Spawn **only the minimum needed** background subagent(s) (default `1` unless disjoint slices require `2-4` via `swarm`) — NEVER spin up redundant agents just because you can.\n"
        f"    2. Pass ALL `SKILL.md` paths below and instruct the child agent to communicate **directly** with the Orchestrator:\n"
        f"       - If blocked/unclear: run `python \"{manager_path}\" worker-ask --project \"{proj_root_str}\" --task-id \"{tid}\" {agent_flag} --question \"<question>\" --wait --timeout 300`\n"
        f"       - When done: write concise (`<=80` lines) result to `{result_draft}` and run `python \"{manager_path}\" worker-complete --project \"{proj_root_str}\" --task-id \"{tid}\" {claim_flag} {agent_flag} --summary-file \"{result_draft}\" --artifacts \"<paths>\" --preserve-listening`\n"
        f"    3. Immediately run `python \"{manager_path}\" worker-delegated --project \"{proj_root_str}\" --task-id \"{tid}\" {agent_flag} --subagent-id \"<id>\"`.\n"
        f"    4. Re-run `worker-listen {agent_flag}`. Use Antigravity reactive wakeup or wait on the Codex shell session."
    )

    mode_directives = {
        "standard": (
            "Execute this task directly if quick (`<=20s`), following the injected `SKILL.md` paths below, or delegate with the current host's agent tools if longer. "
            "Run Proof-of-Work verification before completing."
        ),
        "subagents": (
            "**DELEGATE WITH SUBAGENTS (NON-BLOCKING DEFAULT)**: Use the current host's agent tools. "
            "In Antigravity, use `TypeName='self'` for coding and `TypeName='research'` for exploration. "
            "Pass explicit `SKILL.md` paths into every subagent's prompt." + non_blocking_guide
        ),
        "swarm": (
            "**ORCHESTRATE MULTI-AGENT SWARM / WORKFLOW (NON-BLOCKING DEFAULT)**: Read `native_swarm/SKILL.md` / `run-workflow/SKILL.md` / "
            "`exhaustive-audit-and-repair/SKILL.md` as listed below, coordinate parallel agents cleanly, "
            "cross-check findings, and synthesize final deliverables." + non_blocking_guide
        ),
    }

    skills_lines = []
    for idx, s in enumerate(task.get("skills", [])):
        tag = "MANDATORY DEFAULT" if idx == 0 else "REQUIRED SKILL"
        tier = s.get("tier", "SKILL")
        skills_lines.append(f"{idx + 1}. **[{tag} | {tier}] `{s['name']}`**: Read `{_to_display_path(s['path'])}`\n   - Purpose: {s['description']}")

    context_lines = [f"- `{c}`" for c in task.get("context_files", [])] or ["- Use project `file_map.md` and `context/constraints.md` / `context/mistakes.md` if present."]
    claimed_line = f"\n- **Claimed By**: `{claimed_by}`" if claimed_by else ""

    return f"""# OFFLOAD TASK DOSSIER: `{tid}`

- **Project**: `{project_slug}` (`{proj_root_str}`)
- **Task ID**: `{tid}`
- **Title**: {task.get('title')}
- **Status**: `{task.get('status')}`
- **From**: `{from_agent}`
- **Target**: `{target_agent}`{claimed_line}
- **Execution Mode**: `{mode}` (`{'inline' if inline_exec else 'async-ready'}`)
- **Dispatched At**: `{task.get('created_at')}`
- **WSL / POSIX Note**: Windows paths `C:\\...` map to `/mnt/c/...` in WSL.
- If Windows-only dependencies or native scripts are needed, use `/mnt/c/Python314/python.exe`.

---

## 1. Mandatory Skills to Load (`read_file` Before Acting)
Because slash commands cannot be typed across instances, read these exact `SKILL.md` files directly:
{chr(10).join(skills_lines)}

> List all local/universal/builtin skill paths: `python "{manager_path}" skills --project "{proj_root_str}"`
> Domain lookup: `python "{_to_display_path(SELECT_SKILL_PY)}" "<domain>" --project {project_slug}`

## 2. Execution Directive ({mode.upper()})
{mode_directives.get(mode, mode_directives["standard"])}

## 3. Reference Context Files
{chr(10).join(context_lines)}

## 4. Deliverable & Workspace Guardrails
- Keep deliverables/scripts inside `{proj_root_str}\\temp_read\\` (unless editing actual project source files requested by the task).
- Verify Proof-of-Work (`py_compile`, `tsc --noEmit`, `pytest`, etc.) before marking complete.

## 5. Task Prompt
{task.get('prompt', '').strip()}

---

## 6. Completion Handshake (Run When Finished)

Use the claimed dossier ownership ID for completion, including delegated completion.
Write a concise result summary to `{result_draft}` and execute:
```powershell
python "{manager_path}" worker-complete --project "{proj_root_str}" --task-id "{tid}" {claim_flag} {agent_flag} --summary-file "{result_draft}" --artifacts "<comma_separated_paths>" --preserve-listening
```
"""


def cmd_init(args: argparse.Namespace) -> int:
    if args.all:
        targets = discover_all_targets(include_brain=True)
        print(f"[OffloadInit] Provisioning offload/ message boards across {len(targets)} workspace(s)...")
        for slug, root in sorted(targets.items(), key=lambda kv: kv[0].lower()):
            if not root.exists():
                print(f"  [!] Skipped missing path: {slug} -> {root}")
                continue
            off_dir = ensure_offload_dir(slug, root)
            print(f"  [+] Synced: {slug:<16} -> {off_dir}")
        return 0

    slug, root = resolve_target_project(args.project, args.workspaces)
    off_dir = ensure_offload_dir(slug, root)
    print(f"[OffloadInit] Initialized message board for '{slug}' at: {off_dir}")
    print(format_status_bar_terminal(slug, root, off_dir))
    return 0


def cmd_join(args: argparse.Namespace) -> int:
    """Register an agent (main | worker | collaborator) in the multi-agent roster with atomic auto-ID allocation."""
    slug, root = resolve_target_project(args.project, args.workspaces)
    off_dir = ensure_offload_dir(slug, root)
    norm_role = normalize_agent_role(args.role)
    host = (args.host or "").strip() or ("antigravity" if norm_role == "main" else "cli")
    pid = os.getpid()

    with offload_lock(off_dir):
        status = _load_status(off_dir, slug, root)
        now_ep = _now_epoch()
        now_str = _now_iso()
        agent_id = allocate_agent_id(status, norm_role, requested_id=args.agent_id, pid=pid, now=now_ep)
        note = args.note.strip() if getattr(args, "note", None) else f"Joined as {agent_id}"
        entry = _upsert_agent_entry(
            status,
            agent_id=agent_id,
            role=norm_role,
            state="ONLINE",
            host=host,
            pid=pid,
            note=note,
            now_ep=now_ep,
            now_str=now_str,
        )
        _sync_legacy_mirrors(status, now=now_ep)
        status["updated_at"] = now_str
        _save_status(off_dir, status)
        atomic_write_text(off_dir / "BOARD.md", render_board_markdown(slug, root, off_dir))

    if getattr(args, "json", False):
        payload = {
            "agent_id": agent_id,
            "role": norm_role,
            "host": host,
            "pid": pid,
            "state": entry["state"],
            "project": slug,
            "board": _to_display_path(off_dir / "BOARD.md"),
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"[OffloadJoin] Joined '{slug}' as {agent_id} (role={norm_role}, host={host})")
    return 0


def cmd_leave(args: argparse.Namespace) -> int:
    """Mark an agent OFFLINE and release its active PID cleanly."""
    slug, root = resolve_target_project(args.project, args.workspaces)
    off_dir = ensure_offload_dir(slug, root)
    agent_id = sanitize_agent_id(args.agent_id)
    if not agent_id:
        raise ValueError("A valid --agent-id is required for leave.")

    with offload_lock(off_dir):
        status = _load_status(off_dir, slug, root)
        now_ep = _now_epoch()
        now_str = _now_iso()
        agents = status.setdefault("agents", {})
        existing = agents.get(agent_id)
        role = normalize_agent_role(existing.get("role")) if isinstance(existing, dict) else _infer_role_from_agent_id(agent_id)
        note = args.note.strip() if getattr(args, "note", None) else "Left board cleanly"
        entry = _upsert_agent_entry(
            status,
            agent_id=agent_id,
            role=role,
            state="OFFLINE",
            pid=None,
            note=note,
            now_ep=now_ep,
            now_str=now_str,
        )
        entry["current_tasks"] = []
        _sync_legacy_mirrors(status, now=now_ep)
        status["updated_at"] = now_str
        _save_status(off_dir, status)
        atomic_write_text(off_dir / "BOARD.md", render_board_markdown(slug, root, off_dir))

    print(f"[OffloadLeave] Marked {agent_id} OFFLINE on '{slug}'.")
    return 0


def cmd_post(args: argparse.Namespace) -> int:
    """Append a peer collaboration message to `<project>/offload/messages.jsonl`."""
    slug, root = resolve_target_project(args.project, args.workspaces)
    off_dir = ensure_offload_dir(slug, root)
    msg_text = (args.message or "").strip()
    if not msg_text:
        raise ValueError("Message cannot be empty. Provide --message.")
    file_arg = str(_to_host_path(args.file)) if getattr(args, "file", None) else None
    msg = post_message(
        offload_dir=off_dir,
        project_slug=slug,
        project_root=root,
        from_agent=args.from_agent,
        to_target=args.to_target,
        message=msg_text,
        file_path=file_arg,
    )
    print(f"[OffloadPost] {msg['id']} ({msg['from']} -> {msg['to']}): {msg['message']}")
    return 0


def cmd_inbox(args: argparse.Namespace) -> int:
    """Read peer messages filtered by `--for <agent_id>` and/or `--role <role>`."""
    slug, root = resolve_target_project(args.project, args.workspaces)
    off_dir = ensure_offload_dir(slug, root)
    items = query_inbox(
        offload_dir=off_dir,
        for_agent=getattr(args, "for_agent", None),
        role=getattr(args, "role", None),
        limit=getattr(args, "limit", 20),
    )
    if getattr(args, "json", False):
        print(json.dumps(items, indent=2, ensure_ascii=False))
        return 0

    if not items:
        scope = args.for_agent or (f"role:{args.role}" if args.role else "all")
        print(f"[OffloadInbox] No messages for '{scope}' on '{slug}'.")
        return 0

    print(f"=== OFFLOAD INBOX :: {slug} ({len(items)} message(s)) ===")
    for m in items:
        f_tag = f" [file: {m['file']}]" if m.get("file") else ""
        print(f"  [{m.get('ts', '')}] ({m.get('id', '')}) {m.get('from', '?')} -> {m.get('to', 'all')}: {m.get('message', '')}{f_tag}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    if args.all:
        targets = discover_all_targets(include_brain=True)
        print("================================================================================================================")
        print(f" OFFLOAD FLEET OBSERVABILITY ({len(targets)} Workspaces) :: {_now_iso()}")
        print("----------------------------------------------------------------------------------------------------------------")
        print(f" {'Project':<16} | {'Live (M/C/W)':<12} | {'Orchestrator':<22} | {'Worker':<24} | {'Queue (P/A/C)':<13} | Path")
        print("----------------------------------------------------------------------------------------------------------------")
        for slug, root in sorted(targets.items(), key=lambda kv: kv[0].lower()):
            off_dir = root / "offload"
            if not off_dir.is_dir():
                print(f" {slug:<16} | {'—':<12} | {'UNINITIALIZED':<22} | {'UNINITIALIZED':<24} | {'—':<13} | {root}")
                continue
            status = _load_status(off_dir, slug, root)
            pres = _compute_effective_presence(status)
            tasks = _load_tasks(off_dir)
            p_cnt = sum(1 for t in tasks if t.get("status") == "PENDING")
            a_cnt = sum(1 for t in tasks if t.get("status") == "IN_PROGRESS")
            c_cnt = sum(1 for t in tasks if t.get("status") == "COMPLETED")
            q_str = f"{p_cnt} / {a_cnt} / {c_cnt}"
            live_str = f"{pres['live_main_count']}/{pres['live_collab_count']}/{pres['live_worker_count']}"
            print(f" {slug:<16} | {live_str:<12} | {pres['orchestrator_short']:<22} | {pres['worker_short']:<24} | {q_str:<13} | {off_dir}")
        print("================================================================================================================")
        return 0

    slug, root = resolve_target_project(args.project, args.workspaces)
    off_dir = ensure_offload_dir(slug, root)
    req_agent_id = getattr(args, "agent_id", None)
    if args.role in ("orchestrator", "main"):
        update_presence(
            off_dir, slug, root,
            role="main",
            state="ONLINE",
            note="Checked board status",
            agent_id=req_agent_id or "main-1",
            render_board=True,
        )
    elif args.role in ("worker", "collaborator"):
        update_presence(
            off_dir, slug, root,
            role=args.role,
            state="ONLINE_LISTENING",
            note="Checked board status",
            active_task_id="__KEEP__",
            agent_id=req_agent_id,
            render_board=True,
        )
    print(format_status_bar_terminal(slug, root, off_dir))
    return 0


def cmd_dispatch(args: argparse.Namespace) -> int:
    slug, root = resolve_target_project(args.project, args.workspaces)
    off_dir = ensure_offload_dir(slug, root)

    prompt_text = args.prompt or ""
    if args.prompt_file:
        pfile = _to_host_path(args.prompt_file)
        if not pfile.is_file():
            raise FileNotFoundError(f"Prompt file not found: {pfile}")
        prompt_text = pfile.read_text(encoding="utf-8")

    if not prompt_text.strip():
        raise ValueError("Task prompt cannot be empty. Provide --prompt or --prompt-file.")

    requested_skills = [s.strip() for s in args.skills.split(",")] if args.skills else []
    explicit_skill_paths = [s.strip() for s in args.skill_paths.split(",")] if getattr(args, "skill_paths", "") else []
    if args.mode == "swarm" and not any(s.lower() in ("swarm", "teamwork", "native_swarm", "run-workflow") for s in requested_skills):
        requested_skills.append("native_swarm")
    resolved_skills = resolve_skill_paths(requested_skills, root, slug, explicit_paths=explicit_skill_paths)

    context_files = [
        _to_display_path(_to_host_path(c.strip()))
        for c in args.context.split(",")
        if c.strip()
    ] if args.context else []

    from_agent = sanitize_agent_id(args.from_agent) if getattr(args, "from_agent", None) else "main-1"
    target_agent = _normalize_target(getattr(args, "target_agent", None), default="any")

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    task_id = f"TASK-{stamp}-{uuid.uuid4().hex[:4]}"

    task_obj: Dict[str, Any] = {
        "task_id": task_id,
        "project_name": slug,
        "project_root": _to_display_path(root),
        "title": args.title.strip(),
        "status": "PENDING",
        "from_agent": from_agent,
        "target_agent": target_agent,
        "claimed_by": None,
        "mode": args.mode,
        "inline": bool(getattr(args, "inline", False)),
        "skills": resolved_skills,
        "context_files": context_files,
        "prompt": prompt_text,
        "created_at": _now_iso(),
        "created_epoch": _now_epoch(),
        "claimed_at": None,
        "completed_at": None,
    }

    task_json_path = off_dir / "tasks" / f"{task_id}.json"
    task_md_path = off_dir / "tasks" / f"{task_id}.md"

    with offload_lock(off_dir):
        atomic_write_json(task_json_path, task_obj)
        atomic_write_text(task_md_path, _format_task_dossier(task_obj, slug, root, off_dir))

        status = _load_status(off_dir, slug, root)
        now_ep = _now_epoch()
        now_str = _now_iso()
        existing_sender = status.get("agents", {}).get(from_agent)
        sender_role = (
            normalize_agent_role(existing_sender["role"])
            if isinstance(existing_sender, dict) and existing_sender.get("role")
            else _infer_role_from_agent_id(from_agent, default="main")
        )
        sender_host = (
            existing_sender.get("host")
            if isinstance(existing_sender, dict) and existing_sender.get("host")
            else ("antigravity" if sender_role == "main" else "cli")
        )
        _upsert_agent_entry(
            status,
            agent_id=from_agent,
            role=sender_role,
            state="WAITING_FOR_RESULT" if args.wait else "ONLINE",
            host=sender_host,
            note=f"Dispatched {task_id} (to={target_agent})",
            now_ep=now_ep,
            now_str=now_str,
        )
        if sender_role == "main":
            orch = status.setdefault("orchestrator", {})
            orch["active_expectation"] = f"Expecting {task_id}"
        _sync_legacy_mirrors(status, now=now_ep)
        status["updated_at"] = now_str
        _save_status(off_dir, status)
        atomic_write_text(off_dir / "BOARD.md", render_board_markdown(slug, root, off_dir))

    print(f"[OffloadDispatch] Dispatched {task_id} (from={from_agent}, to={target_agent}) -> {task_md_path}")
    print(format_status_bar_terminal(slug, root, off_dir))

    status_snapshot = _load_status(off_dir, slug, root)
    pres = _compute_effective_presence(status_snapshot)
    if not pres["worker_is_live"]:
        print(
            "\n[Notice] No live Worker/Collaborator is currently listening on this board. "
            f"Tell a worker agent in '{slug}' to run:\n"
            f'  python "{_to_display_path(Path(__file__).resolve())}" worker-listen --project "{_to_display_path(root)}" --role worker'
        )

    if not args.wait:
        return 0

    return _wait_for_task_or_question(off_dir, slug, root, task_id, args.timeout)


def _wait_for_task_or_question(
    off_dir: Path,
    slug: str,
    root: Path,
    task_id: Optional[str],
    timeout: int,
) -> int:
    """Block efficiently (0 LLM tokens) until target task completes/fails OR a subagent posts a question."""
    deadline = _now_epoch() + timeout
    last_ping = _now_epoch()
    label = task_id or "any active task"
    print(f"\n[OffloadWait] Waiting up to {timeout}s for {label} completion or clarification question...", flush=True)

    while _now_epoch() < deadline:
        # 1. Surface any unanswered subagent question immediately (exit code 2)
        pending_qs = _load_pending_questions(off_dir)
        for q in pending_qs:
            if task_id and q.get("task_id") != task_id:
                continue
            q_tid = q.get("task_id")
            update_presence(
                off_dir, slug, root,
                role="orchestrator",
                state="ONLINE",
                note=f"Question waiting on {q_tid}",
                active_expectation=f"Answer {q_tid}",
                render_board=True,
            )
            print(f"\n[ORCHESTRATOR_QUESTION: {q_tid}] From: {q.get('sender', 'worker')}")
            print(f"Question: {q.get('question', '')}")
            print(
                f'Reply via: python "{_to_display_path(Path(__file__).resolve())}" answer --project "{_to_display_path(root)}" '
                f'--task-id "{q_tid}" --reply "<decision>"'
            )
            return 2

        # 2. Check completion of target task (or any newly completed active task)
        tasks = _load_tasks(off_dir)
        target_tasks = [t for t in tasks if t.get("task_id") == task_id] if task_id else tasks
        for current in target_tasks:
            st = current.get("status")
            cid = current.get("task_id")
            if task_id and st in ("COMPLETED", "FAILED", "CANCELLED"):
                update_presence(
                    off_dir, slug, root,
                    role="orchestrator",
                    state="ONLINE",
                    note=f"Collected {cid} ({st})",
                    active_expectation="NONE",
                    render_board=True,
                )
                res_md = off_dir / "results" / f"RESULT-{cid}.md"
                print(f"\n[OffloadWait] {cid} finished with status: {st}")
                if res_md.is_file():
                    print(res_md.read_text(encoding="utf-8", errors="replace"))
                return 0 if st == "COMPLETED" else 1

        if _now_epoch() - last_ping >= 10.0:
            update_presence(
                off_dir, slug, root,
                role="orchestrator",
                state="WAITING_FOR_RESULT",
                note=f"Waiting on {label}",
                active_expectation=f"Waiting on {label}",
                render_board=False,
            )
            last_ping = _now_epoch()
        time.sleep(2.0)

    update_presence(
        off_dir, slug, root,
        role="orchestrator",
        state="ONLINE",
        note=f"Wait timed out on {label}",
        active_expectation=f"Timed out waiting on {label}",
        render_board=True,
    )
    print(f"[OffloadWait] Timeout reached after {timeout}s while waiting for {label}.")
    return 1


def cmd_wait(args: argparse.Namespace) -> int:
    slug, root = resolve_target_project(args.project, args.workspaces)
    off_dir = ensure_offload_dir(slug, root)
    tid = args.task_id
    if not tid:
        active = [t for t in _load_tasks(off_dir) if t.get("status") in ("PENDING", "IN_PROGRESS")]
        if active:
            tid = active[0]["task_id"]
        else:
            print(f"[OffloadWait] No active/pending tasks on '{slug}'.")
            return 0
    return _wait_for_task_or_question(off_dir, slug, root, tid, args.timeout)


def _claim_task(
    off_dir: Path,
    slug: str,
    root: Path,
    task_id: str,
    pid: int,
    agent_id: Optional[str] = None,
    role: str = "worker",
    host: Optional[str] = None,
    enforce_target: bool = False,
) -> Optional[Dict[str, Any]]:
    """Atomically claim a PENDING task under `offload_lock` and bind ownership (`claim_id` + `claimed_by`)."""
    norm_role = normalize_agent_role(role)
    with offload_lock(off_dir):
        task_path = off_dir / "tasks" / f"{task_id}.json"
        task = safe_read_json(task_path)
        if not task or task.get("status") != "PENDING":
            return None

        status = _load_status(off_dir, slug, root)
        now_ep = _now_epoch()
        now_str = _now_iso()
        eff_agent_id = allocate_agent_id(status, norm_role, requested_id=agent_id, pid=pid, now=now_ep)

        if enforce_target and not _target_matches(task.get("target_agent", "any"), eff_agent_id, norm_role):
            return None

        task["claim_id"] = uuid.uuid4().hex
        task["status"] = "IN_PROGRESS"
        task["claimed_at"] = now_str
        task["worker_pid"] = pid
        task["claimed_by"] = eff_agent_id
        task_id = task["task_id"]
        atomic_write_json(task_path, task)
        atomic_write_text(off_dir / "tasks" / f"{task_id}.md", _format_task_dossier(task, slug, root, off_dir))

        _upsert_agent_entry(
            status,
            agent_id=eff_agent_id,
            role=norm_role,
            state="BUSY_EXECUTING",
            host=host,
            pid=pid,
            note=f"Executing {task_id}",
            add_task=task_id,
            now_ep=now_ep,
            now_str=now_str,
        )
        _sync_legacy_mirrors(status, now=now_ep)
        status["updated_at"] = now_str
        _save_status(off_dir, status)
        atomic_write_text(off_dir / "BOARD.md", render_board_markdown(slug, root, off_dir))
        return task


def cmd_worker_listen(args: argparse.Namespace) -> int:
    slug, root = resolve_target_project(args.project, args.workspaces)
    off_dir = ensure_offload_dir(slug, root)
    pid = os.getpid()
    norm_role = normalize_agent_role(getattr(args, "role", "worker"))
    host = (getattr(args, "host", None) or "").strip() or "cli"

    with offload_lock(off_dir):
        status = _load_status(off_dir, slug, root)
        now_ep = _now_epoch()
        now_str = _now_iso()
        agent_id = allocate_agent_id(status, norm_role, requested_id=getattr(args, "agent_id", None), pid=pid, now=now_ep)
        _upsert_agent_entry(
            status,
            agent_id=agent_id,
            role=norm_role,
            state="ONLINE_LISTENING",
            host=host,
            pid=pid,
            note=f"{agent_id} listening on queue",
            now_ep=now_ep,
            now_str=now_str,
        )
        _sync_legacy_mirrors(status, now=now_ep)
        status["updated_at"] = now_str
        _save_status(off_dir, status)
        atomic_write_text(off_dir / "BOARD.md", render_board_markdown(slug, root, off_dir))

    print(format_status_bar_terminal(slug, root, off_dir), flush=True)
    print(
        f"[WorkerListen] Joined as {agent_id} (role={norm_role}) listening on {off_dir / 'tasks'} "
        f"(timeout={args.timeout}s, poll={args.poll_interval}s)...",
        flush=True,
    )

    deadline = _now_epoch() + args.timeout
    last_heartbeat = _now_epoch()
    last_board_render = _now_epoch()

    try:
        while _now_epoch() <= deadline:
            tasks_dir = off_dir / "tasks"
            pending_tasks: List[Dict[str, Any]] = []
            if tasks_dir.is_dir():
                for jf in sorted(tasks_dir.glob("TASK-*.json")):
                    data = safe_read_json(jf)
                    if (
                        data
                        and data.get("status") == "PENDING"
                        and _target_matches(data.get("target_agent", "any"), agent_id, norm_role)
                    ):
                        pending_tasks.append(data)

            if pending_tasks:
                pending_tasks.sort(key=lambda t: float(t.get("created_epoch") or 0.0))
                chosen: Optional[Dict[str, Any]] = None
                for cand in pending_tasks:
                    chosen = _claim_task(
                        off_dir, slug, root,
                        cand["task_id"],
                        pid=pid,
                        agent_id=agent_id,
                        role=norm_role,
                        host=host,
                        enforce_target=True,
                    )
                    if chosen is not None:
                        break
                if chosen is None:
                    continue
                print(f"\n[TASK_CLAIMED: {chosen['task_id']}] (by {agent_id})", flush=True)
                print(format_status_bar_terminal(slug, root, off_dir), flush=True)
                print(_format_task_dossier(chosen, slug, root, off_dir), flush=True)
                return 0

            now = _now_epoch()
            if now - last_heartbeat >= 5.0:
                should_render = (now - last_board_render) >= 30.0
                update_presence(
                    off_dir, slug, root,
                    role=norm_role,
                    state="ONLINE_LISTENING",
                    note=f"{agent_id} listening on queue",
                    active_task_id="__KEEP__",
                    pid=pid,
                    agent_id=agent_id,
                    host=host,
                    render_board=should_render,
                )
                last_heartbeat = now
                if should_render:
                    last_board_render = now

            if args.once:
                break
            time.sleep(max(0.2, args.poll_interval))
    except KeyboardInterrupt:
        update_presence(
            off_dir, slug, root,
            role=norm_role,
            state="OFFLINE",
            note="Listener stopped via KeyboardInterrupt",
            active_task_id=None,
            pid=None,
            agent_id=agent_id,
            host=host,
            render_board=True,
        )
        print(f"\n[WorkerListen] {agent_id} stopped by KeyboardInterrupt.")
        return 0

    update_presence(
        off_dir, slug, root,
        role=norm_role,
        state="OFFLINE",
        note=f"Standby window elapsed ({args.timeout}s) with no pending tasks",
        active_task_id=None,
        pid=None,
        agent_id=agent_id,
        host=host,
        render_board=True,
    )
    print(f"\n[TIMEOUT_STANDBY] {agent_id}: No matching pending tasks received within {args.timeout}s. Re-run worker-listen to stay online.")
    return 0


def cmd_worker_claim(args: argparse.Namespace) -> int:
    slug, root = resolve_target_project(args.project, args.workspaces)
    off_dir = ensure_offload_dir(slug, root)
    task_json = off_dir / "tasks" / f"{args.task_id}.json"
    if not task_json.is_file():
        raise FileNotFoundError(f"Task not found: {task_json}")
    chosen = _claim_task(
        off_dir, slug, root,
        args.task_id,
        pid=os.getpid(),
        agent_id=getattr(args, "agent_id", None),
        role=getattr(args, "role", "worker"),
        host=getattr(args, "host", None),
        enforce_target=False,
    )
    if chosen is None:
        print(f"[WorkerClaim] {args.task_id} is no longer pending", file=sys.stderr)
        return 1
    print(f"[WorkerClaim] Claimed {chosen['task_id']} (by {chosen.get('claimed_by', 'worker')})")
    print(_format_task_dossier(chosen, slug, root, off_dir))
    return 0


def cmd_worker_delegated(args: argparse.Namespace) -> int:
    """Record that a claimed task was handed off to a background subagent/swarm so the worker can return to READY."""
    slug, root = resolve_target_project(args.project, args.workspaces)
    off_dir = ensure_offload_dir(slug, root)
    with offload_lock(off_dir):
        task_json = off_dir / "tasks" / f"{args.task_id}.json"
        if not task_json.is_file():
            raise FileNotFoundError(f"Task not found: {task_json}")

        task = safe_read_json(task_json)
        if task.get("status") != "IN_PROGRESS":
            print("[WorkerDelegated] Task is not in progress", file=sys.stderr)
            return 1
        task["delegated_to"] = args.subagent_id or "background-subagent"
        task["delegated_at"] = _now_iso()
        atomic_write_json(task_json, task)
        atomic_write_text(off_dir / "tasks" / f"{args.task_id}.md", _format_task_dossier(task, slug, root, off_dir))

        status = _load_status(off_dir, slug, root)
        now_ep = _now_epoch()
        now_str = _now_iso()
        worker = status.setdefault("worker", {})
        delegated = [d for d in (worker.get("delegated_tasks") or []) if d != args.task_id]
        delegated.append(args.task_id)
        worker["delegated_tasks"] = delegated

        eff_agent_id = sanitize_agent_id(args.agent_id) if getattr(args, "agent_id", None) else (task.get("claimed_by") or "")
        agents = status.get("agents") or {}
        if eff_agent_id and eff_agent_id in agents and isinstance(agents[eff_agent_id], dict):
            entry = agents[eff_agent_id]
            cur_tasks = [t for t in (entry.get("current_tasks") or []) if t != args.task_id]
            entry["current_tasks"] = cur_tasks
            if str(entry.get("state", "")).upper() == "BUSY_EXECUTING" and not cur_tasks:
                entry["state"] = "OFFLINE"
                entry["pid"] = None
                entry["note"] = args.note or f"Delegated {args.task_id}; restart the listener"
                entry["last_seen"] = now_str
                entry["last_seen_epoch"] = now_ep
            _sync_legacy_mirrors(status, now=now_ep)
        elif worker.get("active_task_id") == args.task_id:
            worker["active_task_id"] = None
            worker["state"] = "OFFLINE"
            worker["pid"] = None
            worker["note"] = args.note or f"Delegated {args.task_id}; restart the listener"

        status["updated_at"] = now_str
        _save_status(off_dir, status)
        atomic_write_text(off_dir / "BOARD.md", render_board_markdown(slug, root, off_dir))

    print(f"[WorkerDelegated] {args.task_id} running in background ({task['delegated_to']}); worker returning to READY.")
    print(format_status_bar_terminal(slug, root, off_dir))
    return 0


def cmd_worker_ask(args: argparse.Namespace) -> int:
    """Allow CLI worker or its spawned subagent to ask Primary Orchestrator a direct clarification question."""
    slug, root = resolve_target_project(args.project, args.workspaces)
    off_dir = ensure_offload_dir(slug, root)
    tid = args.task_id
    q_path = off_dir / "comms" / f"{tid}.json"
    req_agent_id = sanitize_agent_id(args.agent_id) if getattr(args, "agent_id", None) else ""
    sender = args.sender
    if req_agent_id and (not sender or sender == "subagent"):
        sender = req_agent_id
    q_obj: Dict[str, Any] = {
        "task_id": tid,
        "sender": sender or "subagent",
        "agent_id": req_agent_id or None,
        "status": "PENDING_ANSWER",
        "question": args.question.strip(),
        "asked_at": _now_iso(),
        "asked_epoch": _now_epoch(),
        "reply": None,
        "answered_at": None,
    }
    with offload_lock(off_dir):
        atomic_write_json(q_path, q_obj)

        task_json = off_dir / "tasks" / f"{tid}.json"
        if task_json.is_file():
            task = safe_read_json(task_json)
            task["awaiting_orchestrator"] = True
            if not req_agent_id and task.get("claimed_by"):
                req_agent_id = str(task["claimed_by"])
            atomic_write_json(task_json, task)

        if req_agent_id:
            status = _load_status(off_dir, slug, root)
            agents = status.get("agents") or {}
            if req_agent_id in agents and isinstance(agents[req_agent_id], dict):
                agents[req_agent_id]["last_seen"] = _now_iso()
                agents[req_agent_id]["last_seen_epoch"] = _now_epoch()
                status["updated_at"] = _now_iso()
                _save_status(off_dir, status)

        atomic_write_text(off_dir / "BOARD.md", render_board_markdown(slug, root, off_dir))
    print(f"[WorkerAsk] Posted question for {tid} -> {q_path}", flush=True)

    if not args.wait:
        return 0

    deadline = _now_epoch() + args.timeout
    while _now_epoch() < deadline:
        cur = safe_read_json(q_path, q_obj)
        if cur.get("status") == "ANSWERED" and cur.get("reply") is not None:
            print(f"\n[ORCHESTRATOR_REPLY: {tid}]\n{cur['reply']}", flush=True)
            return 0
        time.sleep(1.5)

    print(f"[WorkerAsk] Timed out after {args.timeout}s waiting for Orchestrator reply on {tid}.", flush=True)
    return 1


def cmd_answer(args: argparse.Namespace) -> int:
    """Allow Primary Orchestrator to reply directly to a waiting CLI worker / subagent."""
    slug, root = resolve_target_project(args.project, args.workspaces)
    off_dir = ensure_offload_dir(slug, root)
    tid = args.task_id
    q_path = off_dir / "comms" / f"{tid}.json"
    reply_text = args.reply or ""
    if args.reply_file:
        rfile = _to_host_path(args.reply_file)
        if not rfile.is_file():
            raise FileNotFoundError(f"Reply file not found: {rfile}")
        reply_text = rfile.read_text(encoding="utf-8")

    with offload_lock(off_dir):
        q_obj = safe_read_json(q_path, {"task_id": tid})
        q_obj["status"] = "ANSWERED"
        q_obj["reply"] = reply_text.strip()
        q_obj["answered_at"] = _now_iso()
        atomic_write_json(q_path, q_obj)

        task_json = off_dir / "tasks" / f"{tid}.json"
        if task_json.is_file():
            task = safe_read_json(task_json)
            task["awaiting_orchestrator"] = False
            atomic_write_json(task_json, task)

        update_presence(
            off_dir, slug, root,
            role="orchestrator",
            state="WAITING_FOR_RESULT",
            note=f"Answered question on {tid}",
            active_expectation=f"Expecting {tid}",
            render_board=True,
        )
    print(f"[OffloadAnswer] Delivered reply to {tid} -> {q_path}")
    return 0


def cmd_worker_complete(args: argparse.Namespace) -> int:
    slug, root = resolve_target_project(args.project, args.workspaces)
    off_dir = ensure_offload_dir(slug, root)
    with offload_lock(off_dir):
        task_json = off_dir / "tasks" / f"{args.task_id}.json"
        if not task_json.is_file():
            raise FileNotFoundError(f"Task not found: {task_json}")

        summary_text = args.summary or ""
        if args.summary_file:
            sfile = _to_host_path(args.summary_file)
            if sfile.is_file():
                summary_text = sfile.read_text(encoding="utf-8")

        artifacts = [a.strip() for a in args.artifacts.split(",") if a.strip()] if args.artifacts else []
        completed_at = _now_iso()

        task = safe_read_json(task_json)
        if task.get("status") != "IN_PROGRESS":
            print("[WorkerComplete] Task is not in progress", file=sys.stderr)
            return 1
        if task.get("claim_id") and task["claim_id"] != args.claim_id:
            print("[WorkerComplete] Claim ID does not match task ownership", file=sys.stderr)
            return 1
        task["status"] = args.status
        task["completed_at"] = completed_at
        task["artifacts"] = artifacts
        task["summary"] = summary_text
        if getattr(args, "error", None):
            task["error"] = args.error.strip()
        atomic_write_json(task_json, task)
        atomic_write_text(off_dir / "tasks" / f"{args.task_id}.md", _format_task_dossier(task, slug, root, off_dir))

        art_md = "\n".join(f"- `{a}`" for a in artifacts) if artifacts else "- _(none specified)_"
        owner_label = task.get("claimed_by") or getattr(args, "agent_id", None) or "worker"
        result_md = f"""# OFFLOAD RESULT DOSSIER: `{args.task_id}`

- **Project**: `{slug}` (`{_to_display_path(root)}`)
- **Title**: {task.get('title')}
- **Completed By**: `{owner_label}`
- **Final Status**: `{args.status}`
- **Completed At**: `{completed_at}`

## Artifacts & Modified Files
{art_md}

## Execution Summary & Verification Output
{summary_text.strip() or "_No detailed summary provided._"}
"""
        result_path = off_dir / "results" / f"RESULT-{args.task_id}.md"
        atomic_write_text(result_path, result_md)

        status_data = _load_status(off_dir, slug, root)
        now_ep = _now_epoch()
        now_str = _now_iso()
        worker = status_data.setdefault("worker", {})
        delegated = [d for d in (worker.get("delegated_tasks") or []) if d != args.task_id]
        worker["delegated_tasks"] = delegated

        eff_agent_id = sanitize_agent_id(args.agent_id) if getattr(args, "agent_id", None) else (task.get("claimed_by") or "")
        agents = status_data.get("agents") or {}
        if eff_agent_id and eff_agent_id in agents and isinstance(agents[eff_agent_id], dict):
            entry = agents[eff_agent_id]
            cur_tasks = [t for t in (entry.get("current_tasks") or []) if t != args.task_id]
            entry["current_tasks"] = cur_tasks
            if str(entry.get("state", "")).upper() == "BUSY_EXECUTING" and not cur_tasks:
                entry["state"] = "OFFLINE"
                entry["pid"] = None
                entry["note"] = f"Finished {args.task_id} ({args.status}); restart the listener"
                entry["last_seen"] = now_str
                entry["last_seen_epoch"] = now_ep
            _sync_legacy_mirrors(status_data, now=now_ep)
        elif worker.get("active_task_id") == args.task_id:
            worker["active_task_id"] = None
            worker["state"] = "OFFLINE"
            worker["pid"] = None
            worker["note"] = f"Finished {args.task_id} ({args.status}); restart the listener"

        status_data["updated_at"] = now_str
        _save_status(off_dir, status_data)
        atomic_write_text(off_dir / "BOARD.md", render_board_markdown(slug, root, off_dir))
    print(f"[WorkerComplete] Recorded {args.status} for {args.task_id} -> {result_path}")
    print(format_status_bar_terminal(slug, root, off_dir))
    return 0


def cmd_skills(args: argparse.Namespace) -> int:
    """Print resolved SKILL.md locations across Project, Universal, and Built-in tiers (Windows + WSL paths)."""
    slug, root = resolve_target_project(args.project, args.workspaces)
    catalog = discover_skill_catalog(root, slug)
    print(f"=== SKILL.MD LOCATIONS FOR '{slug}' ({_to_display_path(root)} | WSL: {_to_wsl_path(root)}) ===")
    for label, key in (
        ("PROJECT-SPECIFIC SKILLS", "project"),
        ("UNIVERSAL SKILLS (Central Brain)", "universal"),
        ("BUILT-IN ANTIGRAVITY SKILLS", "builtin"),
        ("GLOBAL CONFIG SKILLS (~/.gemini/config/skills)", "config"),
    ):
        items = catalog.get(key, [])
        print(f"\n[{label}] ({len(items)})")
        if not items:
            print("  (none)")
        for item in items:
            win_p = _to_display_path(item["path"])
            wsl_p = _to_wsl_path(win_p)
            print(f"  {item['name']:<32} -> {win_p}  (WSL: {wsl_p})")
    return 0


def cmd_worker_offline(args: argparse.Namespace) -> int:
    slug, root = resolve_target_project(args.project, args.workspaces)
    off_dir = ensure_offload_dir(slug, root)
    req_agent_id = sanitize_agent_id(args.agent_id) if getattr(args, "agent_id", None) else ""
    if req_agent_id:
        update_presence(
            off_dir, slug, root,
            role=_infer_role_from_agent_id(req_agent_id, default="worker"),
            state="OFFLINE",
            note=f"{req_agent_id} went offline cleanly",
            active_task_id=None,
            pid=None,
            agent_id=req_agent_id,
            render_board=True,
        )
        print(f"[WorkerOffline] Marked {req_agent_id} OFFLINE on '{slug}'.")
        return 0

    with offload_lock(off_dir):
        status = _load_status(off_dir, slug, root)
        now_ep = _now_epoch()
        now_str = _now_iso()
        for entry in (status.get("agents") or {}).values():
            if isinstance(entry, dict) and normalize_agent_role(entry.get("role")) == "worker":
                entry["state"] = "OFFLINE"
                entry["pid"] = None
                entry["current_tasks"] = []
                entry["note"] = "CLI worker went offline cleanly"
                entry["last_seen"] = now_str
                entry["last_seen_epoch"] = now_ep
        worker = status.setdefault("worker", {})
        worker["state"] = "OFFLINE"
        worker["pid"] = None
        worker["active_task_id"] = None
        worker["note"] = "CLI worker went offline cleanly"
        worker["last_heartbeat_epoch"] = now_ep
        worker["last_heartbeat_iso"] = now_str
        _sync_legacy_mirrors(status, now=now_ep)
        status["updated_at"] = now_str
        _save_status(off_dir, status)
        atomic_write_text(off_dir / "BOARD.md", render_board_markdown(slug, root, off_dir))
    print(f"[WorkerOffline] Marked CLI worker OFFLINE on '{slug}'.")
    return 0


def cmd_collect(args: argparse.Namespace) -> int:
    slug, root = resolve_target_project(args.project, args.workspaces)
    off_dir = ensure_offload_dir(slug, root)

    update_presence(
        off_dir, slug, root,
        role="orchestrator",
        state="ONLINE",
        note=f"Collected result {args.task_id or 'latest'}",
        active_expectation="NONE",
        render_board=True,
    )

    tasks = _load_tasks(off_dir)
    if args.task_id:
        matches = [t for t in tasks if t.get("task_id") == args.task_id]
        if not matches:
            raise FileNotFoundError(f"Task '{args.task_id}' not found in {off_dir / 'tasks'}")
        target = matches[0]
    else:
        closed = [t for t in tasks if t.get("status") in ("COMPLETED", "FAILED")]
        if not closed:
            print(f"[OffloadCollect] No completed tasks yet for '{slug}'.")
            print(format_status_bar_terminal(slug, root, off_dir))
            return 0
        target = closed[0]

    tid = target["task_id"]
    res_path = off_dir / "results" / f"RESULT-{tid}.md"
    print(format_status_bar_terminal(slug, root, off_dir))
    if res_path.is_file():
        print("\n" + res_path.read_text(encoding="utf-8", errors="replace"))
    else:
        print(f"\n[OffloadCollect] Task {tid} is currently `{target.get('status')}` (no RESULT file yet).")
    return 0


def cmd_cancel(args: argparse.Namespace) -> int:
    slug, root = resolve_target_project(args.project, args.workspaces)
    off_dir = ensure_offload_dir(slug, root)
    with offload_lock(off_dir):
        task_json = off_dir / "tasks" / f"{args.task_id}.json"
        if not task_json.is_file():
            raise FileNotFoundError(f"Task not found: {task_json}")
        task = safe_read_json(task_json)
        task["status"] = "CANCELLED"
        task["completed_at"] = _now_iso()
        atomic_write_json(task_json, task)
        atomic_write_text(off_dir / "tasks" / f"{args.task_id}.md", _format_task_dossier(task, slug, root, off_dir))
        atomic_write_text(off_dir / "BOARD.md", render_board_markdown(slug, root, off_dir))
    print(f"[OffloadCancel] Cancelled {args.task_id} on '{slug}'.")
    return 0


def cmd_wait_for_worker(args: argparse.Namespace) -> int:
    """Keep Orchestrator ONLINE and block until a CLI Worker connects on the target board (or any board if --any)."""
    is_implicit_any = bool(args.any and not args.project and not args.workspaces)

    if args.any:
        targets = {
            s: r for s, r in discover_all_targets(include_brain=True).items() if r.exists()
        }
    else:
        slug, root = resolve_target_project(args.project, args.workspaces)
        targets = {slug: root}

    if not is_implicit_any:
        slug, root = resolve_target_project(args.project, args.workspaces)
        off_dir = ensure_offload_dir(slug, root)
        update_presence(
            off_dir, slug, root,
            role="orchestrator",
            state="ONLINE",
            note="Waiting for CLI worker to connect",
            active_expectation="Awaiting CLI Worker Connection",
            render_board=True,
        )
        print(format_status_bar_terminal(slug, root, off_dir), flush=True)

    scope_desc = f"ALL {len(targets)} workspace boards" if args.any else f"'{slug}'"
    print(
        f"[OrchestratorWait] ONLINE and waiting up to {args.timeout}s for CLI Worker on {scope_desc}...",
        flush=True,
    )

    deadline = _now_epoch() + args.timeout
    last_ping = _now_epoch()
    last_render = _now_epoch()

    try:
        while _now_epoch() <= deadline:
            now = _now_epoch()
            for t_slug, t_root in targets.items():
                t_off = t_root / "offload"
                st_file = t_off / "status.json"
                if not st_file.is_file():
                    continue
                status_data = _load_status(t_off, t_slug, t_root)
                pres = _compute_effective_presence(status_data, now=now)
                if pres["worker_is_live"]:
                    ensure_offload_dir(t_slug, t_root)
                    update_presence(
                        t_off, t_slug, t_root,
                        role="orchestrator",
                        state="ONLINE",
                        note="Connected with CLI worker",
                        active_expectation="Ready to Dispatch",
                        render_board=True,
                    )
                    print(f"\n[WORKER_CONNECTED: {t_slug}] CLI Worker is LIVE at {t_root}!", flush=True)
                    print(format_status_bar_terminal(t_slug, t_root, t_off), flush=True)
                    return 0

            if not is_implicit_any and (now - last_ping >= 5.0):
                should_render = (now - last_render) >= 30.0
                update_presence(
                    off_dir, slug, root,
                    role="orchestrator",
                    state="ONLINE",
                    note="Waiting for CLI worker to connect",
                    active_expectation="Awaiting CLI Worker Connection",
                    render_board=should_render,
                )
                last_ping = now
                if should_render:
                    last_render = now

            time.sleep(max(0.2, args.poll_interval))
    except KeyboardInterrupt:
        print("\n[OrchestratorWait] Stopped waiting via KeyboardInterrupt.")
        return 0

    print(f"\n[WAIT_TIMEOUT] No CLI Worker connected within {args.timeout}s.")
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Offload V3 Multi-Agent Roster & Cross-Instance Orchestration Engine"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def _add_target_flags(p: argparse.ArgumentParser) -> None:
        p.add_argument("--project", type=str, default=None, help="Target project name or path (defaults via co-folder disambiguation)")
        p.add_argument("--workspaces", type=str, default=None, help="Semicolon/comma-separated workspace roots to disambiguate co-folders")

    p_init = sub.add_parser("init", help="Provision/refresh offload/ message board folder")
    _add_target_flags(p_init)
    p_init.add_argument("--all", action="store_true", help="Provision across all registered projects plus brain")

    p_join = sub.add_parser("join", help="Join the board roster as main, worker, or collaborator")
    _add_target_flags(p_join)
    p_join.add_argument("--role", choices=["main", "worker", "collaborator"], required=True, help="Agent role")
    p_join.add_argument("--agent-id", default=None, help="Optional pinned agent ID (auto-assigned if omitted)")
    p_join.add_argument("--host", default=None, help="Host identifier (e.g. antigravity, codex, cli)")
    p_join.add_argument("--note", default="", help="Optional presence note")
    p_join.add_argument("--json", action="store_true", help="Print machine-readable JSON assignment")

    p_leave = sub.add_parser("leave", help="Mark an agent OFFLINE and release its active PID")
    _add_target_flags(p_leave)
    p_leave.add_argument("--agent-id", required=True, help="Agent ID to sign off")
    p_leave.add_argument("--note", default="", help="Optional sign-off note")

    p_post = sub.add_parser("post", help="Post a peer collaboration message to messages.jsonl")
    _add_target_flags(p_post)
    p_post.add_argument("--from", dest="from_agent", required=True, help="Sender agent ID")
    p_post.add_argument("--to", dest="to_target", default="all", help="Recipient: all, <agent_id>, or role:<role>")
    p_post.add_argument("--message", required=True, help="Message body text")
    p_post.add_argument("--file", default=None, help="Optional associated file path")

    p_inbox = sub.add_parser("inbox", help="Read peer messages addressed to an agent, role, or all")
    _add_target_flags(p_inbox)
    p_inbox.add_argument("--for", dest="for_agent", default=None, help="Filter messages for this agent ID")
    p_inbox.add_argument("--role", choices=["main", "worker", "collaborator"], default=None, help="Filter messages for this role")
    p_inbox.add_argument("--limit", type=int, default=20, help="Maximum messages to display")
    p_inbox.add_argument("--json", action="store_true", help="Output messages as JSON array")

    p_status = sub.add_parser("status", help="Show live Multi-Agent Roster, status bar, and task queue")
    _add_target_flags(p_status)
    p_status.add_argument("--all", action="store_true", help="Show fleet status table across all workspaces")
    p_status.add_argument("--role", choices=["orchestrator", "main", "worker", "collaborator", "none"], default="orchestrator", help="Update presence timestamp for this role")
    p_status.add_argument("--agent-id", default=None, help="Optional specific agent ID whose presence should be refreshed")

    p_dispatch = sub.add_parser("dispatch", help="Post a new offloaded task with resolved SKILL.md paths")
    _add_target_flags(p_dispatch)
    p_dispatch.add_argument("--title", required=True, help="Concise task title")
    p_dispatch.add_argument("--prompt", default="", help="Task instructions")
    p_dispatch.add_argument("--prompt-file", default=None, help="Path to multi-line task prompt markdown file")
    p_dispatch.add_argument("--from", dest="from_agent", default=None, help="Dispatching agent ID (defaults to main-1)")
    p_dispatch.add_argument("--to", dest="target_agent", default="any", help="Target recipient: any, <agent_id>, or role:<role>")
    p_dispatch.add_argument("--skills", default="", help="Comma-separated skill names or SKILL.md paths (auto-skill always included)")
    p_dispatch.add_argument("--skill-paths", default="", help="Comma-separated explicit SKILL.md file paths (universal, builtin, or project-specific)")
    p_dispatch.add_argument("--mode", choices=["standard", "subagents", "swarm"], default="standard", help="Execution topology for the worker")
    p_dispatch.add_argument("--inline", action="store_true", help="Execute inline in main loop instead of non-blocking background delegation")
    p_dispatch.add_argument("--context", default="", help="Comma-separated context/source file paths to inspect")
    p_dispatch.add_argument("--wait", action="store_true", help="Block and refresh orchestrator heartbeat until task completes")
    p_dispatch.add_argument("--timeout", type=int, default=600, help="Wait timeout in seconds when --wait is enabled")

    p_listen = sub.add_parser("worker-listen", help="Join roster and block until a matching task arrives")
    _add_target_flags(p_listen)
    p_listen.add_argument("--role", choices=["worker", "collaborator"], default="worker", help="Listener role (worker or collaborator)")
    p_listen.add_argument("--agent-id", default=None, help="Optional pinned agent ID (auto-assigned worker-X / collab-X if omitted)")
    p_listen.add_argument("--host", default="cli", help="Host identifier (e.g. cli, codex, antigravity)")
    p_listen.add_argument("--timeout", type=int, default=1800, help="Listen timeout in seconds")
    p_listen.add_argument("--poll-interval", "--poll", dest="poll_interval", type=float, default=2.0, help="Queue poll interval in seconds")
    p_listen.add_argument("--once", action="store_true", help="Check once and return immediately if no matching pending task")

    p_claim = sub.add_parser("worker-claim", help="Manually claim a specific task ID as worker or collaborator")
    _add_target_flags(p_claim)
    p_claim.add_argument("--task-id", required=True, help="TASK-... identifier")
    p_claim.add_argument("--agent-id", default=None, help="Optional claiming agent ID")
    p_claim.add_argument("--role", choices=["worker", "collaborator"], default="worker", help="Claiming role")
    p_claim.add_argument("--host", default=None, help="Optional host identifier")

    p_delegated = sub.add_parser("worker-delegated", help="Mark task delegated to background subagent/swarm and return worker to READY")
    _add_target_flags(p_delegated)
    p_delegated.add_argument("--task-id", required=True, help="TASK-... identifier")
    p_delegated.add_argument("--agent-id", default=None, help="Optional agent ID (inferred from task claimed_by if omitted)")
    p_delegated.add_argument("--subagent-id", default="background-subagent", help="Spawned subagent conversationId or swarm name")
    p_delegated.add_argument("--note", default="", help="Optional status bar note")

    p_complete = sub.add_parser("worker-complete", help="Record the claimed task result without clobbering other live workers")
    _add_target_flags(p_complete)
    p_complete.add_argument("--task-id", required=True, help="TASK-... identifier")
    p_complete.add_argument("--claim-id", help="Ownership ID printed in the claimed task dossier")
    p_complete.add_argument("--agent-id", default=None, help="Optional completing agent ID (inferred from task claimed_by if omitted)")
    p_complete.add_argument("--summary", default="", help="Short completion summary")
    p_complete.add_argument("--summary-file", default=None, help="Path to detailed markdown summary file")
    p_complete.add_argument("--artifacts", default="", help="Comma-separated deliverable/modified paths")
    p_complete.add_argument("--status", choices=["COMPLETED", "FAILED"], default="COMPLETED", help="Final status")
    p_complete.add_argument("--preserve-listening", action="store_true", help="Compatibility option; a live listener remains intact by default")

    p_offline = sub.add_parser("worker-offline", help="Mark worker OFFLINE cleanly")
    _add_target_flags(p_offline)
    p_offline.add_argument("--agent-id", default=None, help="Optional specific agent ID to mark OFFLINE")

    p_collect = sub.add_parser("collect", help="Collect latest or specific task result dossier")
    _add_target_flags(p_collect)
    p_collect.add_argument("--task-id", default=None, help="Specific TASK-... identifier")

    p_cancel = sub.add_parser("cancel", help="Cancel a task cleanly")
    _add_target_flags(p_cancel)
    p_cancel.add_argument("--task-id", required=True, help="TASK-... identifier")

    p_wait_worker = sub.add_parser("wait-for-worker", help="Keep Orchestrator ONLINE and block until a Worker connects")
    _add_target_flags(p_wait_worker)
    p_wait_worker.add_argument("--any", action="store_true", help="Watch all registered workspace boards + brain simultaneously")
    p_wait_worker.add_argument("--timeout", type=int, default=1800, help="Wait timeout in seconds")
    p_wait_worker.add_argument("--poll-interval", "--poll", dest="poll_interval", type=float, default=2.0, help="Poll interval in seconds")

    p_skills = sub.add_parser("skills", help="List available PROJECT, UNIVERSAL, and BUILTIN SKILL.md paths")
    _add_target_flags(p_skills)

    p_wait = sub.add_parser("wait", help="Sleep efficiently until a task completes OR a subagent posts a question")
    _add_target_flags(p_wait)
    p_wait.add_argument("--task-id", default=None, help="Specific TASK-... identifier (defaults to latest active)")
    p_wait.add_argument("--timeout", type=int, default=600, help="Wait timeout in seconds")

    p_ask = sub.add_parser("worker-ask", help="Direct subagent->Orchestrator clarification channel")
    _add_target_flags(p_ask)
    p_ask.add_argument("--task-id", required=True, help="TASK-... identifier")
    p_ask.add_argument("--question", required=True, help="Concise blocker or decision needed")
    p_ask.add_argument("--agent-id", default=None, help="Optional asking worker/collaborator ID")
    p_ask.add_argument("--sender", default="subagent", help="Subagent/worker identifier")
    p_ask.add_argument("--wait", action="store_true", help="Block until Orchestrator posts reply")
    p_ask.add_argument("--timeout", type=int, default=300, help="Reply timeout in seconds")

    p_answer = sub.add_parser("answer", help="Reply to a pending worker-ask question")
    _add_target_flags(p_answer)
    p_answer.add_argument("--task-id", required=True, help="TASK-... identifier")
    p_answer.add_argument("--reply", default="", help="Concise decision text")
    p_answer.add_argument("--reply-file", default=None, help="Optional file with decision text")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    handlers = {
        "init": cmd_init,
        "join": cmd_join,
        "leave": cmd_leave,
        "post": cmd_post,
        "inbox": cmd_inbox,
        "status": cmd_status,
        "dispatch": cmd_dispatch,
        "worker-listen": cmd_worker_listen,
        "worker-claim": cmd_worker_claim,
        "worker-delegated": cmd_worker_delegated,
        "worker-ask": cmd_worker_ask,
        "worker-complete": cmd_worker_complete,
        "worker-offline": cmd_worker_offline,
        "collect": cmd_collect,
        "cancel": cmd_cancel,
        "wait": cmd_wait,
        "answer": cmd_answer,
        "wait-for-worker": cmd_wait_for_worker,
        "skills": cmd_skills,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
