#!/usr/bin/env python3
"""server.py - Local WebSocket & REST Bridge Daemon for Antigravity & Chrome MV3 Extension.

Runs on http://127.0.0.1:9229.
Provides:
  - WebSocket at /ws for Manifest V3 Chrome Extension instances across user profiles.
  - REST API at /status, /command, /rotate, /launch for Antigravity agents & PySide6 GUI.
"""

from __future__ import annotations

import asyncio
import ctypes
import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict

from aiohttp import web, WSMsgType

# Add parent directory to path to import profile_manager
sys.path.insert(0, str(Path(__file__).parent))
import profile_manager
import profile_lock_manager

PORT = 9229
HOST = "127.0.0.1"
ROTATOR_SCRIPT = Path(__file__).parent / "profile_rotator.py"

# Global Agent Resource Cap & User-Tab Ownership Ledger
MAX_AGENT_PROFILES = 3
MAX_AGENT_TABS = 6
RESOURCES_FILE = Path(__file__).parent / "bridge_agent_resources.json"
_RESOURCES_LOCK = threading.Lock()
ADMISSION_LOCK = web.AppKey("resource_admission_lock", asyncio.Lock)
PENDING_SLOTS = web.AppKey("pending_resource_slots", dict)
TAB_MUTATIONS = {
    "ATTACH_TAB", "CLEAR_LOGS", "CLICK_ELEMENT", "CLOSE_TAB", "DETACH_TAB",
    "ENABLE_TELEMETRY", "EVAL_DOM", "GO_BACK", "GO_FORWARD", "HANDLE_DIALOG",
    "NAVIGATE_TAB", "RELOAD_TAB", "SCROLL_PAGE", "SWITCH_TAB", "TYPE_TEXT", "UPLOAD_FILES",
}


def _get_current_desktop_name() -> str:
    """Returns the Windows desktop name (e.g. 'Default' vs 'exebox-...') for this process."""
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

# Connected extension WebSocket clients: { client_id: { "ws": WebSocketResponse, "email": str, "dir_name": str, "tabs": list } }
CONNECTED_CLIENTS: Dict[str, Dict[str, Any]] = {}
# Pending request futures: { req_id: asyncio.Future }
PENDING_REQUESTS: Dict[str, asyncio.Future] = {}


# -----------------------------------------------------------------------------
# Global Agent Resource Ledger (MAX_AGENT_PROFILES=3, MAX_AGENT_TABS=6)
# -----------------------------------------------------------------------------

def _normalize_resources(raw: Any) -> Dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    owned = data.get("owned_tabs")
    launched = data.get("launched_by_agent")
    norm_owned: Dict[str, Dict[str, Dict[str, Any]]] = {}
    if isinstance(owned, dict):
        for prof, tabs in owned.items():
            if not prof or not isinstance(tabs, dict):
                continue
            cleaned_tabs = {str(tid): meta for tid, meta in tabs.items() if isinstance(meta, dict)}
            if cleaned_tabs:
                norm_owned[str(prof)] = cleaned_tabs
    norm_launched: Dict[str, Dict[str, Any]] = {}
    if isinstance(launched, dict):
        for prof, meta in launched.items():
            if prof and isinstance(meta, dict):
                norm_launched[str(prof)] = meta
    return {"owned_tabs": norm_owned, "launched_by_agent": norm_launched}


def _load_resources() -> Dict[str, Any]:
    with _RESOURCES_LOCK:
        if RESOURCES_FILE.exists():
            try:
                raw = json.loads(RESOURCES_FILE.read_text(encoding="utf-8"))
                return _normalize_resources(raw)
            except Exception:
                pass
        return {"owned_tabs": {}, "launched_by_agent": {}}


def _save_resources(data: Dict[str, Any]) -> None:
    norm = _normalize_resources(data)
    with _RESOURCES_LOCK:
        try:
            RESOURCES_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = RESOURCES_FILE.with_suffix(".json.tmp")
            tmp_path.write_text(json.dumps(norm, indent=2), encoding="utf-8")
            os.replace(str(tmp_path), str(RESOURCES_FILE))
        except Exception as e:
            print(f"[Bridge] Warning saving {RESOURCES_FILE.name}: {e}", file=sys.stderr)


def register_agent_tab(
    profile: str,
    tab_id: Any,
    owner: str = "agent",
    surface: str = "unknown",
    task: str = "",
    url: str = "",
) -> Dict[str, Any]:
    """Registers a tab as agent-owned in the persistent resource ledger."""
    prof = str(profile or "unknown")
    tid = str(tab_id)
    now = time.time()
    data = _load_resources()
    prof_tabs = data["owned_tabs"].setdefault(prof, {})
    existing = prof_tabs.get(tid, {})
    entry = {
        "owner": owner or existing.get("owner") or "agent",
        "surface": surface or existing.get("surface") or "unknown",
        "task": task or existing.get("task") or "",
        "created_at": existing.get("created_at", now),
        "last_seen": now,
        "url": url or existing.get("url") or "",
    }
    prof_tabs[tid] = entry
    _save_resources(data)
    return entry


def release_agent_tab(profile: str | None, tab_id: Any) -> bool:
    """Removes a tab from the agent-owned ledger."""
    tid = str(tab_id)
    data = _load_resources()
    removed = False
    if profile:
        if tid in data["owned_tabs"].get(profile, {}):
            del data["owned_tabs"][profile][tid]
            if not data["owned_tabs"][profile]:
                del data["owned_tabs"][profile]
            removed = True
    else:
        for prof in list(data["owned_tabs"].keys()):
            if tid in data["owned_tabs"][prof]:
                del data["owned_tabs"][prof][tid]
                if not data["owned_tabs"][prof]:
                    del data["owned_tabs"][prof]
                removed = True
    if removed:
        _save_resources(data)
    return removed


def register_agent_launched_profile(profile: str, owner: str = "agent") -> Dict[str, Any]:
    """Records that a Chrome profile window was launched by an agent."""
    prof = str(profile)
    data = _load_resources()
    entry = {"owner": owner or "agent", "launched_at": time.time()}
    data["launched_by_agent"][prof] = entry
    _save_resources(data)
    return entry


def release_agent_launched_profile(profile: str, clear_tabs: bool = False) -> bool:
    """Removes a profile from launched_by_agent (and optionally clears its owned tabs)."""
    prof = str(profile)
    data = _load_resources()
    changed = False
    if prof in data["launched_by_agent"]:
        del data["launched_by_agent"][prof]
        changed = True
    if clear_tabs and prof in data["owned_tabs"]:
        del data["owned_tabs"][prof]
        changed = True
    if changed:
        _save_resources(data)
    return changed


def is_agent_owned_tab(profile: str | None, tab_id: Any) -> bool:
    """Returns True ONLY if tab_id is explicitly tracked in owned_tabs."""
    tid = str(tab_id)
    data = _load_resources()
    if profile and profile != "unknown":
        return tid in data["owned_tabs"].get(str(profile), {})
    return any(tid in tabs for tabs in data["owned_tabs"].values())


def get_resources_snapshot() -> Dict[str, Any]:
    """Computes live global agent fleet budget across all sessions/profiles."""
    data = _load_resources()
    owned_tabs = data["owned_tabs"]
    launched_by_agent = data["launched_by_agent"]

    active_locks_summary: Dict[str, Any] = {}
    lock_profiles: set[str] = set()
    try:
        active_locks = profile_lock_manager.clean_expired_locks()
        for k, v in active_locks.items():
            if not isinstance(v, dict):
                continue
            prof = v.get("profile") or str(k).split("::")[0]
            if prof:
                lock_profiles.add(prof)
            active_locks_summary[k] = {
                "profile": prof,
                "surface": v.get("surface", "all"),
                "agent_id": v.get("agent_id", "unknown"),
                "task": v.get("task", ""),
                "expires_at": v.get("expires_at"),
            }
    except Exception:
        pass

    active_profiles_set = {prof for prof, tabs in owned_tabs.items() if tabs} | lock_profiles | set(launched_by_agent)
    active_agent_profiles = sorted(active_profiles_set)
    active_agent_tabs = sum(len(tabs) for tabs in owned_tabs.values())

    return {
        "max_agent_profiles": MAX_AGENT_PROFILES,
        "max_agent_tabs": MAX_AGENT_TABS,
        "active_agent_profiles": active_agent_profiles,
        "active_agent_profiles_count": len(active_agent_profiles),
        "active_agent_tabs": active_agent_tabs,
        "owned_tabs": owned_tabs,
        "launched_by_agent": launched_by_agent,
        "active_locks": active_locks_summary,
        "timestamp": time.time(),
    }


async def reconcile_agent_tabs(profile: str | None = None, app: web.Application | None = None) -> Dict[str, Any]:
    """Drop only entries observed before a successful inventory of the same client."""
    owned_tabs = _load_resources()["owned_tabs"]
    for prof in [profile] if profile else list(owned_tabs):
        previous = owned_tabs.get(prof, {})
        client_id, client = _resolve_live_client(prof)
        if not previous or not client or client.get("dir_name") != prof:
            continue
        client_generation = client.get("connected_at")
        result = await send_extension_command(
            "LIST_TABS", {}, preferred_profile=prof, timeout=3.0, client_id=client_id
        )
        if CONNECTED_CLIENTS.get(client_id) is not client or client.get("connected_at") != client_generation:
            continue
        tabs = result.get("tabs")
        if not result.get("ok") or not isinstance(tabs, list):
            continue
        live_ids = {str(tab["id"]) for tab in tabs if isinstance(tab, dict) and tab.get("id") is not None}
        current = _load_resources()
        current_tabs = current["owned_tabs"].get(prof, {})
        removed = False
        for tab_id, old_entry in previous.items():
            if tab_id not in live_ids and current_tabs.get(tab_id) == old_entry:
                del current_tabs[tab_id]
                removed = True
        if removed:
            _save_resources(current)
    return get_resources_snapshot()


def reserve_slot(request: web.Request, profile: str, *, tab: bool) -> str | None:
    """Reserve capacity inside the application admission lock."""
    snapshot = get_resources_snapshot()
    pending = request.app[PENDING_SLOTS]
    now = time.time()
    expired = [
        k for k, v in pending.items()
        if isinstance(v, dict) and v.get("status") == "ambiguous" and v.get("expires_at", 0) <= now
    ]
    for k in expired:
        pending.pop(k, None)

    def _prof(v):
        return v.get("profile") if isinstance(v, dict) else (v[0] if isinstance(v, tuple) else str(v))

    def _is_tab(v):
        return bool(v.get("tab")) if isinstance(v, dict) else (bool(v[1]) if isinstance(v, tuple) else False)

    profiles = set(snapshot["active_agent_profiles"]) | {_prof(v) for v in pending.values() if _prof(v)}
    if profile not in profiles and len(profiles) >= MAX_AGENT_PROFILES:
        return None
    pending_tabs = sum(1 for v in pending.values() if _is_tab(v))
    if tab and snapshot["active_agent_tabs"] + pending_tabs >= MAX_AGENT_TABS:
        return None
    token = str(uuid.uuid4())
    pending[token] = {
        "profile": profile,
        "tab": tab,
        "status": "pending",
        "created_at": now,
    }
    return token


def capacity_error(request: web.Request) -> web.Response:
    slots = request.app[PENDING_SLOTS]

    def _prof(v):
        return v.get("profile") if isinstance(v, dict) else (v[0] if isinstance(v, tuple) else str(v))

    def _is_tab(v):
        return bool(v.get("tab")) if isinstance(v, dict) else (bool(v[1]) if isinstance(v, tuple) else False)

    return web.json_response({
        "ok": False,
        "code": "AGENT_CAPACITY_REACHED",
        "error": "Agent profile or tab capacity reached. Release an agent resource first.",
        "resources": get_resources_snapshot(),
        "pending_profiles": sorted({_prof(item) for item in slots.values() if _prof(item)}),
        "pending_tabs": sum(1 for item in slots.values() if _is_tab(item)),
    }, status=429)


async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    """Handles persistent WebSocket connections from the Chrome extension in each profile."""
    ws = web.WebSocketResponse(heartbeat=20.0)
    await ws.prepare(request)

    client_id = str(uuid.uuid4())[:8]
    client_entry = {
        "ws": ws,
        "email": "unknown",
        "dir_name": "unknown",
        "tabs": [],
        "connected_at": time.time(),
        "last_ping": time.time(),
    }
    CONNECTED_CLIENTS[client_id] = client_entry
    print(f"[Bridge] New extension connected (client_id: {client_id})")

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except Exception:
                    continue

                msg_type = data.get("type")
                req_id = data.get("id")

                # 1. Correlate Response to a Pending Command
                if req_id and req_id in PENDING_REQUESTS:
                    fut = PENDING_REQUESTS.pop(req_id)
                    if not fut.done():
                        fut.set_result(data)
                    if msg_type == "PONG":
                        client_entry["last_ping"] = time.time()
                    continue

                # 1b. PONG Response from Extension
                if msg_type == "PONG":
                    client_entry["last_ping"] = time.time()
                    ping_fut = client_entry.pop("pending_ping", None)
                    if ping_fut and not ping_fut.done():
                        ping_fut.set_result(data)
                    continue

                # 2. Registration Message from Extension
                if msg_type == "REGISTER":
                    email = data.get("email", "")
                    tabs = data.get("tabs", [])
                    client_entry["email"] = email
                    client_entry["tabs"] = tabs
                    client_entry["last_ping"] = time.time()

                    # Match email with Chrome Local State directory
                    all_profiles = profile_manager.get_all_profiles()
                    for p in all_profiles:
                        if p.email and email and (p.email.lower() == email.lower()):
                            client_entry["dir_name"] = p.dir_name
                            break

                    print(f"[Bridge] Registered extension: Email={email} | Dir={client_entry['dir_name']} | Tabs={len(tabs)}")

                # 3. Quota Exhaustion Event Detected by Content Script
                elif msg_type == "QUOTA_EXHAUSTED":
                    dir_name = client_entry.get("dir_name")
                    email = client_entry.get("email")
                    print(f"[Bridge] ⚠️ QUOTA EXHAUSTED for {email} ({dir_name})")
                    if dir_name and dir_name != "unknown":
                        profile_manager.mark_profile_cooldown(dir_name, cooldown_seconds=1800)

                # 4. Tab Update or Page Event
                elif msg_type == "PAGE_EVENT":
                    client_entry["last_ping"] = time.time()

                # 5. Heartbeat Ping
                elif msg_type == "PING":
                    client_entry["last_ping"] = time.time()
                    await ws.send_json({"type": "PONG", "timestamp": time.time()})

            elif msg.type == WSMsgType.ERROR:
                print(f"[Bridge] WebSocket connection closed with error: {ws.exception()}")

    finally:
        CONNECTED_CLIENTS.pop(client_id, None)
        print(f"[Bridge] Extension disconnected: {client_id}")

    return ws


# -----------------------------------------------------------------------------
# REST API Endpoints
# -----------------------------------------------------------------------------

async def handle_health(request: web.Request) -> web.Response:
    """GET /health - Lightweight daemon health & interactive desktop check."""
    desktop_name = _get_current_desktop_name()
    return web.json_response({
        "ok": True,
        "status": "online",
        "desktop": desktop_name,
        "interactive_desktop": desktop_name.lower() == "default",
        "pid": os.getpid(),
        "port": PORT,
        "timestamp": time.time(),
    })


async def handle_resources(request: web.Request) -> web.Response:
    """GET /resources - Returns global agent fleet budget (profiles/3, tabs/6) and ownership ledger."""
    if request.query.get("reconcile") in ("1", "true", "yes"):
        snap = await reconcile_agent_tabs()
    else:
        snap = get_resources_snapshot()
    return web.json_response({"ok": True, **snap})


async def handle_release_profile(request: web.Request) -> web.Response:
    """POST /resources/release_profile - Releases a closed agent-launched profile."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON body"}, status=400)
    profile = body.get("profile")
    if not profile:
        return web.json_response({"ok": False, "error": "Missing 'profile'"}, status=400)
    released = release_agent_launched_profile(str(profile), clear_tabs=bool(body.get("clear_tabs", False)))
    return web.json_response({"ok": True, "released": released, "resources": get_resources_snapshot()})


async def handle_register_tab(request: web.Request) -> web.Response:
    """POST /resources/register_tab - Explicitly registers an agent-owned tab."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON body"}, status=400)
    profile = body.get("profile")
    tab_id = body.get("tab_id") if body.get("tab_id") is not None else body.get("tabId")
    if not profile or tab_id is None:
        return web.json_response({"ok": False, "error": "Missing 'profile' or 'tab_id'"}, status=400)
    entry = register_agent_tab(
        profile=str(profile),
        tab_id=tab_id,
        owner=str(body.get("owner") or "agent"),
        surface=str(body.get("surface") or "unknown"),
        task=str(body.get("task") or ""),
        url=str(body.get("url") or ""),
    )
    return web.json_response({"ok": True, "entry": entry, "resources": get_resources_snapshot()})


async def handle_release_tab(request: web.Request) -> web.Response:
    """POST /resources/release_tab - Releases an agent-owned tab from the resource ledger."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON body"}, status=400)
    profile = body.get("profile")
    tab_id = body.get("tab_id") if body.get("tab_id") is not None else body.get("tabId")
    if tab_id is None:
        return web.json_response({"ok": False, "error": "Missing 'tab_id'"}, status=400)
    released = release_agent_tab(profile=str(profile) if profile else None, tab_id=tab_id)
    return web.json_response({"ok": True, "released": released, "resources": get_resources_snapshot()})


async def handle_status(request: web.Request) -> web.Response:
    """Returns combined system status: Chrome profiles, connected extensions, and quota."""
    profiles = profile_manager.get_all_profiles()
    connected_list = []

    for cid, c in CONNECTED_CLIENTS.items():
        connected_list.append({
            "client_id": cid,
            "email": c.get("email"),
            "dir_name": c.get("dir_name"),
            "tabs_count": len(c.get("tabs", [])),
            "connected_at": c.get("connected_at"),
            "last_ping": c.get("last_ping"),
        })

    # Enrich profile list with connection status
    enriched_profiles = []
    connected_dirs = {c.get("dir_name") for c in CONNECTED_CLIENTS.values() if c.get("dir_name") != "unknown"}
    connected_emails = {c.get("email").lower() for c in CONNECTED_CLIENTS.values() if c.get("email")}

    for p in profiles:
        p_dict = profile_manager.asdict(p)
        is_conn = (p.dir_name in connected_dirs) or (p.email.lower() in connected_emails if p.email else False)
        p_dict["is_connected"] = is_conn
        enriched_profiles.append(p_dict)

    desktop_name = _get_current_desktop_name()
    res = {
        "status": "online",
        "port": PORT,
        "desktop": desktop_name,
        "interactive_desktop": desktop_name.lower() == "default",
        "connected_extensions_count": len(CONNECTED_CLIENTS),
        "connected_extensions": connected_list,
        "profiles": enriched_profiles,
        "ai_premium_count": len(profile_manager.get_ai_premium_profiles()),
        "timestamp": time.time(),
    }
    return web.json_response(res)


def _prune_closed_clients() -> None:
    """Removes any WebSocket entries whose sockets are already closed."""
    for cid, c in list(CONNECTED_CLIENTS.items()):
        ws = c.get("ws")
        if not ws or ws.closed:
            CONNECTED_CLIENTS.pop(cid, None)


def _resolve_live_client(preferred_profile: str | None = None) -> tuple[str | None, dict[str, Any] | None]:
    """Selects the freshest live WebSocket client for preferred_profile (or first live client)."""
    _prune_closed_clients()
    if preferred_profile:
        pref_low = preferred_profile.lower()
        matching: list[tuple[str, dict[str, Any]]] = []
        for cid, c in list(CONNECTED_CLIENTS.items()):
            c_dir = c.get("dir_name")
            c_email = c.get("email")
            if (c_dir and c_dir == preferred_profile) or (c_email and c_email.lower() == pref_low):
                matching.append((cid, c))
        if not matching:
            return None, None
        return max(matching, key=lambda pair: pair[1].get("last_ping", 0.0))

    if not CONNECTED_CLIENTS:
        return None, None
    return max(CONNECTED_CLIENTS.items(), key=lambda pair: pair[1].get("last_ping", 0.0))


async def send_extension_command(
    action: str,
    params: dict[str, Any] | None = None,
    preferred_profile: str | None = None,
    timeout: float = 30.0,
    *,
    client_id: str | None = None,
    client: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Routes and sends an action command to the freshest matching or available extension."""
    if client is not None:
        target_client = client
        target_cid = client_id
        if target_cid is None:
            for cid, c in CONNECTED_CLIENTS.items():
                if c is client:
                    target_cid = cid
                    break
    elif client_id is not None:
        target_cid, target_client = client_id, CONNECTED_CLIENTS.get(client_id)
    else:
        target_cid, target_client = _resolve_live_client(preferred_profile)

    if preferred_profile and not target_client:
        return {
            "ok": False,
            "code": "PROFILE_DISCONNECTED",
            "error": f"PROFILE_DISCONNECTED: {preferred_profile} is not connected to bridge",
            "connected_profiles": [c.get("dir_name") for c in CONNECTED_CLIENTS.values()],
        }
    if not target_client:
        return {"ok": False, "error": "No Chrome extension instances currently connected to bridge."}

    ws: web.WebSocketResponse = target_client["ws"]
    if ws.closed:
        if target_cid:
            CONNECTED_CLIENTS.pop(target_cid, None)
        return {
            "ok": False,
            "code": "PROFILE_DISCONNECTED",
            "error": f"PROFILE_DISCONNECTED: {preferred_profile or target_client.get('dir_name')} socket closed",
            "connected_profiles": [c.get("dir_name") for c in CONNECTED_CLIENTS.values()],
        }

    req_id = str(uuid.uuid4())
    payload = {**(params or {}), "id": req_id, "action": action}

    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    PENDING_REQUESTS[req_id] = fut

    try:
        await ws.send_json(payload)
        res = await asyncio.wait_for(fut, timeout=timeout)
        return res
    except asyncio.TimeoutError:
        PENDING_REQUESTS.pop(req_id, None)
        return {"ok": False, "code": "COMMAND_TIMEOUT", "error": f"Command '{action}' timed out after {timeout}s"}
    except Exception as e:
        PENDING_REQUESTS.pop(req_id, None)
        return {"ok": False, "error": str(e)}


async def handle_command(request: web.Request) -> web.Response:
    """POST /command - Executes action on target extension client with resource-cap & user-tab guards."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON body"}, status=400)

    action = body.get("action")
    if not action:
        return web.json_response({"ok": False, "error": "Missing 'action' parameter"}, status=400)

    preferred_profile = body.get("profile") or body.get("email")
    raw_params = body.get("params", {})
    params = dict(raw_params) if isinstance(raw_params, dict) else {}
    timeout = float(body.get("timeout", 30.0))
    raw_guarded = body.get("agent_guarded")
    if raw_guarded is None:
        raw_guarded = raw_params.get("agent_guarded")
    guarded = True if raw_guarded is None else bool(raw_guarded)
    params.pop("agent_guarded", None)
    idle_eviction = bool(body.get("idle_eviction") or params.pop("idle_eviction", False))
    client_id, client = _resolve_live_client(preferred_profile)
    profile = client.get("dir_name") if client else preferred_profile
    tab_id = params.get("tabId", params.get("tab_id"))
    needs_owner = guarded and (action in TAB_MUTATIONS or action == "CDP_COMMAND")
    if guarded and action == "CDP_COMMAND" and str(params.get("method", "")).startswith(("Browser.", "Target.")):
        return web.json_response({"ok": False, "code": "USER_TAB_PROTECTED"}, status=403)
    if (needs_owner or action == "OPEN_TAB") and (not profile or profile == "unknown"):
        return web.json_response({"ok": False, "code": "PROFILE_REQUIRED"}, status=400)
    if needs_owner and (tab_id is None or not is_agent_owned_tab(profile, tab_id)):
        return web.json_response({
            "ok": False, "code": "USER_TAB_PROTECTED",
            "error": "An explicitly agent-owned tab is required.",
            "profile": profile, "tab_id": tab_id,
        }, status=403)
    if needs_owner:
        params["tabId"] = tab_id

    lock = request.app[ADMISSION_LOCK]
    if idle_eviction:
        active_locks = profile_lock_manager.clean_expired_locks()
        if any((entry.get("profile") or key.split("::")[0]) == profile for key, entry in active_locks.items()):
            return web.json_response({"ok": False, "code": "PROFILE_BUSY"}, status=409)

    token = None
    if action == "OPEN_TAB":
        if profile_lock_manager.is_profile_evicting(profile):
            return web.json_response({"ok": False, "code": "PROFILE_BUSY"}, status=409)
        await reconcile_agent_tabs()
        async with lock:
            token = reserve_slot(request, profile, tab=True)
            if token is None:
                return capacity_error(request)

    uncertain = False
    try:
        dispatch = {"client_id": client_id} if client_id is not None else {}
        result = await send_extension_command(action, params, preferred_profile=profile or preferred_profile,
                                              timeout=timeout, **dispatch)
        if action == "OPEN_TAB":
            opened_tab_id = result.get("tabId", result.get("tab_id"))
            if result.get("ok") and opened_tab_id is not None:
                async with lock:
                    register_agent_tab(profile, opened_tab_id, owner=str(body.get("owner") or "agent"),
                                       surface=str(body.get("surface") or "unknown"),
                                       task=str(body.get("task") or ""), url=str(params.get("url") or ""))
                    if token is not None:
                        request.app[PENDING_SLOTS].pop(token, None)
                        token = None
            elif result.get("code") == "COMMAND_TIMEOUT" or (result.get("ok") and opened_tab_id is None):
                uncertain = True
                if token is not None:
                    async with lock:
                        if token in request.app[PENDING_SLOTS]:
                            slot_val = request.app[PENDING_SLOTS][token]
                            prof_val = slot_val.get("profile", profile) if isinstance(slot_val, dict) else (slot_val[0] if isinstance(slot_val, tuple) else str(slot_val))
                            request.app[PENDING_SLOTS][token] = {
                                "profile": prof_val,
                                "tab": True,
                                "status": "ambiguous",
                                "expires_at": time.time() + 60.0,
                            }
                        token = None
            else:
                if token is not None:
                    async with lock:
                        request.app[PENDING_SLOTS].pop(token, None)
                        token = None
        elif action == "CLOSE_TAB" and (result.get("ok") or "no tab" in str(result.get("error", "")).lower()):
            release_agent_tab(profile, tab_id)
        return web.json_response(result)
    except asyncio.CancelledError:
        uncertain = token is not None
        raise
    finally:
        if token is not None and not uncertain:
            async with lock:
                request.app[PENDING_SLOTS].pop(token, None)


async def handle_ping_profile(request: web.Request) -> web.Response:
    """GET/POST /ping_profile - Sends PING to target profile WebSocket and waits up to 1.5s for PONG."""
    profile = None
    if request.method == "GET":
        profile = request.query.get("profile") or request.query.get("email")
    elif request.method == "POST":
        try:
            body = await request.json()
            profile = body.get("profile") or body.get("email")
        except Exception:
            body = {}
        if not profile:
            profile = request.query.get("profile") or request.query.get("email")

    if not profile:
        return web.json_response(
            {"ok": False, "connected": False, "profile": None, "error": "Missing 'profile' parameter"},
            status=400,
        )

    # Find freshest live matching client
    target_client_id, target_client = _resolve_live_client(profile)

    if not target_client:
        return web.json_response({
            "ok": False,
            "connected": False,
            "profile": profile,
        })

    ws: web.WebSocketResponse = target_client.get("ws")
    if not ws or ws.closed:
        CONNECTED_CLIENTS.pop(target_client_id, None)
        return web.json_response({
            "ok": False,
            "connected": False,
            "profile": profile,
        })

    req_id = str(uuid.uuid4())
    payload = {
        "id": req_id,
        "type": "PING",
        "action": "PING",
        "timeout": 1500,
    }

    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    PENDING_REQUESTS[req_id] = fut
    target_client["pending_ping"] = fut

    try:
        await ws.send_json(payload)
        await asyncio.wait_for(fut, timeout=1.5)
        target_client["last_ping"] = time.time()
        tabs_count = len(target_client.get("tabs", []))
        return web.json_response({
            "ok": True,
            "connected": True,
            "profile": profile,
            "tabs_count": tabs_count,
        })
    except (asyncio.TimeoutError, Exception) as e:
        print(f"[Bridge] Ping failed or timed out for {profile} (client_id: {target_client_id}): {e}")
        CONNECTED_CLIENTS.pop(target_client_id, None)
        try:
            if not ws.closed:
                await ws.close()
        except Exception:
            pass
        return web.json_response({
            "ok": False,
            "connected": False,
            "profile": profile,
        })
    finally:
        PENDING_REQUESTS.pop(req_id, None)
        target_client.pop("pending_ping", None)


async def handle_rotate(request: web.Request) -> web.Response:
    """POST /rotate - Marks current profile as COOLDOWN and picks next ready AI Pro profile."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    current_dir = body.get("profile")
    cooldown = int(body.get("cooldown_seconds", 1800))

    if current_dir:
        profile_manager.mark_profile_cooldown(current_dir, cooldown_seconds=cooldown)

    next_p = profile_manager.get_next_available_profile()
    if next_p:
        return web.json_response({"ok": True, "rotated_to": profile_manager.asdict(next_p)})
    return web.json_response({"ok": False, "error": "No available AI Pro profiles found."}, status=503)


async def handle_launch(request: web.Request) -> web.Response:
    """Keep the legacy launch endpoint on the bounded profile-open path."""
    return await handle_profile_open(request, launch_defaults=True)


async def handle_locks(request: web.Request) -> web.Response:
    """GET /locks - Returns live profile leases and idle status across fleet."""
    status = profile_lock_manager.get_live_profile_status()
    return web.json_response({"ok": True, "profiles": status, "timestamp": time.time()})


async def handle_acquire_lock(request: web.Request) -> web.Response:
    """POST /lock/acquire - Acquires or auto-routes lease for an agent."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    agent_id = body.get("agent_id", "anonymous_agent")
    preferred = body.get("preferred_profile")
    task = body.get("task", "general")
    session_id = body.get("session_id")
    deep_research = body.get("deep_research", False)
    tab_id = body.get("tab_id")

    prof, err = await asyncio.to_thread(
        profile_lock_manager.acquire_profile_lease,
        agent_id=agent_id,
        preferred_profile=preferred,
        task=task,
        session_id=session_id,
        deep_research=deep_research,
        tab_id=tab_id
    )
    if prof:
        return web.json_response({"ok": True, "profile": prof, "agent_id": agent_id})
    return web.json_response({"ok": False, "error": err}, status=409)


async def handle_renew_lock(request: web.Request) -> web.Response:
    """POST /lock/renew - Heartbeat to extend active profile lease during long thinking/research."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    profile = body.get("profile")
    agent_id = body.get("agent_id")
    extend_seconds = float(body.get("extend_seconds", 180.0))
    if profile and agent_id:
        ok = profile_lock_manager.renew_profile_lease(profile, agent_id=agent_id, extend_seconds=extend_seconds)
        return web.json_response({"ok": ok, "profile": profile})
    return web.json_response({"ok": False, "error": "Missing profile or agent_id"}, status=400)


async def handle_release_lock(request: web.Request) -> web.Response:
    """POST /lock/release - Releases profile lease."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    profile = body.get("profile")
    agent_id = body.get("agent_id")
    if profile:
        profile_lock_manager.release_profile_lease(profile, agent_id=agent_id)
        return web.json_response({"ok": True, "released": profile})
    return web.json_response({"ok": False, "error": "Missing 'profile'"}, status=400)


async def _run_rotator_cmd(args: list[str], timeout: float = 30.0) -> tuple[int, dict[str, Any]]:
    """Runs profile_rotator.py asynchronously (non-blocking so /command callbacks work cleanly)."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(ROTATOR_SCRIPT),
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return 1, {"ok": False, "error": f"Rotator command timed out after {timeout}s"}

    out_txt = (stdout_b or b"").decode("utf-8", errors="replace").strip()
    err_txt = (stderr_b or b"").decode("utf-8", errors="replace").strip()
    try:
        parsed = json.loads(out_txt) if out_txt else {}
        if err_txt and isinstance(parsed, dict) and "stderr" not in parsed:
            parsed["stderr"] = err_txt
        return proc.returncode or 0, parsed
    except Exception:
        return proc.returncode or 1, {"ok": False, "stdout": out_txt, "stderr": err_txt}


async def handle_profile_open(request: web.Request, *, launch_defaults: bool = False) -> web.Response:
    """POST /profile/open - Launches a Chrome profile on interactive WinSta0\\Default desktop (enforces MAX_AGENT_PROFILES=3)."""
    desktop_name = _get_current_desktop_name()
    if desktop_name.lower() != "default":
        return web.json_response(
            {
                "ok": False,
                "code": "NON_INTERACTIVE_DESKTOP",
                "desktop": desktop_name,
                "error": (
                    f"Bridge daemon is running in an isolated desktop ({desktop_name}). "
                    "Double-click Start_Gemini_Session.bat on Desktop to run on WinSta0\\Default."
                ),
            },
            status=409,
        )
    try:
        body = await request.json()
    except Exception:
        body = {}

    if launch_defaults:
        body.setdefault("profile", "Profile 8")
        body.setdefault("url", "https://aistudio.google.com/prompts/new_chat")
    profile = body.get("profile")
    if not profile:
        return web.json_response({"ok": False, "error": "Missing 'profile' parameter"}, status=400)

    is_setup = bool(body.get("setup"))
    requested_max = int(body.get("max_open", MAX_AGENT_PROFILES))
    clamped_max = max(1, min(requested_max, MAX_AGENT_PROFILES))
    cmd_args = ["open", str(profile), "--local", "--max-open", str(clamped_max)]
    if body.get("url"):
        cmd_args += ["--url", str(body["url"])]
    req_timeout = float(body.get("timeout", 18.0))
    cmd_args += ["--timeout", str(req_timeout)]
    if body.get("no_wait"):
        cmd_args.append("--no-wait")
    if is_setup:
        cmd_args.append("--setup")
    if body.get("auto_close_idle"):
        cmd_args.append("--auto-close-idle")

    lock = request.app[ADMISSION_LOCK]
    token = None
    if not is_setup:
        await reconcile_agent_tabs()
        async with lock:
            if any(slot == (str(profile), False) for slot in request.app[PENDING_SLOTS].values()):
                return web.json_response({"ok": False, "code": "PROFILE_LAUNCH_PENDING"}, status=409)
            token = reserve_slot(request, str(profile), tab=False)
            if token is None:
                return capacity_error(request)

    try:
        rc, res = await _run_rotator_cmd(cmd_args, timeout=max(10.0, req_timeout + 10.0))
        if rc == 0 and res.get("ok") and not res.get("already_open") and not is_setup:
            launched_dir = str(res.get("dir_name") or profile)
            register_agent_launched_profile(launched_dir, owner=str(body.get("owner") or "profile_open"))
    finally:
        if token is not None:
            async with lock:
                request.app[PENDING_SLOTS].pop(token, None)

    res_code = res.get("code") if isinstance(res, dict) else None
    if rc == 0:
        status_code = 200
    elif res_code == "AGENT_CAPACITY_REACHED":
        status_code = 429
    elif res_code == "MAX_OPEN_PROFILES_REACHED":
        status_code = 409
    else:
        status_code = 500
    return web.json_response(res, status=status_code)


async def handle_profile_close(request: web.Request) -> web.Response:
    """POST /profile/close - Safely closes a single Chrome profile's agent-owned tabs (never closes user windows/tabs)."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    profile = body.get("profile")
    if not profile:
        return web.json_response({"ok": False, "error": "Missing 'profile' parameter"}, status=400)

    req_timeout = float(body.get("timeout", 10.0))
    cmd_args = ["close", str(profile), "--timeout", str(req_timeout)]
    if body.get("force"):
        cmd_args.append("--force")

    rc, res = await _run_rotator_cmd(cmd_args, timeout=max(10.0, req_timeout + 8.0))
    if rc == 0 and isinstance(res, dict) and res.get("remaining_tabs", 0) == 0:
        release_agent_launched_profile(str(res.get("dir_name") or profile), clear_tabs=True)
    res_code = res.get("code") if isinstance(res, dict) else None
    if rc == 0:
        status_code = 200
    elif res_code in ("PERSONAL_TABS_PROTECTED", "USER_TAB_PROTECTED"):
        status_code = 409
    else:
        status_code = 500
    return web.json_response(res, status=status_code)


async def handle_profile_rotate(request: web.Request) -> web.Response:
    """POST /profile/rotate - Closes current profile cleanly and opens target/--auto next on WinSta0\\Default."""
    desktop_name = _get_current_desktop_name()
    if desktop_name.lower() != "default":
        return web.json_response(
            {
                "ok": False,
                "code": "NON_INTERACTIVE_DESKTOP",
                "desktop": desktop_name,
                "error": (
                    f"Bridge daemon is running in an isolated desktop ({desktop_name}). "
                    "Double-click Start_Gemini_Session.bat on Desktop to run on WinSta0\\Default."
                ),
            },
            status=409,
        )
    try:
        body = await request.json()
    except Exception:
        body = {}

    cmd_args = ["rotate"]
    if body.get("close"):
        cmd_args += ["--close", str(body["close"])]
    if body.get("open"):
        cmd_args += ["--open", str(body["open"])]
    if body.get("auto"):
        cmd_args.append("--auto")
    if body.get("max_open") is not None:
        cmd_args += ["--max-open", str(int(body["max_open"]))]
    if body.get("force"):
        cmd_args.append("--force")
    req_timeout = float(body.get("timeout", 18.0))
    cmd_args += ["--timeout", str(req_timeout)]

    rc, res = await _run_rotator_cmd(cmd_args, timeout=max(15.0, req_timeout + 15.0))
    return web.json_response(res, status=(200 if rc == 0 else 500))


async def handle_profile_shortcuts(request: web.Request) -> web.Response:
    """POST /profile/shortcuts - Regenerates Windows .lnk profile shortcuts."""
    rc, res = await _run_rotator_cmd(["generate-shortcuts"], timeout=20.0)
    return web.json_response(res, status=(200 if rc == 0 else 500))


async def handle_shutdown(request: web.Request) -> web.Response:
    """POST /shutdown - Cleanly stops the daemon so Start_Gemini_Session.bat can replace it."""
    loop = asyncio.get_running_loop()
    loop.call_later(0.2, lambda: os._exit(0))
    return web.json_response({"ok": True, "shutting_down": True})


def create_app() -> web.Application:
    """Constructs the aiohttp application with CORS support."""
    app = web.Application()
    app[ADMISSION_LOCK] = asyncio.Lock()
    app[PENDING_SLOTS] = {}
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/", lambda r: web.Response(text="Browser operator is running online.\n", content_type="text/plain"))
    app.router.add_get("/health", handle_health)
    app.router.add_get("/status", handle_status)
    app.router.add_get("/resources", handle_resources)
    app.router.add_post("/resources/register_tab", handle_register_tab)
    app.router.add_post("/resources/release_tab", handle_release_tab)
    app.router.add_post("/resources/release_profile", handle_release_profile)
    app.router.add_get("/locks", handle_locks)
    app.router.add_get("/ping_profile", handle_ping_profile)
    app.router.add_post("/ping_profile", handle_ping_profile)
    app.router.add_post("/command", handle_command)
    app.router.add_post("/rotate", handle_rotate)
    app.router.add_post("/launch", handle_launch)
    app.router.add_post("/profile/open", handle_profile_open)
    app.router.add_post("/profile/close", handle_profile_close)
    app.router.add_post("/profile/rotate", handle_profile_rotate)
    app.router.add_post("/profile/shortcuts", handle_profile_shortcuts)
    app.router.add_post("/shutdown", handle_shutdown)
    app.router.add_post("/lock/acquire", handle_acquire_lock)
    app.router.add_post("/lock/renew", handle_renew_lock)
    app.router.add_post("/lock/release", handle_release_lock)

    # Enable basic CORS for local browser access
    async def add_cors(request: web.Request, response: web.Response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"

    app.on_response_prepare.append(add_cors)
    return app


if __name__ == "__main__":
    desktop_name = _get_current_desktop_name()
    rot_state = "ENABLED" if desktop_name.lower() == "default" else "DISABLED (start via Start_Gemini_Session.bat)"
    print("============================================================")
    print(" ANTIGRAVITY ARGON BRIDGE DAEMON STARTING")
    print(f" Running on http://{HOST}:{PORT} (WebSocket at ws://{HOST}:{PORT}/ws)")
    print(f" Desktop: WinSta0\\{desktop_name} | Interactive Rotation: {rot_state}")
    print("============================================================")
    app = create_app()
    web.run_app(app, host=HOST, port=PORT, access_log=None)
