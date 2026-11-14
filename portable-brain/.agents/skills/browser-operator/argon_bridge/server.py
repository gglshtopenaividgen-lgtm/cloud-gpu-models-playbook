#!/usr/bin/env python3
"""server.py - Local WebSocket & REST Bridge Daemon for Antigravity & Chrome MV3 Extension.

Runs on http://127.0.0.1:9229.
Provides:
  - WebSocket at /ws for Manifest V3 Chrome Extension instances across user profiles.
  - REST API at /status, /command, /rotate, /launch for Antigravity agents & PySide6 GUI.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
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

# Connected extension WebSocket clients: { client_id: { "ws": WebSocketResponse, "email": str, "dir_name": str, "tabs": list } }
CONNECTED_CLIENTS: Dict[str, Dict[str, Any]] = {}
# Pending request futures: { req_id: asyncio.Future }
PENDING_REQUESTS: Dict[str, asyncio.Future] = {}


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

    res = {
        "status": "online",
        "port": PORT,
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
) -> dict[str, Any]:
    """Routes and sends an action command to the freshest matching or available extension."""
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
    payload = {"id": req_id, "action": action, **(params or {})}

    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    PENDING_REQUESTS[req_id] = fut

    try:
        await ws.send_json(payload)
        res = await asyncio.wait_for(fut, timeout=timeout)
        return res
    except asyncio.TimeoutError:
        PENDING_REQUESTS.pop(req_id, None)
        return {"ok": False, "error": f"Command '{action}' timed out after {timeout}s"}
    except Exception as e:
        PENDING_REQUESTS.pop(req_id, None)
        return {"ok": False, "error": str(e)}


async def handle_command(request: web.Request) -> web.Response:
    """POST /command - Executes action on target extension client."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON body"}, status=400)

    action = body.get("action")
    if not action:
        return web.json_response({"ok": False, "error": "Missing 'action' parameter"}, status=400)

    preferred_profile = body.get("profile") or body.get("email")
    params = body.get("params", {})
    timeout = float(body.get("timeout", 30.0))

    result = await send_extension_command(action, params, preferred_profile=preferred_profile, timeout=timeout)
    return web.json_response(result)


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
    """POST /launch - Launches target profile Chrome window with the extension."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    target = body.get("profile", "Profile 8")
    target_url = body.get("url", "https://aistudio.google.com/prompts/new_chat")

    try:
        profile_manager.launch_profile_window(target, target_url)
        return web.json_response({"ok": True, "launched": target, "url": target_url})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


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

    prof, err = profile_lock_manager.acquire_profile_lease(
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


def create_app() -> web.Application:
    """Constructs the aiohttp application with CORS support."""
    app = web.Application()
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/", lambda r: web.Response(text="Browser operator is running online.\n", content_type="text/plain"))
    app.router.add_get("/status", handle_status)
    app.router.add_get("/locks", handle_locks)
    app.router.add_get("/ping_profile", handle_ping_profile)
    app.router.add_post("/ping_profile", handle_ping_profile)
    app.router.add_post("/command", handle_command)
    app.router.add_post("/rotate", handle_rotate)
    app.router.add_post("/launch", handle_launch)
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
    print(f"============================================================")
    print(f" ANTIGRAVITY ARGON BRIDGE DAEMON STARTING")
    print(f" Running on http://{HOST}:{PORT} (WebSocket at ws://{HOST}:{PORT}/ws)")
    print(f"============================================================")
    app = create_app()
    web.run_app(app, host=HOST, port=PORT, access_log=None)
