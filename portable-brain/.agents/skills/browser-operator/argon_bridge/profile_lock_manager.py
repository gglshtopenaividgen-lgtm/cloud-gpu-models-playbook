#!/usr/bin/env python3
"""profile_lock_manager.py - Dynamic Profile Lease & Shared Fleet Observability.

Enforces:
1. Full visibility across all 6 Google One AI Premium profiles for every agent and subagent.
2. Real-time lease tracking: who is using what, current task, elapsed time, and lease remaining.
3. Live usage telemetry (5-hour usage %, weekly %, reset times) so agents can autonomously
   select or switch to profiles with lower usage.
4. Autonomous non-colliding routing: if a requested profile is busy, routes to the optimal idle profile.
5. Strictly enforces exactly 1 Gemini tab per profile window to conserve RAM on low-memory systems (~3GB free).
6. Auto-expires stale locks (>120s) if an agent terminates unexpectedly.
"""

from __future__ import annotations

import ctypes
import json
import math
import os
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent))
import profile_manager

LOCKS_FILE = Path(__file__).parent / "bridge_profile_locks.json"
LOCKS_LOCK_FILE = Path(__file__).parent / "bridge_profile_locks.json.lock"
SESSIONS_FILE = Path(__file__).parent / "bridge_sessions_map.json"
FLOW_STATE_FILE = Path(__file__).parent / "bridge_flow_state.json"
FLOW_REGISTRY_FILE = Path(__file__).parents[2] / "external-resource" / "references" / "flow_tool_registry.json"
FLOW_SURFACE = "flow"
LEGACY_FLOW_GLOBAL_LOCK = "flow_global"
QUOTA_BUCKETS = ("aistudio_argon", "aistudio_neon", "gemini_web_neon", "notebooklm")

try:
    from filelock import FileLock, Timeout as FileLockTimeout
    HAS_FILELOCK = True
except ImportError:
    HAS_FILELOCK = False
    FileLock = None
    FileLockTimeout = None


@contextmanager
def profile_lock_context(timeout: float = 10.0):
    """Process-safe file lock around bridge_profile_locks.json to eliminate Windows NTFS race conditions."""
    if HAS_FILELOCK and FileLock is not None:
        lock = FileLock(str(LOCKS_LOCK_FILE), timeout=timeout)
        with lock:
            yield
    else:
        # Atomic fallback file lock
        start = time.time()
        acquired = False
        fallback = Path(str(LOCKS_LOCK_FILE) + ".fallback")
        while time.time() - start < timeout:
            try:
                fd = os.open(str(fallback), os.O_CREAT | os.O_EXCL | os.O_RDWR)
                os.close(fd)
                acquired = True
                break
            except (FileExistsError, OSError):
                time.sleep(0.05)
        if not acquired:
            raise TimeoutError("Timed out acquiring the Chrome profile lease file lock")
        try:
            yield
        finally:
            if acquired and fallback.exists():
                try:
                    fallback.unlink()
                except Exception:
                    pass


PRIMARY_WATSAPP_1 = "Profile 14"  # agent5@example.com
PRIMARY_WATSAPP_2 = "Profile 13"  # agent6@example.com
FAILSAFE_ORDER = ["Profile 7", "Profile 9", "Profile 16", "Profile 8"]
DEFAULT_TIMEOUT_SEC = 300.0  # 5 minutes default lease
DEEP_RESEARCH_TIMEOUT_SEC = 900.0  # 15 minutes lease for deep research runs
EVICTION_SURFACE = "__eviction__"


def _load_flow_state() -> Dict[str, Any]:
    if not FLOW_STATE_FILE.exists():
        return {}
    state = json.loads(FLOW_STATE_FILE.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise ValueError("Invalid Flow state ledger")
    return state


def _save_flow_state(state: Dict[str, Any]) -> None:
    pending = FLOW_STATE_FILE.with_suffix(".json.tmp")
    pending.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(pending, FLOW_STATE_FILE)


def _flow_deadline(seconds: float) -> float:
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("Flow lease or cooldown duration must be finite and positive")
    return time.time() + seconds


def acquire_flow_lock(agent_id: str, profile: str, lease_seconds: float = DEFAULT_TIMEOUT_SEC) -> Optional[str]:
    """Reserve one Flow tab on an enabled manager profile within shared bridge capacity."""
    if not agent_id:
        raise ValueError("Flow lease owner is required")
    if profile not in _flow_profiles():
        return None
    resources = _get_bridge_resources_json()
    if not resources.get("ok"):
        return None
    with profile_lock_context():
        state = _load_flow_state()
        if LEGACY_FLOW_GLOBAL_LOCK in state:
            if state[LEGACY_FLOW_GLOBAL_LOCK]["expires_at"] > time.time():
                return None
            del state[LEGACY_FLOW_GLOBAL_LOCK]
            _save_flow_state(state)

        locks = _load_active_locks()
        key = _lock_key(profile, FLOW_SURFACE)
        if _find_active_lock(locks, profile, surface=FLOW_SURFACE) or _lock_key(profile, EVICTION_SURFACE) in locks:
            return None
        active_profiles = set(resources["active_agent_profiles"]) | set(resources.get("pending_profiles", []))
        active_profiles.update(info.get("profile") or name.split("::", 1)[0] for name, info in locks.items())
        if profile not in active_profiles and len(active_profiles) >= min(3, resources["max_agent_profiles"]):
            return None

        owned = resources.get("owned_tabs", {})
        active_flows = {info["profile"] for info in locks.values() if info.get("surface") == FLOW_SURFACE}
        already_open = {name for name, tabs in owned.items() if any(tab.get("surface") == FLOW_SURFACE for tab in tabs.values())}
        if profile in already_open:
            return None  # A timed-out owner may have left a tab. Reconcile it first.
        tabs = resources["active_agent_tabs"] + resources.get("pending_tabs", 0) + len(active_flows - already_open)
        if tabs >= min(6, resources["max_agent_tabs"]):
            return None

        token = uuid.uuid4().hex
        locks[key] = {
            "profile": profile, "surface": FLOW_SURFACE, "task": "flow", "agent_id": agent_id,
            "pid": os.getpid(), "token": token, "expires_at": _flow_deadline(lease_seconds),
        }
        _save_locks(locks)
        return token


def renew_flow_lock(agent_id: str, profile: str, token: str, lease_seconds: float = DEFAULT_TIMEOUT_SEC) -> bool:
    """Extend a current lease while its Flow work is still running."""
    with profile_lock_context():
        locks = _load_active_locks()
        lease = locks.get(_lock_key(profile, FLOW_SURFACE))
        if not token or not lease or lease["agent_id"] != agent_id or lease.get("token") != token:
            return False
        lease["expires_at"] = _flow_deadline(lease_seconds)
        _save_locks(locks)
        return True


def release_flow_lock(agent_id: str, profile: str, token: str) -> bool:
    """Release only the matching lease generation after the Flow tab has closed."""
    with profile_lock_context():
        locks = _load_active_locks()
        key = _lock_key(profile, FLOW_SURFACE)
        lease = locks.get(key)
        if not token or not lease or lease["agent_id"] != agent_id or lease.get("token") != token:
            return False
        del locks[key]
        _save_locks(locks)
        return True


def _flow_profiles() -> Dict[str, Any]:
    registry = json.loads(FLOW_REGISTRY_FILE.read_text(encoding="utf-8"))
    return {
        profile: info for profile, info in registry["profiles"].items()
        if info.get("enabled") is True and info.get("role") == "pro_manager"
    }


def mark_flow_video_depleted(profile: str, cooldown_seconds: float = 1800.0, *, reason: str = "credits_depleted") -> None:
    """Record the observed video cooldown for one enabled manager profile."""
    if profile not in _flow_profiles():
        raise ValueError(f"Flow profile is not an enabled Pro Manager: {profile!r}")
    key = f"profile:{profile}"
    with profile_lock_context():
        state = _load_flow_state()
        cooldowns = state.setdefault("flow_video_depleted", {})
        previous = cooldowns.get(key, {}).get("until", 0)
        cooldowns[key] = {"until": max(previous, _flow_deadline(cooldown_seconds)), "reason": reason}
        _save_flow_state(state)


def pick_flow_profile(modality: Literal["image", "video"] = "image", *, open_profiles: Optional[set[str]] = None) -> Optional[str]:
    """Choose a Flow candidate from the current Pro fleet without opening a profile."""
    if modality not in ("image", "video"):
        raise ValueError(f"Unsupported Flow modality: {modality!r}")
    metadata = _flow_profiles()
    with profile_lock_context():
        cooldowns = _load_flow_state().get("flow_video_depleted", {})
        locks = _load_active_locks()
    now = time.time()
    candidates = []
    for p in profile_manager.get_ai_premium_profiles():
        if p.dir_name not in metadata or not p.has_bridge_extension or p.cooldown_until > now:
            continue
        if _find_active_lock(locks, p.dir_name, surface=FLOW_SURFACE) or _lock_key(p.dir_name, EVICTION_SURFACE) in locks:
            continue
        if modality == "video" and cooldowns.get(f"profile:{p.dir_name}", {}).get("until", 0) > now:
            continue
        candidates.append(p)

    if modality == "image" and open_profiles is None:
        connected_profiles = _get_connected_profiles()
        open_profiles = {p.dir_name for p in candidates if p.dir_name in connected_profiles and _is_profile_truly_open(p.dir_name)}
    open_profiles = open_profiles or set()

    def priority(p: profile_manager.ChromeProfile) -> tuple:
        data = metadata.get(p.dir_name, {})
        is_daily = p.is_daily_driver or data.get("tier") == "daily_driver"
        image_reuse = modality == "image" and p.dir_name in open_profiles
        return is_daily, not image_reuse, data.get("priority", 100), p.dir_name

    selected = min(candidates, key=priority, default=None)
    return selected.dir_name if selected else None


def get_fleet_order() -> List[str]:
    """Dynamically builds the AI Pro fleet list from Local State (Tier 1 Alts first, Daily Drivers last)."""
    try:
        profs = profile_manager.get_ai_premium_profiles()
        tier1 = [p.dir_name for p in profs if not p.is_daily_driver]
        tier2 = [p.dir_name for p in profs if p.is_daily_driver]
        # Keep Profile 14 / Profile 13 near the top of Tier 1 if present
        ordered_t1: List[str] = []
        for pref in (PRIMARY_WATSAPP_1, PRIMARY_WATSAPP_2):
            if pref in tier1:
                ordered_t1.append(pref)
        for d in tier1:
            if d not in ordered_t1:
                ordered_t1.append(d)
        return ordered_t1 + tier2
    except Exception:
        return [PRIMARY_WATSAPP_1, PRIMARY_WATSAPP_2, *FAILSAFE_ORDER]


FLEET_ORDER = get_fleet_order()


def _lock_key(profile: str, surface: Optional[str] = None) -> str:
    return f"{profile}::{surface}" if surface else profile


def _is_pid_alive(pid: Any) -> bool:
    """Returns True if process ID is still running (or cannot be queried safely)."""
    if not isinstance(pid, int) or pid <= 0:
        return True
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    try:
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        k32 = ctypes.windll.kernel32
        handle = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong(0)
            if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == STILL_ACTIVE
        finally:
            k32.CloseHandle(handle)
    except Exception:
        return True


def _read_json(path: Path) -> Dict[str, Any]:
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[ProfileLock] Warning saving {path.name}: {e}", file=sys.stderr)


def _load_active_locks() -> Dict[str, Any]:
    """Read and prune the lease ledger while the caller holds its file lock."""
    now = time.time()
    if not LOCKS_FILE.exists():
        return {}
    locks = json.loads(LOCKS_FILE.read_text(encoding="utf-8"))
    if not isinstance(locks, dict):
        raise ValueError("Invalid Chrome profile lease ledger")
    active = {}
    for prof_key, info in locks.items():
        if not isinstance(info, dict):
            raise ValueError("Invalid Chrome profile lease entry")
        exp = info.get("expires_at", 0)
        pid = info.get("pid")
        if exp > now and _is_pid_alive(pid):
            active[prof_key] = info
    if active != locks:
        _save_locks(active)
    return active


def _save_locks(locks: Dict[str, Any]) -> None:
    pending = LOCKS_FILE.with_suffix(".json.tmp")
    pending.write_text(json.dumps(locks, indent=2), encoding="utf-8")
    os.replace(pending, LOCKS_FILE)


def _read_locks() -> Dict[str, Any]:
    with profile_lock_context():
        return _load_active_locks()


def _write_locks(locks: Dict[str, Any]) -> None:
    with profile_lock_context():
        _save_locks(locks)


def clean_expired_locks() -> Dict[str, Any]:
    """Purges expired or dead-PID leases and returns active locks."""
    return {key: info for key, info in _read_locks().items() if info.get("surface") != EVICTION_SURFACE}


def is_profile_evicting(profile: str) -> bool:
    with profile_lock_context():
        return _lock_key(profile, EVICTION_SURFACE) in _load_active_locks()


@contextmanager
def idle_profile_eviction(profile: str):
    """Prevent new profile leases until an already-idle profile has been closed."""
    key = _lock_key(profile, EVICTION_SURFACE)
    with profile_lock_context():
        locks = _load_active_locks()
        acquired = _find_active_lock(locks, profile) is None
        if acquired:
            locks[key] = {
                "profile": profile,
                "surface": EVICTION_SURFACE,
                "pid": os.getpid(),
                "expires_at": time.time() + DEFAULT_TIMEOUT_SEC,
            }
            _save_locks(locks)
    try:
        yield acquired
    finally:
        if acquired:
            with profile_lock_context():
                locks = _load_active_locks()
                if locks.get(key, {}).get("pid") == os.getpid():
                    del locks[key]
                    _save_locks(locks)


def mark_bucket_cooldown(profile: str, bucket: str, cooldown_seconds: int = 1800, reason: str = "") -> None:
    """Marks one independent quota bucket (e.g. 'aistudio_argon', 'gemini_web_neon') in cooldown."""
    state = profile_manager.load_quota_state()
    p_state = state.setdefault(profile, {})
    buckets = p_state.setdefault("buckets", {})
    now = time.time()
    buckets[bucket] = {
        "cooldown_until": now + max(1, int(cooldown_seconds)),
        "reason": reason or "quota_exhausted",
        "updated_at": now,
    }
    profile_manager.save_quota_state(state)
    print(f"[ProfileLock] Bucket '{bucket}' on '{profile}' marked COOLDOWN for {cooldown_seconds}s ({reason or 'quota'}).")


def is_bucket_available(profile: str, bucket: Optional[str] = None) -> bool:
    """Checks global cooldown, NEEDS_REAUTH, and per-bucket cooldown for a profile."""
    state = profile_manager.load_quota_state()
    p_state = state.get(profile, {})
    now = time.time()
    if p_state.get("cooldown_until", 0.0) > now:
        return False
    reauth = p_state.get("needs_reauth", {})
    if isinstance(reauth, dict) and any(v for v in reauth.values()):
        # Surface-specific reauth check
        surf_map = {"aistudio_argon": "aistudio", "aistudio_neon": "aistudio", "gemini_web_neon": "gemini_web", "notebooklm": "notebook"}
        surf = surf_map.get(bucket or "")
        if surf and reauth.get(surf):
            return False
    if bucket:
        b_info = p_state.get("buckets", {}).get(bucket, {})
        if isinstance(b_info, dict) and b_info.get("cooldown_until", 0.0) > now:
            return False
    return True


def mark_profile_needs_reauth(profile: str, surface: str) -> None:
    """Flags a profile as requiring manual sign-in on the specified surface."""
    state = profile_manager.load_quota_state()
    p_state = state.setdefault(profile, {})
    reauth = p_state.setdefault("needs_reauth", {})
    reauth[surface] = time.time()
    profile_manager.save_quota_state(state)
    print(f"[ProfileLock] Profile '{profile}' flagged NEEDS_REAUTH on surface '{surface}'.")


def clear_needs_reauth(profile: str, surface: Optional[str] = None) -> None:
    """Clears NEEDS_REAUTH flag for a surface (or all surfaces)."""
    state = profile_manager.load_quota_state()
    p_state = state.get(profile, {})
    reauth = p_state.get("needs_reauth")
    if isinstance(reauth, dict):
        if surface:
            reauth.pop(surface, None)
        else:
            p_state["needs_reauth"] = {}
        profile_manager.save_quota_state(state)


def _find_active_lock(active_locks: Dict[str, Any], profile: str, surface: Optional[str] = None) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Finds any conflicting active lock for (profile, surface)."""
    if surface:
        scoped_k = _lock_key(profile, surface)
        if scoped_k in active_locks:
            return scoped_k, active_locks[scoped_k]
        if profile in active_locks:
            return profile, active_locks[profile]
        return None
    # Unscoped callers respect either bare profile lock or any surface lock on that profile
    if profile in active_locks:
        return profile, active_locks[profile]
    prefix = f"{profile}::"
    for k, v in active_locks.items():
        if k.startswith(prefix):
            return k, v
    return None


def get_live_profile_status() -> Dict[str, Any]:
    """Returns full observability status across all discovered AI Pro profiles, buckets, and leases."""
    active_locks = clean_expired_locks()
    profiles_meta: Dict[str, Dict[str, Any]] = {}
    quota_state: Dict[str, Any] = {}
    try:
        for p in profile_manager.get_all_profiles():
            profiles_meta[p.dir_name] = {
                "name": p.name,
                "email": p.email,
                "is_ai_premium": p.is_ai_premium,
                "is_daily_driver": p.is_daily_driver,
                "has_bridge_extension": p.has_bridge_extension,
                "status": p.status,
                "cooldown_until": p.cooldown_until,
            }
        quota_state = profile_manager.load_quota_state()
    except Exception:
        pass

    status: Dict[str, Any] = {}
    now = time.time()
    for prof in get_fleet_order():
        lock_match = _find_active_lock(active_locks, prof)
        lock = lock_match[1] if lock_match else None
        p_meta = profiles_meta.get(prof, {})
        q_meta = quota_state.get(prof, {})

        cooldown_until = p_meta.get("cooldown_until", 0.0)
        is_cooldown = cooldown_until > now

        if lock:
            prof_status = "BUSY"
            elapsed = round(now - lock.get("locked_at", now), 1)
            remaining = round(lock.get("expires_at", now) - now, 1)
            holder = lock.get("agent_id", "unknown")
            task = lock.get("task", "processing")
            tab_id = lock.get("tab_id")
            session_id = lock.get("session_id")
        elif is_cooldown:
            prof_status = "COOLDOWN"
            elapsed = None
            remaining = round(cooldown_until - now, 1)
            holder = None
            task = f"Rate limited (resets in {int(remaining)}s)"
            tab_id = None
            session_id = None
        else:
            prof_status = "IDLE"
            elapsed = None
            remaining = None
            holder = None
            task = None
            tab_id = None
            session_id = None

        status[prof] = {
            "profile": prof,
            "name": p_meta.get("name", prof),
            "email": p_meta.get("email", ""),
            "tier_bucket": "TIER_2_DAILY_DRIVER" if p_meta.get("is_daily_driver") else "TIER_1_ALT_PRO",
            "is_daily_driver": bool(p_meta.get("is_daily_driver")),
            "has_bridge_extension": bool(p_meta.get("has_bridge_extension")),
            "status": prof_status,
            "holder": holder,
            "task": task,
            "elapsed_seconds": elapsed,
            "remaining_seconds": max(0, remaining) if remaining is not None else None,
            "tab_id": tab_id,
            "session_id": session_id,
            "buckets": q_meta.get("buckets", {}),
            "needs_reauth": q_meta.get("needs_reauth", {}),
            "current_usage_percent": q_meta.get("current_usage_percent"),
            "weekly_usage_percent": q_meta.get("weekly_usage_percent"),
            "current_reset": q_meta.get("current_reset"),
            "weekly_reset": q_meta.get("weekly_reset"),
            "last_used": q_meta.get("last_used", 0.0),
        }
    return status


def is_bridge_running(timeout: float = 2.5) -> bool:
    """Checks if the local Argon Bridge daemon is running and reachable on port 9229 (/health -> /status)."""
    import urllib.request
    import urllib.error

    for endpoint in ("/health", "/status"):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:9229{endpoint}", timeout=timeout) as response:
                if response.status == 200:
                    return True
        except OSError:
            continue
    return False


def ensure_bridge_running(timeout: float = 2.5) -> bool:
    """Wait for a restarting bridge before considering an interactive auto-start."""

    def wait_for_bridge(seconds: float) -> bool:
        deadline = time.monotonic() + max(seconds, 0.0)
        while True:
            remaining = deadline - time.monotonic()
            if is_bridge_running(timeout=max(0.05, min(0.25, remaining / 2))):
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(0.5, remaining))

    if wait_for_bridge(timeout):
        return True
    if sys.platform == "win32" and os.environ.get("AGY_ALLOW_HEADLESS_BRIDGE") != "1":
        from profile_rotator import _get_current_desktop_name

        desktop = _get_current_desktop_name()
        if desktop.lower() != "default":
            print(
                f"[ProfileLock] Refusing to start non-interactive bridge daemon in WinSta0\\{desktop}. "
                "Start Start_Gemini_Session.bat on Desktop.",
                file=sys.stderr,
            )
            return False

    try:
        import subprocess

        server_path = Path(__file__).parent / "server.py"
        if server_path.is_file():
            subprocess.Popen(
                [sys.executable, str(server_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if wait_for_bridge(timeout):
                print("[ProfileLock] Auto-started Argon Bridge daemon (127.0.0.1:9229).")
                return True
    except OSError as exc:
        print(f"[ProfileLock] Note: bridge auto-start: {exc}", file=sys.stderr)
    return False


def ping_profile(profile: str, timeout: float = 1.5) -> bool:
    """Queries server.py's /ping_profile?profile=<candidate> to verify live WebSocket responsiveness."""
    try:
        import urllib.request
        import urllib.parse
        url = f"http://127.0.0.1:9229/ping_profile?{urllib.parse.urlencode({'profile': profile})}"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return bool(data.get("ok") and data.get("connected"))
    except Exception:
        pass
    return False


def _get_bridge_status_json() -> Dict[str, Any]:
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:9229/status", timeout=3.0) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {}


def _get_bridge_resources_json(reconcile: bool = False) -> Dict[str, Any]:
    try:
        import urllib.request

        url = "http://127.0.0.1:9229/resources"
        if reconcile:
            url += "?reconcile=1"
        with urllib.request.urlopen(url, timeout=12.0 if reconcile else 3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _cleanup_idle_bridge_resources() -> None:
    """Ask the interactive bridge to reclaim only safe idle agent resources."""
    import urllib.request

    request = urllib.request.Request(
        "http://127.0.0.1:9229/cleanup/idle",
        data=b'{"idle_seconds": 0}',
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20.0):
            pass
    except OSError as exc:
        print(f"[ProfileLock] Idle cleanup unavailable: {exc}", file=sys.stderr)


def _is_profile_truly_open(profile: str) -> bool:
    """Verifies via LIST_TABS (not stale REGISTER tabs_count) whether profile has >= 1 open window tab."""
    try:
        import urllib.request
        req = urllib.request.Request(
            "http://127.0.0.1:9229/command",
            data=json.dumps({"action": "LIST_TABS", "profile": profile, "params": {}, "timeout": 4.0}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return bool(data.get("ok") and isinstance(data.get("tabs"), list) and len(data["tabs"]) > 0)
    except Exception:
        return False


def launch_profile_candidate(profile: str, max_open: int = 3, auto_close_idle: bool = True) -> bool:
    """Attempts to launch a Chrome profile via interactive /profile/open host endpoint first, then /launch."""
    import urllib.request
    status_data = _get_bridge_status_json()
    if status_data.get("interactive_desktop"):
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:9229/profile/open",
                data=json.dumps({"profile": profile, "max_open": max_open, "auto_close_idle": auto_close_idle, "timeout": 15.0}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=22.0) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                if res.get("ok"):
                    return True
        except Exception as e:
            print(f"[ProfileLock] Note /profile/open for '{profile}': {e}", file=sys.stderr)
        return False

    try:
        req = urllib.request.Request(
            "http://127.0.0.1:9229/launch",
            data=json.dumps({"profile": profile}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            if resp.status == 200 and json.loads(resp.read().decode("utf-8")).get("ok"):
                return True
    except Exception:
        pass
    return False


def _get_connected_profiles() -> set:
    """Queries local bridge /status to identify which Chrome profiles have live connected extensions."""
    data = _get_bridge_status_json()
    return {c.get("dir_name") for c in data.get("connected_extensions", []) if c.get("dir_name")}


def pick_optimal_idle_profile(
    preferred_order: Optional[List[str]] = None,
    surface: Optional[str] = None,
    bucket: Optional[str] = None,
    max_open: int = 3,
    *,
    allow_daily_driver: bool = False,
    explicit_preferred: Optional[str] = None,
) -> Optional[str]:
    """Drain Tier 1 first, allowing Tier 2 for exhausted fleet or explicit opt-in."""
    if not ensure_bridge_running():
        return None
    max_open = max(1, min(int(max_open or 3), 3))

    def refresh():
        resources = _get_bridge_resources_json(reconcile=True)
        bridge = _get_bridge_status_json()
        connected = {item["dir_name"] for item in bridge.get("connected_extensions", []) if item.get("dir_name")}
        return (
            clean_expired_locks(),
            get_live_profile_status(),
            set(resources.get("active_agent_profiles") or []),
            min(max_open, int(resources.get("max_agent_profiles") or max_open)),
            {profile for profile in connected if _is_profile_truly_open(profile)},
            bool(bridge.get("interactive_desktop")),
        )

    active_locks, status_map, active_agent_profiles, max_agent_profiles, open_set, interactive_host = refresh()
    base_order = preferred_order or get_fleet_order()
    tier1_order: List[str] = []
    tier2_order: List[str] = []
    for prof in base_order:
        info = status_map.get(prof, {})
        if info.get("is_daily_driver"):
            tier2_order.append(prof)
        else:
            tier1_order.append(prof)

    def _is_candidate_eligible(prof: str) -> Tuple[bool, str]:
        if _find_active_lock(active_locks, prof, surface=surface):
            return False, "locked"
        if not is_bucket_available(prof, bucket=bucket):
            return False, f"bucket_cooldown({bucket or 'global'})"
        info = status_map.get(prof, {})
        usage_pct = info.get("current_usage_percent")
        if usage_pct is not None and usage_pct >= 95:
            return False, f"quota_95%({usage_pct}%)"
        return True, "ok"

    def _try_tier(candidates: List[str], is_daily_tier: bool) -> Optional[str]:
        # Prefer already-open profiles ALREADY in active_agent_profiles -> other already-open profiles -> closed
        open_agent_first = [p for p in candidates if p in open_set and p in active_agent_profiles]
        open_other = [p for p in candidates if p in open_set and p not in active_agent_profiles]
        closed_cands = [p for p in candidates if p not in open_set]
        ordered = open_agent_first + open_other + closed_cands
        if explicit_preferred in ordered:
            ordered.remove(explicit_preferred)
            ordered.insert(0, explicit_preferred)

        for prof in ordered:
            ok, _ = _is_candidate_eligible(prof)
            if not ok:
                continue
            # Never exceed MAX_AGENT_PROFILES (3) by expanding onto a 4th distinct profile
            if len(active_agent_profiles) >= max_agent_profiles and prof not in active_agent_profiles:
                continue
            tier_tag = "[LAST_RESORT_DAILY_DRIVER]" if is_daily_tier else "[Tier1-Alt]"
            if prof in open_set and ping_profile(prof):
                print(f"[ProfileLock] {tier_tag} Waterfall Drain selected open profile '{prof}'.")
                return prof
            if interactive_host:
                if launch_profile_candidate(prof, max_open=max_open, auto_close_idle=True):
                    t0 = time.time()
                    while time.time() - t0 < 8.0:
                        if ping_profile(prof):
                            print(f"[ProfileLock] {tier_tag} Launched & verified '{prof}'.")
                            return prof
                        time.sleep(0.5)
        return None

    def tier1_has_quota() -> bool:
        return any(
            info.get("has_bridge_extension")
            and not info.get("is_daily_driver")
            and (info.get("current_usage_percent") or 0) < 95
            and is_bucket_available(prof, bucket=bucket)
            for prof, info in status_map.items()
        )

    chosen = _try_tier(tier1_order, is_daily_tier=False)
    if chosen:
        return chosen

    any_tier1_has_quota = tier1_has_quota()
    if any_tier1_has_quota and interactive_host:
        _cleanup_idle_bridge_resources()
        active_locks, status_map, active_agent_profiles, max_agent_profiles, open_set, interactive_host = refresh()
        chosen = _try_tier(tier1_order, is_daily_tier=False)
        if chosen:
            return chosen
        any_tier1_has_quota = tier1_has_quota()

    daily_driver_allowed = allow_daily_driver or explicit_preferred in tier2_order
    if any_tier1_has_quota and not daily_driver_allowed:
        if not interactive_host:
            detail = "Start Start_Gemini_Session.bat on Desktop to open a Tier-1 profile."
        elif len(active_agent_profiles) >= max_agent_profiles:
            detail = "Agent profile capacity is full after idle cleanup."
        else:
            detail = "Tier-1 launches were unavailable; check active leases and bridge connections."
        print(f"[TIER1_ROTATION_NEEDED] Tier-1 Alts still have quota. {detail}", file=sys.stderr)
        return None

    chosen_daily = _try_tier(tier2_order, is_daily_tier=True)
    if chosen_daily:
        reason = "Daily Driver explicitly allowed" if any_tier1_has_quota else "No bridged Tier-1 Alt has quota"
        print(f"[LAST_RESORT_DAILY_DRIVER] {reason}; selected '{chosen_daily}'.", file=sys.stderr)
        return chosen_daily

    print("[ProfileLock] All AI Pro profiles exhausted, busy, or offline.")
    return None


def renew_profile_lease(profile: str, agent_id: str, extend_seconds: float = 180.0, surface: Optional[str] = None) -> bool:
    """Heartbeat: extends the lease on a profile/surface while generation is actively proceeding."""
    with profile_lock_context():
        locks = _load_active_locks()
        match = _find_active_lock(locks, profile, surface=surface)
        if match and match[1].get("surface") != FLOW_SURFACE and match[1].get("agent_id") == agent_id:
            match[1]["expires_at"] = time.time() + extend_seconds
            _save_locks(locks)
            return True
    return False


def acquire_profile_lease(
    agent_id: str,
    preferred_profile: Optional[str] = None,
    task: str = "cognition",
    session_id: Optional[str] = None,
    deep_research: bool = False,
    tab_id: Optional[int] = None,
    lease_seconds: Optional[float] = None,
    surface: Optional[str] = None,
    bucket: Optional[str] = None,
    max_open: int = 3,
    *,
    allow_daily_driver: bool = False,
) -> Tuple[Optional[str], Optional[str]]:
    """Acquires a surface-scoped profile lease using 11-profile Waterfall Drain & 4-bucket quota state."""
    if surface == FLOW_SURFACE:
        return None, "Use acquire_flow_lock for Flow leases."
    now = time.time()
    ttl = lease_seconds or (DEEP_RESEARCH_TIMEOUT_SEC if deep_research else DEFAULT_TIMEOUT_SEC)
    active_locks = clean_expired_locks()
    sessions = _read_json(SESSIONS_FILE)

    target_prof = None

    if session_id and session_id in sessions:
        bound_prof = sessions[session_id].get("profile")
        if bound_prof:
            match = _find_active_lock(active_locks, bound_prof, surface=surface)
            if (not match or match[1].get("agent_id") == agent_id) and is_bucket_available(bound_prof, bucket=bucket):
                target_prof = bound_prof

    if not target_prof:
        pref_order = None
        if preferred_profile:
            pref_order = [preferred_profile] + [p for p in get_fleet_order() if p != preferred_profile]
        target_prof = pick_optimal_idle_profile(
            preferred_order=pref_order, surface=surface, bucket=bucket, max_open=max_open,
            explicit_preferred=preferred_profile, allow_daily_driver=allow_daily_driver,
        )

    if not target_prof:
        return None, f"All AI Pro profiles are offline, busy, or exhausted on bucket '{bucket or 'default'}'."

    with profile_lock_context():
        active_locks = _load_active_locks()
        if _lock_key(target_prof, EVICTION_SURFACE) in active_locks:
            return None, f"Profile '{target_prof}' is being closed."
        same_profile = {
            key: info for key, info in active_locks.items()
            if (info.get("profile") or key.split("::", 1)[0]) == target_prof
        }
        relevant_locks = (
            [info for key, info in same_profile.items() if key in (target_prof, _lock_key(target_prof, surface))]
            if surface else same_profile.values()
        )
        if any(info.get("agent_id") != agent_id for info in relevant_locks):
            return None, f"Profile '{target_prof}' became busy while it was being selected."
        leased_profiles = {info.get("profile") or key.split("::", 1)[0] for key, info in active_locks.items()}
        if target_prof not in leased_profiles and len(leased_profiles) >= max(1, min(int(max_open or 3), 3)):
            return None, "Chrome agent profile lease capacity reached."
        now = time.time()
        active_locks[_lock_key(target_prof, surface=surface)] = {
            "profile": target_prof,
            "surface": surface or "all",
            "bucket": bucket or "default",
            "agent_id": agent_id,
            "pid": os.getpid(),
            "task": task,
            "session_id": session_id,
            "tab_id": tab_id,
            "locked_at": now,
            "expires_at": now + ttl,
        }
        _save_locks(active_locks)

        if session_id:
            sessions = _read_json(SESSIONS_FILE)
            sessions[session_id] = {"profile": target_prof, "agent_id": agent_id, "last_active": now}
            _write_json(SESSIONS_FILE, sessions)

    return target_prof, None


def release_profile_lease(profile: str, agent_id: Optional[str] = None, surface: Optional[str] = None) -> bool:
    """Releases the surface-scoped (or legacy unscoped) lock on a profile."""
    with profile_lock_context():
        active_locks = _load_active_locks()
        key = _lock_key(profile, surface=surface)
        target_key = key if key in active_locks else (profile if profile in active_locks else None)
        if not target_key:
            return True
        current_holder = active_locks[target_key].get("agent_id")
        if active_locks[target_key].get("surface") == FLOW_SURFACE:
            return False
        if agent_id and current_holder != agent_id:
            return False
        del active_locks[target_key]
        _save_locks(active_locks)
        print(f"[ProfileLock] Released lease '{target_key}' (now IDLE).")
        return True
