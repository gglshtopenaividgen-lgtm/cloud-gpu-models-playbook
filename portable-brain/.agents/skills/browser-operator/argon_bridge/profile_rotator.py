#!/usr/bin/env python3
"""profile_rotator.py - Standalone Windows Host-Side Chrome Profile Shortcut Rotator.

Generates per-profile Windows .lnk shortcuts, audits live open Chrome profiles via the
127.0.0.1:9229 bridge, enforces the low-RAM open-profile cap (default 3), prioritizes
Tier 1 Alt Pro accounts before Tier 2 Daily Drivers, and safely closes single profiles
with a personal-tab protection guard. Zero Chrome MV3 extension modifications required.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict
from pathlib import Path
from typing import Any

BRIDGE_DIR = Path(__file__).parent
sys.path.insert(0, str(BRIDGE_DIR))
import profile_manager  # noqa: E402
from profile_lock_manager import idle_profile_eviction  # noqa: E402

BRIDGE_URL = "http://127.0.0.1:9229"
DEFAULT_MAX_OPEN_PROFILES = 3
MANIFEST_NAME = "shortcuts_manifest.json"
AGENT_CHROME_FLAGS = (
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
)


def _get_current_desktop_name() -> str:
    """Returns the current Windows Desktop name ('Default' vs 'exebox-...')."""
    if sys.platform != "win32":
        return "Default"
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        hdesk = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
        buf = ctypes.create_unicode_buffer(256)
        ok = user32.GetUserObjectInformationW(hdesk, 2, buf, ctypes.sizeof(buf), None)
        if ok and buf.value:
            return buf.value
    except Exception:
        pass
    return "unknown"


def _http_json(method: str, path: str, payload: dict[str, Any] | None = None, timeout: float = 5.0) -> dict[str, Any]:
    """Performs an HTTP JSON request against the local bridge daemon."""
    url = f"{BRIDGE_URL}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8")
            return json.loads(body)
        except Exception:
            return {"ok": False, "error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]+', "_", (name or "").strip())
    return cleaned or "Profile"


def _shortcut_filename(p: profile_manager.ChromeProfile) -> str:
    return f"{p.dir_name} - {_sanitize_filename(p.name)}.lnk"


def _resolve_profile(identifier: str) -> profile_manager.ChromeProfile:
    """Resolves a profile by directory name (e.g. 'Profile 14'), email, or display name."""
    target = (identifier or "").strip().lower()
    profiles = profile_manager.get_all_profiles()
    for p in profiles:
        if p.dir_name.lower() == target or p.email.lower() == target:
            return p
    for p in profiles:
        if p.name.lower() == target:
            return p
    raise ValueError(f"Profile not found in Chrome Local State: {identifier!r}")


def _list_tabs_for_profile(dir_name: str, timeout: float = 4.0) -> dict[str, Any]:
    return _http_json(
        "POST",
        "/command",
        {"action": "LIST_TABS", "profile": dir_name, "params": {}, "timeout": timeout},
        timeout=timeout + 2.0,
    )


def _get_bridge_resources(timeout: float = 3.0) -> dict[str, Any]:
    """Queries GET /resources from the local bridge daemon for global agent ownership state."""
    res = _http_json("GET", "/resources", timeout=timeout)
    if isinstance(res, dict) and res.get("ok"):
        return res
    return {
        "ok": False,
        "max_agent_profiles": DEFAULT_MAX_OPEN_PROFILES,
        "max_agent_tabs": 6,
        "active_agent_profiles": [],
        "active_agent_profiles_count": 0,
        "active_agent_tabs": 0,
        "owned_tabs": {},
        "launched_by_agent": {},
    }


def get_live_profile_states() -> tuple[bool, dict[str, dict[str, Any]]]:
    """Fetches authoritative live open-tab states for all profiles via LIST_TABS.

    GET /status only reflects tabs_count from WebSocket REGISTER time, so we always verify
    live open windows with LIST_TABS per connected profile.
    """
    profiles = profile_manager.get_all_profiles()
    status_res = _http_json("GET", "/status", timeout=3.0)
    bridge_online = status_res.get("status") == "online"

    connected_dirs: set[str] = set()
    if bridge_online:
        for ext in status_res.get("connected_extensions", []):
            d = ext.get("dir_name")
            if d:
                connected_dirs.add(d)

    states: dict[str, dict[str, Any]] = {}
    for p in profiles:
        connected = p.dir_name in connected_dirs
        tabs: list[dict[str, Any]] = []
        is_open = False
        list_error = ""
        if bridge_online and connected:
            res = _list_tabs_for_profile(p.dir_name, timeout=4.0)
            if res.get("ok") and isinstance(res.get("tabs"), list):
                tabs = res["tabs"]
                is_open = len(tabs) > 0
            else:
                list_error = str(res.get("error", ""))

        lnk_path = profile_manager.SHORTCUTS_DIR / _shortcut_filename(p)
        states[p.dir_name] = {
            "profile": p,
            "connected": connected,
            "is_open": is_open,
            "tabs_count": len(tabs),
            "tabs": tabs,
            "shortcut_path": str(lnk_path),
            "shortcut_exists": lnk_path.exists(),
            "list_error": list_error,
        }
    return bridge_online, states


def generate_shortcuts(target_dir: Path | None = None) -> dict[str, Any]:
    """Generates one Windows .lnk Chrome shortcut per discovered profile in a single PowerShell COM pass."""
    out_dir = Path(target_dir) if target_dir else profile_manager.SHORTCUTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    chrome_exe = str(profile_manager.get_chrome_executable())
    profiles = profile_manager.get_all_profiles()

    specs: list[dict[str, Any]] = []
    manifest: dict[str, dict[str, Any]] = {}
    for p in profiles:
        lnk_path = out_dir / _shortcut_filename(p)
        ico_candidate = profile_manager.CHROME_USER_DATA / p.dir_name / "Google Profile.ico"
        icon_loc = str(ico_candidate) if ico_candidate.exists() else f"{chrome_exe},0"
        args = f'--profile-directory="{p.dir_name}" {" ".join(AGENT_CHROME_FLAGS)} --new-window about:blank'
        desc = f"Chrome {p.dir_name} ({p.email or p.name})"
        specs.append(
            {
                "lnk_path": str(lnk_path),
                "target_path": chrome_exe,
                "arguments": args,
                "icon_location": icon_loc,
                "description": desc,
            }
        )
        manifest[p.dir_name] = {
            "dir_name": p.dir_name,
            "name": p.name,
            "email": p.email,
            "shortcut_path": str(lnk_path),
            "is_ai_premium": p.is_ai_premium,
            "is_daily_driver": p.is_daily_driver,
            "has_bridge_extension": p.has_bridge_extension,
        }

    # Execute a single PowerShell COM WScript.Shell loop using base64 JSON payload (safe against quoting)
    specs_json = json.dumps(specs)
    ps_script = (
        "$ErrorActionPreference = 'Stop'; "
        "$specs = $env:PROFILE_SHORTCUT_SPECS | ConvertFrom-Json; "
        "$sh = New-Object -ComObject WScript.Shell; "
        "foreach ($item in $specs) { "
        "  $s = $sh.CreateShortcut($item.lnk_path); "
        "  $s.TargetPath = $item.target_path; "
        "  $s.Arguments = $item.arguments; "
        "  $s.IconLocation = $item.icon_location; "
        "  $s.Description = $item.description; "
        "  $s.Save(); "
        "}"
    )
    env = os.environ.copy()
    env["PROFILE_SHORTCUT_SPECS"] = specs_json
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"PowerShell shortcut creation failed: {proc.stderr or proc.stdout}")

    manifest_path = out_dir / MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "shortcuts_dir": str(out_dir),
        "manifest_path": str(manifest_path),
        "count": len(specs),
        "profiles": list(manifest.values()),
    }


def ensure_shortcut_for_profile(p: profile_manager.ChromeProfile) -> Path:
    lnk_path = profile_manager.SHORTCUTS_DIR / _shortcut_filename(p)
    if not lnk_path.exists():
        generate_shortcuts(profile_manager.SHORTCUTS_DIR)
    return lnk_path


def print_status(as_json: bool = False) -> int:
    status_res = _http_json("GET", "/status", timeout=3.0)
    host_desktop = status_res.get("desktop", "offline") if status_res.get("status") == "online" else "offline"
    interactive_ready = bool(status_res.get("interactive_desktop", False))
    bridge_online, states = get_live_profile_states()
    if as_json:
        out = {
            "bridge_online": bridge_online,
            "host_desktop": host_desktop,
            "interactive_rotation": interactive_ready,
            "local_desktop": _get_current_desktop_name(),
            "open_count": sum(1 for st in states.values() if st["is_open"]),
            "profiles": [
                {
                    **asdict(st["profile"]),
                    "tier_bucket": "TIER_2_DAILY_DRIVER" if st["profile"].is_daily_driver else ("TIER_1_ALT_PRO" if st["profile"].is_ai_premium else "FREE"),
                    "connected": st["connected"],
                    "is_open": st["is_open"],
                    "tabs_count": st["tabs_count"],
                    "shortcut_exists": st["shortcut_exists"],
                    "shortcut_path": st["shortcut_path"],
                }
                for st in states.values()
            ],
        }
        print(json.dumps(out, indent=2))
        return 0

    open_count = sum(1 for st in states.values() if st["is_open"])
    rot_badge = "READY" if interactive_ready else "RUN Start_Gemini_Session.bat"
    print(
        f"\nBridge Daemon (127.0.0.1:9229): {'ONLINE' if bridge_online else 'OFFLINE'} | "
        f"Host Desktop: {host_desktop} (Interactive Rotation: {rot_badge}) | "
        f"Live Open Profiles: {open_count}/{DEFAULT_MAX_OPEN_PROFILES}"
    )
    for header, selector in (
        ("TIER 1 — ALT PRO POOL (DRAIN FIRST)", lambda s: not s["profile"].is_daily_driver),
        ("TIER 2 — DAILY DRIVERS (STRICT LAST RESORT)", lambda s: s["profile"].is_daily_driver),
    ):
        print(f"\n=== {header} ===")
        print(f"{'DIR':<11} {'PRO':<4} {'EXT':<7} {'LIVE':<7} {'TABS':<5} {'LNK':<4} {'EMAIL':<33} {'NAME'}")
        print("-" * 100)
        for st in states.values():
            if not selector(st):
                continue
            p = st["profile"]
            pro_str = "YES" if p.is_ai_premium else "NO"
            ext_str = "OK" if p.has_bridge_extension else "MISSING"
            live_str = "OPEN" if st["is_open"] else ("IDLE_SW" if st["connected"] else "CLOSED")
            lnk_str = "YES" if st["shortcut_exists"] else "NO"
            print(f"{p.dir_name:<11} {pro_str:<4} {ext_str:<7} {live_str:<7} {st['tabs_count']:<5} {lnk_str:<4} {p.email:<33} {p.name}")
    print()
    return 0


def close_profile(identifier: str, force: bool = False, timeout: float = 10.0, *, idle_eviction: bool = False) -> tuple[int, dict[str, Any]]:
    """Safely closes a Chrome profile ONLY if launched by an agent AND containing ZERO user-owned tabs.

    If the profile was not launched by an agent or contains ANY non-agent-owned tab (e.g. YouTube,
    personal Gemini, etc.), only agent-owned tabs are closed and the Chrome window is left open.
    """
    p = _resolve_profile(identifier)
    bridge_online, states = get_live_profile_states()
    if not bridge_online:
        return 1, {"ok": False, "error": "Bridge daemon on 127.0.0.1:9229 is offline; cannot inspect or close tabs safely."}

    st = states[p.dir_name]
    if st.get("list_error"):
        return 1, {"ok": False, "code": "TAB_STATE_UNKNOWN", "error": st["list_error"]}
    if not st["is_open"]:
        return 1, {"ok": False, "code": "TAB_STATE_UNKNOWN", "error": "No verified open tabs to close."}

    tabs = st["tabs"]
    resources = _get_bridge_resources()
    if not resources.get("ok") and not force:
        return 1, {"ok": False, "code": "TAB_STATE_UNKNOWN", "error": "Agent tab ownership could not be verified."}
    launched_by_agent = resources.get("launched_by_agent") or {}
    owned_tabs_map = resources.get("owned_tabs") or {}
    owned_ids = {str(k) for k in (owned_tabs_map.get(p.dir_name) or {}).keys()}

    agent_tabs = [t for t in tabs if str(t.get("id")) in owned_ids]
    user_tabs = [t for t in tabs if str(t.get("id")) not in owned_ids]
    is_agent_launched = p.dir_name in launched_by_agent

    if idle_eviction:
        locks = resources.get("active_locks")
        if not isinstance(locks, dict) or any(
            not isinstance(lease, dict) or lease.get("profile", key.split("::", 1)[0]) == p.dir_name
            for key, lease in locks.items()
        ):
            return 3, {"ok": False, "code": "PROFILE_BUSY", "error": "Profile has an active lease or lease state is unknown."}
        if not is_agent_launched or user_tabs:
            return 3, {"ok": False, "code": "USER_TAB_PROTECTED", "error": "Idle eviction requires a verified agent window with only agent tabs."}

    if not force and (not is_agent_launched or len(user_tabs) > 0):
        # Strictly hands-off: close ONLY our own agent_owned_tabs and leave user window & tabs untouched!
        closed_agent_ids: list[Any] = []
        for t in agent_tabs:
            tid = t.get("id")
            if tid is None:
                continue
            res = _http_json(
                "POST",
                "/command",
                {
                    "action": "CLOSE_TAB",
                    "profile": p.dir_name,
                    "agent_guarded": True,
                    "params": {"tabId": tid},
                    "timeout": 5.0,
                },
                timeout=7.0,
            )
            if res.get("ok"):
                closed_agent_ids.append(tid)

        preserved = [{"id": t.get("id"), "url": t.get("url", ""), "title": t.get("title", "")} for t in user_tabs]
        reason = (
            f"found {len(user_tabs)} user-owned/non-agent tab(s)"
            if user_tabs
            else "profile window was not launched by an agent"
        )
        return 3, {
            "ok": False,
            "code": "USER_TAB_PROTECTED",
            "dir_name": p.dir_name,
            "launched_by_agent": is_agent_launched,
            "closed_agent_tabs": len(closed_agent_ids),
            "preserved_user_tabs": preserved,
            "personal_tabs": preserved,
            "error": (
                f"Refused to close window {p.dir_name}: {reason}. "
                f"Closed {len(closed_agent_ids)} agent-owned tab(s) and left window open."
            ),
        }

    tabs_to_close = tabs if force else agent_tabs
    closed_ids: list[Any] = []
    for t in tabs_to_close:
        tid = t.get("id")
        if tid is None:
            continue
        res = _http_json(
            "POST",
            "/command",
            {
                "action": "CLOSE_TAB",
                "profile": p.dir_name,
                "agent_guarded": not force,
                "idle_eviction": idle_eviction,
                "params": {"tabId": tid},
                "timeout": 5.0,
            },
            timeout=7.0,
        )
        if res.get("ok"):
            closed_ids.append(tid)
        elif idle_eviction:
            return 3, {"ok": False, "code": res.get("code", "CLOSE_TAB_FAILED"), "error": res.get("error")}

    deadline = time.time() + max(2.0, timeout)
    remaining = len(tabs)
    while time.time() < deadline:
        check = _list_tabs_for_profile(p.dir_name, timeout=3.0)
        if check.get("code") == "PROFILE_DISCONNECTED" and len(closed_ids) == len(tabs):
            remaining = 0
            break
        cur_tabs = check.get("tabs")
        if not check.get("ok") or not isinstance(cur_tabs, list):
            return 1, {"ok": False, "code": "TAB_STATE_UNKNOWN", "error": "Could not verify profile closure."}
        remaining = len(cur_tabs)
        if remaining == 0:
            break
        time.sleep(0.4)

    if remaining == 0:
        _http_json("POST", "/resources/release_profile", {"profile": p.dir_name}, timeout=3.0)

    return (0 if remaining == 0 else 1), {
        "ok": remaining == 0,
        "dir_name": p.dir_name,
        "email": p.email,
        "closed_tabs": len(closed_ids),
        "remaining_tabs": remaining,
    }


def close_idle_profile(identifier: str, timeout: float = 10.0) -> tuple[int, dict[str, Any]]:
    """Reserve an idle profile against new leases throughout guarded tab closure."""
    profile = _resolve_profile(identifier).dir_name
    try:
        with idle_profile_eviction(profile) as acquired:
            if not acquired:
                return 3, {"ok": False, "code": "PROFILE_BUSY", "error": "Profile has an active lease or eviction."}
            return close_profile(profile, timeout=timeout, idle_eviction=True)
    except (TimeoutError, ValueError, OSError) as exc:
        return 3, {"ok": False, "code": "PROFILE_BUSY", "error": f"Could not verify lease availability: {exc}"}


def open_profile(
    identifier: str,
    url: str | None = None,
    max_open: int = DEFAULT_MAX_OPEN_PROFILES,
    timeout: float = 18.0,
    no_wait: bool = False,
    setup: bool = False,
    auto_close_idle: bool = False,
    force_local: bool = False,
) -> tuple[int, dict[str, Any]]:
    """Opens a Chrome profile cleanly via its .lnk shortcut (or delegates to the WinSta0\\Default host daemon)."""
    p = _resolve_profile(identifier)
    bridge_online, states = get_live_profile_states()
    st = states[p.dir_name]

    if st["is_open"] and not setup:
        return 0, {
            "ok": True,
            "dir_name": p.dir_name,
            "email": p.email,
            "already_open": True,
            "tabs_count": st["tabs_count"],
            "launch_method": "already_open",
            "elapsed_s": 0.0,
        }

    current_desktop = _get_current_desktop_name()
    if not force_local and (not setup or current_desktop.lower() != "default"):
        status_res = _http_json("GET", "/status", timeout=3.0)
        if status_res.get("interactive_desktop") is True:
            payload = {
                "profile": p.dir_name,
                "url": url,
                "max_open": max_open,
                "timeout": timeout,
                "no_wait": no_wait,
                "setup": setup,
                "auto_close_idle": auto_close_idle,
            }
            res = _http_json("POST", "/profile/open", payload, timeout=max(15.0, timeout + 12.0))
            return (0 if res.get("ok") else 1), {**res, "delegated_via_host": True}
        return 2, {
            "ok": False,
            "code": "HOST_SESSION_REQUIRED",
            "local_desktop": current_desktop,
            "host_desktop": status_res.get("desktop", "offline") if status_res.get("status") == "online" else "offline",
            "error": (
                f"Profile launch from {current_desktop} needs the bridge on WinSta0\\Default. "
                "Double-click Start_Gemini_Session.bat on Desktop first."
            ),
        }

    max_open = max(1, min(int(max_open), DEFAULT_MAX_OPEN_PROFILES))
    resources = _get_bridge_resources()
    if not setup and not resources.get("ok"):
        return 2, {"ok": False, "code": "RESOURCE_STATE_UNKNOWN", "error": "Agent capacity could not be verified."}
    active_agent_profiles = [d for d in (resources.get("active_agent_profiles") or []) if d != p.dir_name]
    launched_by_agent = resources.get("launched_by_agent") or {}

    open_dirs = [d for d, item in states.items() if item["is_open"] and d != p.dir_name]
    at_agent_cap = len(active_agent_profiles) >= max_open
    at_open_cap = len(open_dirs) >= max_open
    if (at_agent_cap or at_open_cap) and not setup:
        closed_idle_profile = None
        if auto_close_idle:
            # STRICTLY only consider closing profiles launched by an agent (never user windows)
            closable = [d for d in open_dirs if d in launched_by_agent]
            candidates = sorted(
                closable,
                key=lambda d: (not states[d]["profile"].is_daily_driver, states[d]["tabs_count"]),
            )
            for cand in candidates:
                rc, close_res = close_idle_profile(cand, timeout=8.0)
                if rc == 0:
                    closed_idle_profile = cand
                    break
        if closed_idle_profile is None:
            code = "AGENT_CAPACITY_REACHED" if at_agent_cap else "MAX_OPEN_PROFILES_REACHED"
            return 2, {
                "ok": False,
                "code": code,
                "error": (
                    f"Agent/RAM guard: active_agent_profiles={len(active_agent_profiles)}/{max_open} "
                    f"({active_agent_profiles}), open_profiles={len(open_dirs)}/{max_open} ({open_dirs}). "
                    "Reuse an already-open idle Tier 1 Alt or release an agent-launched profile first."
                ),
                "open_profiles": open_dirs,
                "active_agent_profiles": active_agent_profiles,
                "resources": resources,
            }

    if setup:
        chrome_exe = str(profile_manager.get_chrome_executable())
        subprocess.Popen(
            [chrome_exe, f"--profile-directory={p.dir_name}", "--new-window", "chrome://extensions"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return 0, {
            "ok": True,
            "dir_name": p.dir_name,
            "email": p.email,
            "launch_method": "setup_extensions",
            "load_unpacked_path": str(profile_manager.EXTENSION_DIR),
            "instructions": "Enable Developer mode -> Load unpacked -> select load_unpacked_path, then sign into AI Studio / Gemini once.",
        }

    if p.is_daily_driver:
        print(f"[LAST_RESORT_DAILY_DRIVER] Launching protected daily-driver profile {p.dir_name} ({p.email}).", file=sys.stderr)

    t0 = time.time()
    lnk_path = ensure_shortcut_for_profile(p)
    if url:
        chrome_exe = str(profile_manager.get_chrome_executable())
        subprocess.Popen(
            [chrome_exe, f"--profile-directory={p.dir_name}", *AGENT_CHROME_FLAGS, "--new-window", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        launch_method = "chrome_url"
    else:
        os.startfile(str(lnk_path))
        launch_method = "shortcut"

    if no_wait or not p.has_bridge_extension:
        note = "" if p.has_bridge_extension else "Bridge extension not installed in this profile; skipped 9229 wait (run with --setup to install)."
        return 0, {
            "ok": True,
            "dir_name": p.dir_name,
            "email": p.email,
            "launch_method": launch_method,
            "shortcut_path": str(lnk_path),
            "has_bridge_extension": p.has_bridge_extension,
            "waited_for_bridge": False,
            "note": note,
            "elapsed_s": round(time.time() - t0, 2),
        }

    if not bridge_online:
        return 1, {
            "ok": False,
            "dir_name": p.dir_name,
            "email": p.email,
            "launch_method": launch_method,
            "error": "Bridge daemon on 127.0.0.1:9229 is offline; launched shortcut but cannot verify bridge connection.",
        }

    deadline = t0 + max(3.0, timeout)
    last_err = ""
    while time.time() < deadline:
        res = _list_tabs_for_profile(p.dir_name, timeout=3.0)
        if res.get("ok") and isinstance(res.get("tabs"), list) and len(res["tabs"]) >= 1:
            return 0, {
                "ok": True,
                "dir_name": p.dir_name,
                "email": p.email,
                "launch_method": launch_method,
                "shortcut_path": str(lnk_path),
                "tabs_count": len(res["tabs"]),
                "tabs": [{"id": t.get("id"), "url": t.get("url", "")} for t in res["tabs"]],
                "elapsed_s": round(time.time() - t0, 2),
            }
        last_err = str(res.get("error", ""))
        time.sleep(0.5)

    return 1, {
        "ok": False,
        "code": "BRIDGE_ATTACH_TIMEOUT",
        "dir_name": p.dir_name,
        "email": p.email,
        "launch_method": launch_method,
        "shortcut_path": str(lnk_path),
        "error": f"Profile {p.dir_name} did not report an open tab on 127.0.0.1:9229 within {timeout}s ({last_err}).",
        "elapsed_s": round(time.time() - t0, 2),
    }


def cleanup_idle(idle_seconds: float = 0.0) -> int:
    """Closes blank tabs and unused Tier-1 Alt Chrome profiles via POST /cleanup/idle."""
    res = _http_json("POST", "/cleanup/idle", {"idle_seconds": idle_seconds})
    print(json.dumps(res, indent=2))
    return 0 if res.get("ok") else 1


def pick_next_auto_profile(exclude: set[str] | None = None) -> tuple[profile_manager.ChromeProfile | None, bool]:
    """Selects next closed bridged AI Pro profile: Tier 1 Alts first, Tier 2 Daily Drivers last."""
    excluded = exclude or set()
    _, states = get_live_profile_states()
    now = time.time()

    tier1: list[profile_manager.ChromeProfile] = []
    tier2: list[profile_manager.ChromeProfile] = []
    for d, st in states.items():
        p: profile_manager.ChromeProfile = st["profile"]
        if d in excluded or st["is_open"]:
            continue
        if not p.is_ai_premium or not p.has_bridge_extension or p.cooldown_until > now:
            continue
        if p.is_daily_driver:
            tier2.append(p)
        else:
            tier1.append(p)

    if tier1:
        tier1.sort(key=lambda x: x.last_used)
        return tier1[0], False
    if tier2:
        tier2.sort(key=lambda x: x.last_used)
        return tier2[0], True
    return None, False


def main() -> int:
    parser = argparse.ArgumentParser(description="Standalone host-side Chrome Profile Shortcut Rotator.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_gen = sub.add_parser("generate-shortcuts", help="Generate Windows .lnk shortcuts for all Chrome profiles.")
    p_gen.add_argument("--dir", type=Path, default=None, help="Target directory for .lnk shortcuts (defaults to argon_bridge/shortcuts).")

    p_stat = sub.add_parser("status", help="Show live Tier 1 Alt vs Tier 2 Daily Driver profile status.")
    p_stat.add_argument("--json", action="store_true", help="Output JSON.")

    p_open = sub.add_parser("open", help="Open a Chrome profile via its .lnk shortcut (enforces RAM cap).")
    p_open.add_argument("profile", help="Profile directory name (e.g. 'Profile 14'), email, or display name.")
    p_open.add_argument("--url", default=None, help="Optional explicit URL instead of launching the .lnk (about:blank).")
    p_open.add_argument("--max-open", type=int, default=DEFAULT_MAX_OPEN_PROFILES, help="Max concurrent open Chrome profiles.")
    p_open.add_argument("--timeout", type=float, default=18.0, help="Seconds to wait for bridge registration.")
    p_open.add_argument("--no-wait", action="store_true", help="Launch and return immediately without waiting on 9229.")
    p_open.add_argument("--setup", action="store_true", help="Open chrome://extensions in target profile to load unpacked extension.")
    p_open.add_argument("--auto-close-idle", action="store_true", help="Close an idle non-personal profile if at max_open.")
    p_open.add_argument("--local", action="store_true", help="Force local desktop launch without delegating to interactive bridge.")

    p_close = sub.add_parser("close", help="Close a single Chrome profile cleanly via CLOSE_TAB (with personal-tab guard).")
    p_close.add_argument("profile", help="Profile directory name, email, or display name.")
    p_close.add_argument("--force", action="store_true", help="Close even if non-agent tabs are open.")
    p_close.add_argument("--timeout", type=float, default=10.0, help="Seconds to verify closure.")

    p_clean = sub.add_parser("cleanup", help="Close blank tabs and unused Tier-1 Alt Chrome profiles.")
    p_clean.add_argument("--idle-seconds", type=float, default=0.0, help="Minimum idle time in seconds (default 0 for immediate cleanup).")

    p_rot = sub.add_parser("rotate", help="Optionally close one profile and open another (or --auto next Tier 1 Alt).")
    p_rot.add_argument("--close", dest="close_target", default=None, help="Profile to close first.")
    p_rot.add_argument("--open", dest="open_target", default=None, help="Specific profile to open.")
    p_rot.add_argument("--auto", action="store_true", help="Automatically pick next closed bridged Tier 1 Alt (Tier 2 Daily Driver last).")
    p_rot.add_argument("--max-open", type=int, default=DEFAULT_MAX_OPEN_PROFILES, help="Max concurrent open Chrome profiles.")
    p_rot.add_argument("--force", action="store_true", help="Force close --close target if personal tabs exist.")
    p_rot.add_argument("--timeout", type=float, default=18.0, help="Bridge readiness wait timeout.")
    p_rot.add_argument("--local", action="store_true", help="Force local desktop launch without delegating to interactive bridge.")

    args = parser.parse_args()

    if args.cmd == "generate-shortcuts":
        res = generate_shortcuts(args.dir)
        print(json.dumps(res, indent=2))
        return 0

    if args.cmd == "status":
        return print_status(as_json=args.json)

    if args.cmd == "open":
        rc, res = open_profile(
            args.profile,
            url=args.url,
            max_open=args.max_open,
            timeout=args.timeout,
            no_wait=args.no_wait,
            setup=args.setup,
            auto_close_idle=args.auto_close_idle,
            force_local=args.local,
        )
        print(json.dumps(res, indent=2))
        return rc

    if args.cmd == "close":
        rc, res = close_profile(args.profile, force=args.force, timeout=args.timeout)
        print(json.dumps(res, indent=2))
        return rc

    if args.cmd == "cleanup":
        return cleanup_idle(idle_seconds=args.idle_seconds)

    if args.cmd == "rotate":
        if not args.open_target and not args.auto:
            print(json.dumps({"ok": False, "error": "Specify either --open <profile> or --auto"}))
            return 1
        close_res: dict[str, Any] | None = None
        excluded: set[str] = set()
        if args.close_target:
            resolved_close = _resolve_profile(args.close_target)
            excluded.add(resolved_close.dir_name)
            if args.force:
                c_rc, close_res = close_profile(resolved_close.dir_name, force=True)
            else:
                c_rc, close_res = close_idle_profile(resolved_close.dir_name)
            if c_rc != 0:
                print(json.dumps({"ok": False, "stage": "close", "close": close_res}, indent=2))
                return c_rc
        if args.auto:
            next_p, is_last_resort = pick_next_auto_profile(exclude=excluded)
            if next_p is None:
                print(json.dumps({"ok": False, "error": "No closed bridged AI Pro profile available to rotate to.", "close": close_res}, indent=2))
                return 1
            if is_last_resort:
                print(f"[LAST_RESORT_DAILY_DRIVER] All Tier 1 Alt profiles are busy/open/cooldown; rotating to {next_p.dir_name}.", file=sys.stderr)
            target_open = next_p.dir_name
        else:
            target_open = args.open_target
        o_rc, open_res = open_profile(target_open, max_open=args.max_open, timeout=args.timeout, force_local=args.local)
        print(json.dumps({"ok": o_rc == 0, "close": close_res, "open": open_res}, indent=2))
        return o_rc

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
