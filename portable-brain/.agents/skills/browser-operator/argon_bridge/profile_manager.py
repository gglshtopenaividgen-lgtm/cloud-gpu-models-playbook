#!/usr/bin/env python3
"""profile_manager.py - Chrome Profile Discovery, Quota State & Profile Launcher.

Discovers authentic user Chrome profiles from Local State, prioritizes Google One AI
Premium accounts (ai_subscription_tier == 1), and manages failover rotation.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

CHROME_USER_DATA = Path(os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data"))
LOCAL_STATE_PATH = CHROME_USER_DATA / "Local State"
EXTENSION_DIR = Path(__file__).parent / "extension"
QUOTA_STATE_PATH = Path(__file__).parent / "quota_state.json"

CHROME_PATHS = [
    Path(os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe")),
    Path(os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe")),
    Path(os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")),
]


@dataclass
class ChromeProfile:
    dir_name: str
    name: str
    email: str
    gaia_name: str
    ai_subscription_tier: int
    is_ai_premium: bool
    avatar_path: str
    status: str = "IDLE"  # IDLE, RUNNING, COOLDOWN, OFFLINE
    cooldown_until: float = 0.0
    last_used: float = 0.0
    requests_completed: int = 0
    quota_hits: int = 0


def get_chrome_executable() -> Path:
    """Finds the installed Google Chrome executable."""
    for p in CHROME_PATHS:
        if p.exists():
            return p
    which = shutil.which("chrome.exe") or shutil.which("chrome")
    if which:
        return Path(which)
    raise FileNotFoundError("Google Chrome executable not found in standard paths.")


def load_quota_state() -> dict[str, dict[str, Any]]:
    """Loads persistent quota state file if present."""
    if QUOTA_STATE_PATH.exists():
        try:
            with open(QUOTA_STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_quota_state(state: dict[str, dict[str, Any]]) -> None:
    """Saves quota state persistently."""
    try:
        with open(QUOTA_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"[ProfileManager] Warning saving quota state: {e}", file=sys.stderr)


def update_profile_usage_telemetry(dir_name: str, usage_info: dict[str, Any]) -> None:
    """Updates persistent quota and usage telemetry for a profile."""
    if not dir_name or not usage_info:
        return
    state = load_quota_state()
    p_state = state.setdefault(dir_name, {})
    if usage_info.get("current_usage_percent") is not None:
        p_state["current_usage_percent"] = usage_info.get("current_usage_percent")
    if usage_info.get("weekly_usage_percent") is not None:
        p_state["weekly_usage_percent"] = usage_info.get("weekly_usage_percent")
    if usage_info.get("current_reset"):
        p_state["current_reset"] = usage_info.get("current_reset")
    if usage_info.get("weekly_reset"):
        p_state["weekly_reset"] = usage_info.get("weekly_reset")
    p_state["last_checked"] = time.time()
    save_quota_state(state)


def get_all_profiles() -> list[ChromeProfile]:
    """Parses Local State to extract all user profiles with AI Pro prioritization."""
    if not LOCAL_STATE_PATH.exists():
        raise FileNotFoundError(f"Chrome Local State not found at: {LOCAL_STATE_PATH}")

    with open(LOCAL_STATE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    info_cache = data.get("profile", {}).get("info_cache", {})
    quota_state = load_quota_state()
    profiles: list[ChromeProfile] = []
    now = time.time()

    for dir_name, info in info_cache.items():
        name = info.get("name", dir_name)
        email = info.get("user_name", "")
        gaia_name = info.get("gaia_name", "")
        tier = int(info.get("ai_subscription_tier", 0))
        is_premium = (tier == 1)

        # Avatar picture check
        pic_file = info.get("gaia_picture_file_name", "Google Profile Picture.png")
        avatar_file = CHROME_USER_DATA / dir_name / pic_file
        avatar_path = str(avatar_file) if avatar_file.exists() else ""

        # Merge with quota state
        q = quota_state.get(dir_name, {})
        cooldown_until = q.get("cooldown_until", 0.0)
        if cooldown_until > now:
            status = "COOLDOWN"
        else:
            status = "IDLE" if q.get("status") == "COOLDOWN" else q.get("status", "IDLE")
            cooldown_until = 0.0

        p = ChromeProfile(
            dir_name=dir_name,
            name=name,
            email=email,
            gaia_name=gaia_name,
            ai_subscription_tier=tier,
            is_ai_premium=is_premium,
            avatar_path=avatar_path,
            status=status,
            cooldown_until=cooldown_until,
            last_used=q.get("last_used", 0.0),
            requests_completed=q.get("requests_completed", 0),
            quota_hits=q.get("quota_hits", 0),
        )
        profiles.append(p)

    # Sort AI Premium first, then by least recently used
    profiles.sort(key=lambda x: (not x.is_ai_premium, x.last_used))
    return profiles


def get_ai_premium_profiles() -> list[ChromeProfile]:
    """Returns only the confirmed Google One AI Premium profiles."""
    return [p for p in get_all_profiles() if p.is_ai_premium]


def get_next_available_profile(preferred: str | None = None) -> ChromeProfile | None:
    """Finds the next ready AI Premium profile using round-robin / least-recently-used."""
    profiles = get_ai_premium_profiles()
    now = time.time()

    # If preferred profile is valid and not in cooldown, choose it
    if preferred:
        for p in profiles:
            if (p.dir_name == preferred or p.email == preferred) and (p.cooldown_until <= now):
                return p

    # Otherwise pick first available non-cooldown AI Pro profile
    available = [p for p in profiles if p.cooldown_until <= now and p.status != "BUSY"]
    if available:
        # Sort by least recently used
        available.sort(key=lambda x: x.last_used)
        return available[0]

    # If all in cooldown, pick the one with earliest cooldown expiration
    if profiles:
        profiles.sort(key=lambda x: x.cooldown_until)
        return profiles[0]
    return None


def mark_profile_cooldown(dir_name: str, cooldown_seconds: int = 1800) -> None:
    """Marks a profile in cooldown when rate-limit (429 / limit banner) is encountered."""
    state = load_quota_state()
    p_state = state.setdefault(dir_name, {})
    p_state["cooldown_until"] = time.time() + cooldown_seconds
    p_state["status"] = "COOLDOWN"
    p_state["quota_hits"] = p_state.get("quota_hits", 0) + 1
    save_quota_state(state)
    print(f"[ProfileManager] Profile {dir_name} marked COOLDOWN for {cooldown_seconds}s.")


def mark_profile_used(dir_name: str) -> None:
    """Updates profile last_used and request counters."""
    state = load_quota_state()
    p_state = state.setdefault(dir_name, {})
    p_state["last_used"] = time.time()
    p_state["requests_completed"] = p_state.get("requests_completed", 0) + 1
    p_state["status"] = "IDLE"
    save_quota_state(state)


def launch_profile_window(dir_name: str, url: str = "https://aistudio.google.com/prompts/new_chat") -> subprocess.Popen:
    """Launches a Chrome window for the specified profile with the unpacked bridge extension."""
    chrome_exe = get_chrome_executable()
    args = [
        str(chrome_exe),
        f"--profile-directory={dir_name}",
    ]
    if EXTENSION_DIR.exists():
        args.append(f"--load-extension={str(EXTENSION_DIR)}")
    args.append(url)

    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc


def print_profiles_summary() -> None:
    """Prints a clean CLI summary table of all detected profiles."""
    profiles = get_all_profiles()
    now = time.time()

    print("\n" + "=" * 80)
    print(" CHROME GOOGLE ACCOUNTS & AI PRO PROFILES (from Local State)")
    print("=" * 80)
    print(f"{'DIR':<12} {'TIER':<8} {'STATUS':<10} {'NAME':<15} {'EMAIL':<30}")
    print("-" * 80)

    for p in profiles:
        tier_str = "PRO ⭐️" if p.is_ai_premium else "FREE"
        status_str = p.status
        if p.cooldown_until > now:
            remaining = int(p.cooldown_until - now)
            status_str = f"COOL({remaining}s)"
        print(f"{p.dir_name:<12} {tier_str:<8} {status_str:<10} {p.name[:14]:<15} {p.email:<30}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "launch":
        target = sys.argv[2] if len(sys.argv) > 2 else "Profile 8"
        target_url = sys.argv[3] if len(sys.argv) > 3 else "https://aistudio.google.com/prompts/new_chat"
        print(f"Launching {target} -> {target_url}...")
        launch_profile_window(target, target_url)
    elif len(sys.argv) > 1 and sys.argv[1] == "rotate":
        next_p = get_next_available_profile()
        if next_p:
            print(json.dumps(asdict(next_p), indent=2))
        else:
            print(json.dumps({"error": "No AI Premium profiles found"}))
    elif len(sys.argv) > 1 and sys.argv[1] == "json":
        print(json.dumps([asdict(p) for p in get_all_profiles()], indent=2))
    else:
        print_profiles_summary()
