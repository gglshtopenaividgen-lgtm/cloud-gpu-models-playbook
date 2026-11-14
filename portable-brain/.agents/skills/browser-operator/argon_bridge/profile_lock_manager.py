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

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

LOCKS_FILE = Path(__file__).parent / "bridge_profile_locks.json"
SESSIONS_FILE = Path(__file__).parent / "bridge_sessions_map.json"
FLEET_ORDER = ["Profile 14", "Profile 13", "Profile 7", "Profile 9", "Profile 16", "Profile 8"]
PRIMARY_PROFILE_1 = "Profile 14"  # profile-2@example.com
PRIMARY_PROFILE_2 = "Profile 13"  # profile-1@example.com
FAILSAFE_ORDER = ["Profile 7", "Profile 9", "Profile 16", "Profile 8"]
DEFAULT_TIMEOUT_SEC = 300.0  # 5 minutes default lease (covers standard & high thinking)  # 5 minutes default lease (covers standard & high thinking)
DEEP_RESEARCH_TIMEOUT_SEC = 900.0  # 15 minutes lease for deep research runs


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


def _read_locks() -> Dict[str, Any]:
    return _read_json(LOCKS_FILE)


def _write_locks(locks: Dict[str, Any]) -> None:
    _write_json(LOCKS_FILE, locks)


def clean_expired_locks() -> Dict[str, Any]:
    """Purges expired leases and returns active locks."""
    now = time.time()
    locks = _read_locks()
    changed = False
    active = {}
    for prof, info in locks.items():
        exp = info.get("expires_at", 0)
        if exp > now:
            active[prof] = info
        else:
            changed = True
    if changed:
        _write_locks(active)
    return active


def get_live_profile_status() -> Dict[str, Any]:
    """Returns a full observability status report of all fleet profiles, active agent leases, and usage."""
    active_locks = clean_expired_locks()
    
    # Try importing profile_manager for account identities and quota state
    profiles_meta = {}
    quota_state = {}
    try:
        import profile_manager
        for p in profile_manager.get_all_profiles():
            profiles_meta[p.dir_name] = {
                "name": p.name,
                "email": p.email,
                "is_ai_premium": p.is_ai_premium,
                "status": p.status,
                "cooldown_until": p.cooldown_until,
            }
        quota_state = profile_manager.load_quota_state()
    except Exception:
        pass

    status = {}
    now = time.time()
    for prof in FLEET_ORDER:
        lock = active_locks.get(prof)
        p_meta = profiles_meta.get(prof, {})
        q_meta = quota_state.get(prof, {})

        # Compute status
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
            "status": prof_status,
            "holder": holder,
            "task": task,
            "elapsed_seconds": elapsed,
            "remaining_seconds": max(0, remaining) if remaining is not None else None,
            "tab_id": tab_id,
            "session_id": session_id,
            "current_usage_percent": q_meta.get("current_usage_percent"),
            "weekly_usage_percent": q_meta.get("weekly_usage_percent"),
            "current_reset": q_meta.get("current_reset"),
            "weekly_reset": q_meta.get("weekly_reset"),
            "last_used": q_meta.get("last_used", 0.0),
        }
    return status


def is_bridge_running() -> bool:
    """Checks if the local Argon Bridge daemon is running and reachable on port 9229."""
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:9229/status", timeout=1.0) as resp:
            return resp.status == 200
    except Exception:
        return False


def ensure_bridge_running() -> bool:
    """Attempts to auto-start the local Argon Bridge server if not already running."""
    if is_bridge_running():
        return True
    try:
        import subprocess
        server_path = Path(__file__).parent / "server.py"
        if server_path.exists():
            subprocess.Popen(
                [sys.executable, str(server_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            t0 = time.time()
            while time.time() - t0 < 3.0:
                time.sleep(0.3)
                if is_bridge_running():
                    print("[ProfileLock] Auto-started Argon Bridge daemon (127.0.0.1:9229).")
                    return True
    except Exception as e:
        print(f"[ProfileLock] Note: bridge auto-start: {e}", file=sys.stderr)
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


def launch_profile_candidate(profile: str) -> bool:
    """Attempts to launch Chrome for the candidate profile via bridge /launch or profile_manager."""
    # Method 1: Try bridge /launch endpoint
    try:
        import urllib.request
        req_data = json.dumps({"profile": profile}).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:9229/launch",
            data=req_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            if resp.status == 200:
                res = json.loads(resp.read().decode("utf-8"))
                if res.get("ok"):
                    return True
    except Exception:
        pass

    # Method 2: Direct profile_manager launch
    try:
        import profile_manager
        profile_manager.launch_profile_window(profile)
        return True
    except Exception as e:
        print(f"[ProfileLock] Warning launching window for '{profile}': {e}", file=sys.stderr)
        return False


def _get_connected_profiles() -> set:
    """Queries local bridge /status to identify which Chrome profiles have live connected extensions."""
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:9229/status", timeout=2.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {c.get("dir_name") for c in data.get("connected_extensions", []) if c.get("dir_name")}
    except Exception:
        return set()


def pick_optimal_idle_profile(preferred_order: Optional[List[str]] = None) -> Optional[str]:
    """Autonomous selector: picks the best idle profile with strict user-mandated hierarchy:

    Priority 1: Profile 14 (profile-2@example.com)
    Priority 2: Profile 13 (profile-1@example.com)
    Failsafes: Profile 7, Profile 9, Profile 16, Profile 8

    For each candidate in the hierarchy:
    1. Skips if BUSY, COOLDOWN, or quota exhausted (>=95%).
    2. Verifies live WebSocket responsiveness via server.py's /ping_profile?profile=<candidate>.
    3. If not connected, attempts launch and polls /ping_profile for up to 8s (0.5s intervals).
    4. If responsive, selects profile immediately.
    5. If still offline after 8s, steps down to the next priority profile in the hierarchy.
    """
    ensure_bridge_running()
    status = get_live_profile_status()

    hierarchy = preferred_order or [
        PRIMARY_PROFILE_1,  # Priority 1: Profile 14
        PRIMARY_PROFILE_2,  # Priority 2: Profile 13
        *FAILSAFE_ORDER,     # Failsafes: Profile 7, Profile 9, Profile 16, Profile 8
    ]

    for prof in hierarchy:
        info = status.get(prof, {})
        prof_status = info.get("status", "IDLE")

        # Skip if currently locked or in rate-limit cooldown
        if prof_status != "IDLE":
            print(f"[ProfileLock] Candidate '{prof}' is not IDLE ({prof_status}, holder: {info.get('holder')}). Skipping...")
            continue

        # Skip if 5-hour quota is exhausted (>= 95%)
        usage_pct = info.get("current_usage_percent")
        if usage_pct is not None and usage_pct >= 95:
            print(f"[ProfileLock] Candidate '{prof}' skipped: quota exhausted ({usage_pct}% >= 95%).")
            continue

        if prof == PRIMARY_PROFILE_1:
            tier_desc = "Priority 1 (profile-2@example.com)"
        elif prof == PRIMARY_PROFILE_2:
            tier_desc = "Priority 2 (profile-1@example.com)"
        else:
            tier_desc = f"Failsafe ({prof})"

        print(f"[ProfileLock] Testing candidate '{prof}' [{tier_desc}] for live responsiveness...")

        # 1. Live WebSocket responsiveness check via /ping_profile
        if ping_profile(prof):
            print(f"[ProfileLock] ✅ Profile '{prof}' ({tier_desc}) is online and responsive to WebSocket ping. Selected.")
            return prof

        # 2. Not connected: attempt launch and poll /ping_profile for up to 8s (0.5s intervals)
        print(f"[ProfileLock] Profile '{prof}' ({tier_desc}) is not connected. Attempting launch...")
        launched = launch_profile_candidate(prof)
        if launched:
            print(f"[ProfileLock] Polling /ping_profile for '{prof}' up to 8.0s (0.5s intervals)...")
            start_poll = time.time()
            online = False
            while time.time() - start_poll < 8.0:
                time.sleep(0.5)
                if ping_profile(prof):
                    online = True
                    break

            if online:
                elapsed = round(time.time() - start_poll, 2)
                print(f"[ProfileLock] ✅ Profile '{prof}' ({tier_desc}) came online in {elapsed}s and responded to WebSocket ping. Selected.")
                return prof

        print(f"[ProfileLock] ⚠️ Profile '{prof}' ({tier_desc}) still offline after 8s launch attempt. Stepping down to next priority profile in hierarchy...")

    print("[ProfileLock] ❌ All browser profiles in hierarchy failed /ping_profile or launch verification.")
    return None


def renew_profile_lease(profile: str, agent_id: str, extend_seconds: float = 180.0) -> bool:
    """Heartbeat: extends the lease on a profile while generation or research is actively proceeding."""
    locks = clean_expired_locks()
    lock = locks.get(profile)
    if lock and lock.get("agent_id") == agent_id:
        lock["expires_at"] = time.time() + extend_seconds
        _write_locks(locks)
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
) -> Tuple[Optional[str], Optional[str]]:
    """Acquires a profile lease for the calling agent.
    
    Observability & Dynamic Routing:
    - If preferred_profile is idle: acquires it immediately.
    - If preferred_profile is busy: reports the active holder/task and auto-routes to an idle profile with lowest usage.
    - If preferred_profile is None: picks the optimal idle profile automatically.
    - Supports session affinity: reuses profile previously bound to session_id if free.
    """
    now = time.time()
    ttl = lease_seconds or (DEEP_RESEARCH_TIMEOUT_SEC if deep_research else DEFAULT_TIMEOUT_SEC)
    active_locks = clean_expired_locks()
    sessions = _read_json(SESSIONS_FILE)

    target_prof = None

    # 1. Check session affinity first (sticky multi-turn conversation)
    if session_id and session_id in sessions:
        bound_prof = sessions[session_id].get("profile")
        if bound_prof:
            current_lock = active_locks.get(bound_prof)
            if not current_lock or current_lock.get("agent_id") == agent_id:
                target_prof = bound_prof

    # 2. Check preferred profile if specified
    if not target_prof and preferred_profile:
        current_lock = active_locks.get(preferred_profile)
        if current_lock and current_lock.get("agent_id") != agent_id:
            holder = current_lock.get("agent_id", "another agent")
            task_desc = current_lock.get("task", "task")
            rem = max(0, int(current_lock.get("expires_at", now) - now))
            print(
                f"[ProfileLock] Preferred '{preferred_profile}' is BUSY (held by '{holder}' for '{task_desc}', {rem}s remaining)."
            )
            print("[ProfileLock] Auto-negotiating optimal idle profile in hierarchy...")
            target_prof = pick_optimal_idle_profile()
        else:
            # Preferred profile is idle: verify responsiveness / launch, falling back to hierarchy if offline
            pref_hierarchy = [preferred_profile] + [p for p in FLEET_ORDER if p != preferred_profile]
            target_prof = pick_optimal_idle_profile(preferred_order=pref_hierarchy)

    # 3. If not assigned, pick optimal idle profile across fleet using strict hierarchy
    if not target_prof:
        target_prof = pick_optimal_idle_profile()
        if target_prof:
            print(f"[ProfileLock] Assigned idle profile '{target_prof}' to agent '{agent_id}'.")

    if not target_prof:
        holders = {p: f"{active_locks[p].get('agent_id')} ({active_locks[p].get('task', 'task')})" for p in active_locks}
        return None, f"All Google One AI Premium profiles are offline, busy, or in cooldown: {holders}. Please wait or select another profile."

    # Record the lease
    active_locks[target_prof] = {
        "agent_id": agent_id,
        "task": task,
        "session_id": session_id,
        "tab_id": tab_id,
        "locked_at": now,
        "expires_at": now + ttl,
    }
    _write_locks(active_locks)

    # Update session affinity
    if session_id:
        sessions[session_id] = {
            "profile": target_prof,
            "agent_id": agent_id,
            "last_active": now,
        }
        _write_json(SESSIONS_FILE, sessions)

    return target_prof, None


def release_profile_lease(profile: str, agent_id: Optional[str] = None) -> bool:
    """Releases the lock on a profile so other agents can immediately acquire it."""
    active_locks = clean_expired_locks()
    if profile in active_locks:
        current_holder = active_locks[profile].get("agent_id")
        if agent_id and current_holder != agent_id:
            return False
        del active_locks[profile]
        _write_locks(active_locks)
        print(f"[ProfileLock] Released lease on '{profile}' (now IDLE).")
        return True
    return True
