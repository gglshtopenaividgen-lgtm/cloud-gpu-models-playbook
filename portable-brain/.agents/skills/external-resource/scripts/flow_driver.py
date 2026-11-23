#!/usr/bin/env python3
"""flow_driver.py - Automated CLI Driver & Bridge Controller for Google Flow Asset Studio Pro.

Enforces multi-account Flow lease management, safe tab lifecycles, and
automation postMessage communication with the sandboxed applet runner.

Supported Modes:
  --status: Query Flow profile registry and bridge availability.
  --manifest <file> --preset <preset> [--modality <image|video>] [--concurrency 4]
                    [--profile <Profile>] [--export] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

VERSION = "2.0.0"
DEFAULT_BRIDGE_URL = os.environ.get("ARGON_BRIDGE_URL", "http://127.0.0.1:9229")
DEFAULT_CONCURRENCY = 4
DEFAULT_MODALITY = "image"
PRESETS = ("game", "characters", "comics", "scenes", "video")

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
BRAIN_DIR = SKILL_DIR.parent.parent
ARGON_BRIDGE_DIR = BRAIN_DIR / ".agents" / "skills" / "browser-operator" / "argon_bridge"
FLOW_REGISTRY_PATH = SKILL_DIR / "references" / "flow_tool_registry.json"

if str(ARGON_BRIDGE_DIR) not in sys.path and ARGON_BRIDGE_DIR.exists():
    sys.path.insert(0, str(ARGON_BRIDGE_DIR))

try:
    import profile_lock_manager
except ImportError:
    profile_lock_manager = None  # type: ignore


# ==============================================================================
# PATH & SYSTEM HELPERS
# ==============================================================================

def normalize_path(p: str | Path) -> Path:
    """Normalizes WSL and Windows paths to local filesystem path."""
    raw = str(p).strip()
    if os.name != "nt" and re.match(r"^[A-Za-z]:[\\/]", raw):
        drive = raw[0].lower()
        subpath = raw[2:].replace("\\", "/").lstrip("/")
        return Path(f"/mnt/{drive}/{subpath}")
    if os.name == "nt" and raw.startswith("/mnt/"):
        parts = raw.split("/")
        if len(parts) >= 3:
            drive = parts[2].upper()
            subpath = "\\".join(parts[3:])
            return Path(f"{drive}:\\{subpath}")
    return Path(raw)


def load_flow_registry() -> Dict[str, Any]:
    """Loads flow tool registry configuration."""
    reg_path = normalize_path(FLOW_REGISTRY_PATH)
    if not reg_path.exists():
        return {"schema_version": 2, "profiles": {}}
    try:
        return json.loads(reg_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"error": str(e), "profiles": {}}


# ==============================================================================
# MANIFEST PARSER
# ==============================================================================

def parse_manifest(content: str) -> List[Dict[str, Any]]:
    """Parses manifest content supporting JSON array or delimited block formats."""
    raw = content.strip()
    if not raw:
        return []

    # Attempt JSON parsing first
    if raw.startswith("[") or raw.startswith("{"):
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return [data]
        except Exception:
            pass

    # Delimited block format (=== ID: ... === or ID | Prompt | Style | Negative)
    items: List[Dict[str, Any]] = []
    lines = [line.strip() for line in raw.splitlines() if line.strip() and not line.strip().startswith("#")]

    current_item: Dict[str, Any] = {}
    for line in lines:
        if line.startswith("===") or line.startswith("---"):
            if current_item and current_item.get("id"):
                items.append(current_item)
                current_item = {}
            id_match = re.search(r"ID:\s*([^\s=]+)", line, re.IGNORECASE)
            if id_match:
                current_item["id"] = id_match.group(1)
            continue

        if "|" in line:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 2:
                items.append({
                    "id": parts[0],
                    "prompt": parts[1],
                    "style": parts[2] if len(parts) > 2 else "",
                    "negative": parts[3] if len(parts) > 3 else "",
                })
            continue

        kv = line.split(":", 1)
        if len(kv) == 2:
            key = kv[0].strip().lower()
            val = kv[1].strip()
            if key in ("id", "prompt", "style", "negative", "aspect", "folder", "type", "model", "char"):
                current_item[key] = val

    if current_item and current_item.get("id"):
        items.append(current_item)

    return items


# ==============================================================================
# BRIDGE COMMUNICATION
# ==============================================================================

def send_bridge_request(
    endpoint: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    timeout: float = 15.0,
    bridge_url: str = DEFAULT_BRIDGE_URL,
) -> Dict[str, Any]:
    """Sends JSON HTTP request to local bridge daemon."""
    url = f"{bridge_url.rstrip('/')}{endpoint}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "error": str(e)}


def eval_tab_js(profile: str, tab_id: int, js_code: str, bridge_url: str = DEFAULT_BRIDGE_URL, timeout: float = 20.0) -> Dict[str, Any]:
    """Evaluates JavaScript code inside the specified tab via bridge EVAL_DOM."""
    payload = {
        "action": "EVAL_DOM",
        "profile": profile,
        "params": {
            "tabId": tab_id,
            "code": js_code,
        },
    }
    return send_bridge_request("/command", method="POST", payload=payload, timeout=timeout, bridge_url=bridge_url)


# ==============================================================================
# POSTMESSAGE AUTOMATION BRIDGE IN TAB
# ==============================================================================

def post_message_to_runner(
    profile: str,
    tab_id: int,
    action: str,
    payload_data: Optional[Dict[str, Any]] = None,
    timeout_sec: float = 10.0,
    bridge_url: str = DEFAULT_BRIDGE_URL,
) -> Dict[str, Any]:
    """Posts a message to the iframe applet runner and awaits its response."""
    req_id = f"req_{int(time.time() * 1000)}"
    msg_obj = {
        "type": action,
        "action": action,
        "requestId": req_id,
        "payload": payload_data or {},
        **(payload_data or {}),
    }
    msg_json = json.dumps(msg_obj)

    js_code = f"""(() => {{
        return new Promise((resolve) => {{
            const runner = document.querySelector('iframe[src*="flow-applet-runner"]');
            if (!runner || !runner.contentWindow) {{
                resolve({{ ok: false, error: 'Applet runner iframe not found' }});
                return;
            }}
            const timer = setTimeout(() => {{
                window.removeEventListener('message', handler);
                resolve({{ ok: false, error: 'postMessage timed out after {timeout_sec}s' }});
            }}, {int(timeout_sec * 1000)});

            const handler = (event) => {{
                if (event.data && event.data.requestId === '{req_id}') {{
                    clearTimeout(timer);
                    window.removeEventListener('message', handler);
                    resolve({{ ok: true, data: event.data }});
                }}
            }};
            window.addEventListener('message', handler);
            runner.contentWindow.postMessage({msg_json}, '*');
        }});
    }})()"""

    res = eval_tab_js(profile, tab_id, js_code, bridge_url=bridge_url, timeout=timeout_sec + 5.0)
    if res.get("ok"):
        return res.get("result", {})
    return {"ok": False, "error": res.get("error", "EVAL_DOM failed")}


# ==============================================================================
# EXECUTION LIFECYCLE
# ==============================================================================

def run_status(bridge_url: str = DEFAULT_BRIDGE_URL) -> Dict[str, Any]:
    """Queries Flow registry and bridge status."""
    registry = load_flow_registry()
    resources = send_bridge_request("/resources", bridge_url=bridge_url)
    locks = send_bridge_request("/locks", bridge_url=bridge_url)

    profiles_info = {}
    for p_name, p_info in registry.get("profiles", {}).items():
        profiles_info[p_name] = {
            "tier": p_info.get("tier"),
            "role": p_info.get("role"),
            "enabled": p_info.get("enabled", True),
            "app_url": p_info.get("app_url"),
        }

    return {
        "ok": True,
        "version": VERSION,
        "bridge_online": resources.get("ok", False),
        "active_agent_tabs": resources.get("active_agent_tabs", 0),
        "active_agent_profiles": resources.get("active_agent_profiles", []),
        "profiles": profiles_info,
        "active_locks": locks.get("profiles", {}),
    }


def execute_flow_batch(
    manifest_path: str | Path,
    preset: str,
    modality: str = DEFAULT_MODALITY,
    concurrency: int = DEFAULT_CONCURRENCY,
    profile: Optional[str] = None,
    export_package: bool = False,
    dry_run: bool = False,
    agent_id: str = "worker-2",
    bridge_url: str = DEFAULT_BRIDGE_URL,
    poll_interval: float = 3.0,
    max_wait_seconds: float = 900.0,
) -> Dict[str, Any]:
    """Safely leases a profile, opens Flow tab, executes manifest, exports, and closes tab."""
    preset = preset.lower()
    if preset not in PRESETS:
        return {"ok": False, "error": f"Invalid preset: {preset}. Choose from {PRESETS}"}

    norm_manifest = normalize_path(manifest_path)
    if not norm_manifest.exists():
        return {"ok": False, "error": f"Manifest file not found: {norm_manifest}"}

    manifest_text = norm_manifest.read_text(encoding="utf-8")
    items = parse_manifest(manifest_text)
    if not items:
        return {"ok": False, "error": "Manifest contains no valid items"}

    registry = load_flow_registry()
    target_profile = profile
    if not target_profile:
        if profile_lock_manager:
            try:
                target_profile = profile_lock_manager.pick_flow_profile(modality=modality)  # type: ignore
            except Exception:
                pass
        if not target_profile:
            # Fallback to first enabled manager in registry
            for p_name, p_info in registry.get("profiles", {}).items():
                if p_info.get("enabled") and p_info.get("role") == "pro_manager":
                    target_profile = p_name
                    break
        if not target_profile:
            target_profile = "Profile 13"

    profile_meta = registry.get("profiles", {}).get(target_profile, {})
    app_url = profile_meta.get("app_url") or "https://flow.google.com/project/YOUR_FLOW_PROJECT_ID/tool/YOUR_FLOW_TOOL_ID?mode=APP"

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "version": VERSION,
            "target_profile": target_profile,
            "preset": preset,
            "modality": modality,
            "concurrency": concurrency,
            "items_count": len(items),
            "export_package": export_package,
            "app_url": app_url,
            "sample_items": items[:3],
        }

    # Live Execution Lifecycle
    lock_token = None
    tab_id = None
    try:
        # 1. Acquire Lease
        if profile_lock_manager:
            lock_token = profile_lock_manager.acquire_flow_lock(agent_id=agent_id, profile=target_profile, lease_seconds=max_wait_seconds)
            if not lock_token:
                return {"ok": False, "error": f"Failed to acquire Flow lock for profile {target_profile}"}

        # 2. Open Tab on Profile
        open_res = send_bridge_request(
            "/command",
            method="POST",
            payload={"action": "OPEN_TAB", "profile": target_profile, "params": {"url": app_url}},
            bridge_url=bridge_url,
        )
        if not open_res.get("ok"):
            return {"ok": False, "error": f"Failed to open Flow tab: {open_res.get('error')}"}
        tab_id = open_res.get("tabId")

        # Wait for page settle and iframe presence
        time.sleep(5)

        # 3. Configure Preset & Concurrency
        preset_res = post_message_to_runner(target_profile, tab_id, "FLOW_SET_PRESET", {"preset": preset}, bridge_url=bridge_url)
        concurrency_res = post_message_to_runner(target_profile, tab_id, "FLOW_SET_CONCURRENCY", {"concurrency": concurrency, "modality": modality}, bridge_url=bridge_url)

        # 4. Ingest Manifest
        ingest_res = post_message_to_runner(target_profile, tab_id, "FLOW_INGEST_MANIFEST", {"manifestText": manifest_text, "items": items}, bridge_url=bridge_url)
        if not ingest_res.get("ok"):
            return {"ok": False, "error": f"Manifest ingestion failed: {ingest_res.get('error')}"}

        # 5. Start Batch
        start_res = post_message_to_runner(target_profile, tab_id, "FLOW_START_BATCH", {"modality": modality}, bridge_url=bridge_url)
        if not start_res.get("ok"):
            return {"ok": False, "error": f"Start batch failed: {start_res.get('error')}"}

        # 6. Polling loop until completion
        start_time = time.time()
        final_stats = {}
        while time.time() - start_time < max_wait_seconds:
            time.sleep(poll_interval)
            status_res = post_message_to_runner(target_profile, tab_id, "FLOW_GET_STATUS", bridge_url=bridge_url)
            if status_res.get("ok"):
                data = status_res.get("data", {})
                final_stats = data.get("stats", {})
                is_generating = data.get("isGenerating", False)
                if not is_generating:
                    break

        # 7. Export Package if requested
        export_res = None
        if export_package:
            export_res = post_message_to_runner(target_profile, tab_id, "FLOW_EXPORT_PACKAGE", bridge_url=bridge_url)

        return {
            "ok": True,
            "version": VERSION,
            "profile": target_profile,
            "preset": preset,
            "modality": modality,
            "items_processed": len(items),
            "stats": final_stats,
            "export_triggered": bool(export_package and export_res and export_res.get("ok")),
            "elapsed_seconds": round(time.time() - start_time, 2),
        }

    finally:
        # STRICT CLEANUP INVARIANT: Always close opened agent tab & release lock
        if tab_id is not None:
            send_bridge_request(
                "/command",
                method="POST",
                payload={"action": "CLOSE_TAB", "profile": target_profile, "params": {"tabId": tab_id}},
                bridge_url=bridge_url,
            )
        if lock_token is not None and profile_lock_manager:
            try:
                profile_lock_manager.release_flow_lock(agent_id=agent_id, profile=target_profile, token=lock_token)
            except Exception:
                pass


# ==============================================================================
# CLI DISPATCH
# ==============================================================================

def main() -> int:
    parser = argparse.ArgumentParser(description=f"flow_driver.py v{VERSION} - Google Flow Asset Studio CLI Driver")
    parser.add_argument("--status", action="store_true", help="Query Flow registry and bridge status")
    parser.add_argument("--manifest", type=str, help="Path to batch manifest file")
    parser.add_argument("--preset", type=str, choices=PRESETS, help="Production preset (game, characters, comics, scenes, video)")
    parser.add_argument("--modality", type=str, choices=["image", "video"], default=DEFAULT_MODALITY, help="Asset modality (default: image)")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY, help="Worker concurrency (default: 4)")
    parser.add_argument("--profile", type=str, help="Specific profile to use (e.g. 'Profile 13')")
    parser.add_argument("--export", action="store_true", help="Trigger package export download upon batch completion")
    parser.add_argument("--dry-run", action="store_true", help="Validate manifest and simulate lifecycle without touching browser")
    parser.add_argument("--agent-id", type=str, default="worker-2", help="Agent identifier for lease tracking")
    parser.add_argument("--bridge-url", type=str, default=DEFAULT_BRIDGE_URL, help="Argon bridge daemon URL")

    args = parser.parse_args()

    if args.status:
        res = run_status(bridge_url=args.bridge_url)
        print(json.dumps(res, indent=2))
        return 0 if res.get("ok") else 1

    if not args.manifest:
        parser.print_help(sys.stderr)
        return 1

    if not args.preset:
        print("[!] Error: --preset is required when executing a manifest.", file=sys.stderr)
        return 1

    res = execute_flow_batch(
        manifest_path=args.manifest,
        preset=args.preset,
        modality=args.modality,
        concurrency=args.concurrency,
        profile=args.profile,
        export_package=args.export,
        dry_run=args.dry_run,
        agent_id=args.agent_id,
        bridge_url=args.bridge_url,
    )
    print(json.dumps(res, indent=2))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
