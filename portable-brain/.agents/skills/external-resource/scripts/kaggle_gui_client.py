#!/usr/bin/env python3
"""
Kaggle Connect GUI Client (/external-resource live bridge)
Queries and controls active Kaggle Connect Workbench GUI sessions on 127.0.0.1:7895.

Commands:
  status                    Check if the Kaggle Connect GUI server & sessions are active
  tail [--session ID]       Print recent ANSI-cleaned terminal output + OAuth links
  exec "<cmd>" [--wait 3]   Send command to the active Kaggle GUI terminal & print delta
  ls [path]                 List files in /kaggle/working or /tmp via flh.fs
  read <path>               Read text file from the active Kaggle session
"""

import argparse
import base64
import json
import sys
import urllib.error
import urllib.request

DEFAULT_BASE = "http://127.0.0.1:7895"


def _http_json(method: str, url: str, payload=None, timeout: int = 25):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as he:
        body = he.read().decode("utf-8", errors="replace")
        return he.code, {"error": body}
    except Exception as exc:
        return -1, {"error": str(exc)}


def _resolve_session_id(base: str, requested_id: str | None) -> str:
    code, data = _http_json("GET", f"{base}/api/kaggle/terminal/sessions")
    if code != 200:
        raise RuntimeError(f"Kaggle GUI server unreachable at {base}: {data.get('error')}")
    sessions = data.get("sessions", [])
    if not sessions:
        raise RuntimeError("No active Kaggle Connect GUI terminal sessions running.")
    if requested_id:
        for s in sessions:
            if s["session_id"] == requested_id:
                return requested_id
        raise RuntimeError(f"Session '{requested_id}' not found. Active: {[s['session_id'] for s in sessions]}")
    for s in sessions:
        if s.get("status") == "connected":
            return s["session_id"]
    return sessions[0]["session_id"]


def main():
    parser = argparse.ArgumentParser(description="Inspect and assist active Kaggle Connect GUI sessions.")
    parser.add_argument("--base", default=DEFAULT_BASE, help="Base URL of colab_manager (default http://127.0.0.1:7895)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="Check active Kaggle GUI terminal & /kaggle/v1 sessions")

    p_tail = sub.add_parser("tail", help="Read recent terminal output")
    p_tail.add_argument("--session", default=None)
    p_tail.add_argument("--lines", type=int, default=80)

    p_exec = sub.add_parser("exec", help="Run a command in the active Kaggle GUI terminal")
    p_exec.add_argument("command")
    p_exec.add_argument("--session", default=None)
    p_exec.add_argument("--wait", type=float, default=4.0)

    p_ls = sub.add_parser("ls", help="List files on the active Kaggle session")
    p_ls.add_argument("path", nargs="?", default="/kaggle/working")
    p_ls.add_argument("--session", default=None)

    p_read = sub.add_parser("read", help="Read a text file from the active Kaggle session")
    p_read.add_argument("path")
    p_read.add_argument("--session", default=None)

    args = parser.parse_args()
    base = args.base.rstrip("/")

    if args.cmd == "status":
        code_t, term_data = _http_json("GET", f"{base}/api/kaggle/terminal/sessions")
        if code_t != 200:
            print(json.dumps({"gui_online": False, "base_url": base, "error": term_data.get("error")}, indent=2))
            sys.exit(1)
        _, bridge_data = _http_json("GET", f"{base}/api/kaggle/status")
        print(json.dumps({
            "gui_online": True,
            "workbench_url": f"{base}/kaggle-terminal",
            "terminal_sessions": term_data.get("sessions", []),
            "kaggle_v1_bridge": bridge_data,
        }, indent=2))
        return

    try:
        sid = _resolve_session_id(base, getattr(args, "session", None))
    except RuntimeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        sys.exit(1)

    if args.cmd == "tail":
        code, data = _http_json("GET", f"{base}/api/kaggle/terminal/{sid}/tail?lines={args.lines}")
        if code != 200:
            print(json.dumps(data, indent=2))
            sys.exit(1)
        print(f"=== SESSION {sid} ({data.get('status')}) ===")
        print(data.get("tail", ""))
        if data.get("detected_oauth_urls"):
            print("\n=== DETECTED OAUTH URLS ===")
            for u in data["detected_oauth_urls"]:
                print(u)

    elif args.cmd == "exec":
        code, data = _http_json(
            "POST",
            f"{base}/api/kaggle/terminal/{sid}/exec",
            {"command": args.command, "wait_seconds": args.wait, "append_newline": True},
            timeout=int(args.wait) + 15,
        )
        if code != 200:
            print(json.dumps(data, indent=2))
            sys.exit(1)
        print(data.get("output", ""))

    elif args.cmd == "ls":
        code, data = _http_json("POST", f"{base}/api/kaggle/terminal/{sid}/fs", {"op": "list", "path": args.path})
        if code != 200:
            print(json.dumps(data, indent=2))
            sys.exit(1)
        print(f"Path: {data.get('path')}")
        for e in data.get("entries", []):
            kind = "DIR " if e.get("is_dir") else f"{e.get('size', 0):>9} B"
            print(f"  {kind}  {e.get('name')}")

    elif args.cmd == "read":
        code, data = _http_json("POST", f"{base}/api/kaggle/terminal/{sid}/fs", {"op": "read", "path": args.path})
        if code != 200:
            print(json.dumps(data, indent=2))
            sys.exit(1)
        if data.get("is_binary"):
            print(f"[Binary file: {data.get('path')} ({data.get('size')} bytes)]")
            return
        print(base64.b64decode(data.get("b64", "")).decode("utf-8", errors="replace"))


if __name__ == "__main__":
    main()
