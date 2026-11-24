#!/usr/bin/env python3
"""gemini_brain_driver.py - Autonomous Driver for gemini.google.com.

Drives Gemini 4 Argon with High Thinking, multi-turn follow-ups, parallel subagent chats,
Deep Research mode, and autonomous chat cleanup/deletion.
Designed and verified by Gemini 4 Argon.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))
from stealth_input import dispatch_stealth_click, dispatch_stealth_type, RICH_HARVEST_JS
try:
    import popup_healer
except ImportError:
    popup_healer = None

BRIDGE_URL = "http://127.0.0.1:9229"
REGISTRY_PATH = Path(__file__).parent / "gemini_sessions_registry.json"
LOCKS_FILE = Path(__file__).parent / "bridge_profile_locks.json"
LOCKS_LOCK_FILE = Path(__file__).parent / "bridge_profile_locks.json.lock"

try:
    from filelock import FileLock, Timeout as FileLockTimeout
    HAS_FILELOCK = True
except ImportError:
    HAS_FILELOCK = False
    FileLock = None
    FileLockTimeout = None

from contextlib import contextmanager


@contextmanager
def profile_lock_context(timeout: float = 10.0):
    """Process-safe file lock around bridge_profile_locks.json to eliminate Windows NTFS race conditions."""
    if HAS_FILELOCK and FileLock is not None:
        lock = FileLock(str(LOCKS_LOCK_FILE), timeout=timeout)
        try:
            with lock:
                yield
        except Exception:
            yield
    else:
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
        try:
            yield
        finally:
            if acquired and fallback.exists():
                try:
                    fallback.unlink()
                except Exception:
                    pass


MODEL_SPECS: Dict[str, Dict[str, Any]] = {
    "neon": {
        "key": "neon",
        "label": "4 Neon",
        "test_id": "bard-mode-option-e6fa609c3fa255c0",
        "supports_thinking": True,
        "aliases": ("4 neon", "neon", "deeper analysis", "3.1 pro", "pro"),
    },
    "argon": {
        "key": "argon",
        "label": "4 Argon",
        "test_id": "bard-mode-option-argon",
        "supports_thinking": True,
        "deprecated_on_web": True,
        "aliases": ("4 argon", "argon", "code & analysis"),
    },
    "hydrogen": {
        "key": "hydrogen",
        "label": "4 Hydrogen",
        "test_id": "bard-mode-option-56fdd199312815e2",
        "supports_thinking": True,
        "blocked": True,
        "aliases": ("4 hydrogen", "hydrogen", "everyday help"),
    },
    "flash-lite": {
        "key": "flash-lite",
        "label": "3.5 Flash-Lite",
        "test_id": "bard-mode-option-8c46e95b1a07cecc",
        "supports_thinking": False,
        "aliases": ("3.5 flash-lite", "flash-lite", "flash lite", "quick answers"),
    },
    "carbon": {
        "key": "carbon",
        "label": "4 Carbon",
        "test_id": "bard-mode-option-upsell_MODE_CATEGORY_ULTRA",
        "supports_thinking": True,
        "blocked": True,
        "aliases": ("4 carbon", "carbon", "most complex work"),
    },
}


def resolve_model_spec(model: Optional[str] = None) -> Dict[str, Any]:
    """Resolve user-friendly model strings ('4 Neon', 'neon', etc.) to canonical UI metadata."""
    raw = (model or "4 Neon").strip()
    low = raw.lower()
    for spec in MODEL_SPECS.values():
        if low == spec["key"] or low == spec["label"].lower() or any(a in low for a in spec["aliases"]):
            return dict(spec)
    return {
        "key": low,
        "label": raw,
        "test_id": "",
        "supports_thinking": True,
        "aliases": (low,),
    }


def resolve_execution_route(
    model: Optional[str] = None,
    thinking: Optional[str] = None,
    mode: str = "chat",
    deep_research: bool = False,
) -> Dict[str, Any]:
    """
    Canonical Gemini Web routing policy:
    - All Gemini Web modes (Chat, Deep Research, Task) route to `4 Neon` + `High` Thinking.
    - `4 Hydrogen` and `4 Carbon` are HARD BLOCKED in browser bridges.
    - Legacy `4 Argon` requests on Gemini Web auto-route to `4 Neon` (4 Argon lives on AI Studio Playground).
    """
    mode_norm = (mode or "chat").strip().lower()
    if mode_norm not in ("chat", "task"):
        mode_norm = "chat"

    # Deep research chip lives strictly inside Chat mode (+ -> More tools -> Deep research)
    if deep_research and mode_norm != "chat":
        mode_norm = "chat"

    chosen_raw = (model or "4 Neon").strip()
    spec = resolve_model_spec(chosen_raw)

    if spec.get("blocked"):
        raise ValueError(
            f"Model '{spec['label']}' is blocked in browser bridges. "
            "4 Hydrogen is reserved for local Antigravity coding and 4 Carbon requires Ultra. "
            "Use '4 Neon' on Gemini Web or 'gemini-4-argon' / 'gemini-4-neon' on AI Studio Playground."
        )

    if spec.get("deprecated_on_web"):
        print(
            "[GeminiDriver] Note: 4 Argon was removed from Gemini Web; routing Gemini Web request to '4 Neon' High "
            "(use AI Studio Playground for 4 Argon).",
            file=sys.stderr,
        )
        spec = dict(MODEL_SPECS["neon"])

    if not spec.get("supports_thinking", True):
        resolved_thinking = ""
    else:
        t = (thinking or "High").strip()
        resolved_thinking = t.title() if t else "High"

    return {
        "mode": mode_norm,
        "model": spec["label"],
        "model_key": spec["key"],
        "test_id": spec.get("test_id", ""),
        "supports_thinking": bool(spec.get("supports_thinking", True)),
        "thinking": resolved_thinking,
    }


# Injected DOM helper library
HELPER_JS = """
window.__geminiDriver = {
    sleep: ms => new Promise(r => setTimeout(r, ms)),
    smartClick: async function(el) {
        if (!el) return false;
        el.scrollIntoView({ behavior: 'instant', block: 'center' });
        await this.sleep(100);
        const rect = el.getBoundingClientRect();
        const evOpts = { bubbles: true, cancelable: true, view: window, clientX: rect.x + rect.width / 2, clientY: rect.y + rect.height / 2 };
        el.dispatchEvent(new MouseEvent('pointerdown', evOpts));
        el.dispatchEvent(new MouseEvent('mousedown', evOpts));
        el.dispatchEvent(new MouseEvent('pointerup', evOpts));
        el.dispatchEvent(new MouseEvent('mouseup', evOpts));
        el.dispatchEvent(new MouseEvent('click', evOpts));
        return true;
    },
    smartHover: async function(el) {
        if (!el) return false;
        el.scrollIntoView({ behavior: 'instant', block: 'center' });
        await this.sleep(80);
        const rect = el.getBoundingClientRect();
        const evOpts = { bubbles: true, cancelable: true, view: window, clientX: rect.x + rect.width / 2, clientY: rect.y + rect.height / 2 };
        el.dispatchEvent(new MouseEvent('pointerenter', evOpts));
        el.dispatchEvent(new MouseEvent('mouseenter', evOpts));
        el.dispatchEvent(new MouseEvent('mouseover', evOpts));
        return true;
    },
    findByText: function(selector, regexPattern, root = document) {
        const re = new RegExp(regexPattern, 'i');
        const nodes = Array.from(root.querySelectorAll(selector));
        return nodes.find(el => {
            const t = el.innerText || el.getAttribute('aria-label') || el.getAttribute('data-test-id') || '';
            return re.test(t.trim());
        }) || null;
    },
    findOverlayItem: function(regexPattern) {
        const overlays = Array.from(document.querySelectorAll('.cdk-overlay-container, .cdk-overlay-pane, .cdk-overlay-popover, gem-menu, [role="menu"], [role="listbox"], mat-dialog-container, bard-mode-switcher'));
        for (const ov of overlays) {
            const found = this.findByText('gem-menu-item, gem-menu-item-content, [role="menuitem"], [role="option"], mat-option, button, span, div', regexPattern, ov);
            if (found) return found;
        }
        return this.findByText('gem-menu-item, [role="menuitem"], .mat-mdc-menu-item', regexPattern, document);
    },
    findSubmitButton: function() {
        const isVisEnabled = (el) => {
            if (!el || el.disabled || el.getAttribute('aria-disabled') === 'true') return false;
            const r = el.getBoundingClientRect();
            const s = window.getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
        };
        const explicitSelectors = [
            'button[aria-label="Send message"]',
            'gem-icon-button.send-button button',
            'button[aria-label*="Send" i]',
            'button[aria-label*="Submit" i]',
            'button[aria-label*="Start task" i]',
            'button[aria-label*="Run" i]',
            'button[data-test-id*="send" i]',
            'button[data-test-id*="submit" i]',
            'button.send-button',
            'button.submit-button'
        ];
        for (const sel of explicitSelectors) {
            const matches = Array.from(document.querySelectorAll(sel)).filter(isVisEnabled);
            if (matches.length > 0) {
                return matches[matches.length - 1];
            }
        }
        // Fallback for Task Mode circular purple up-arrow button: rightmost enabled non-mic icon button in bottom half of composer
        const box = document.querySelector('input-area-v2, .input-area-container, input-container, .text-input-field, form');
        if (!box) return null;
        const boxRect = box.getBoundingClientRect();
        const midY = boxRect.top + boxRect.height * 0.4;
        const excludedRe = /microphone|mic\b|voice|dictate|live|audio|upload|tool|attach|add\b|menu|picker|mode|neon|argon|hydrogen|flash|pro|expand|fullscreen|collapse|maximize|close|dismiss|stop/i;
        const candidates = Array.from(box.querySelectorAll('button')).filter(btn => {
            if (!isVisEnabled(btn)) return false;
            const meta = ((btn.innerText || '') + ' ' + (btn.getAttribute('aria-label') || '') + ' ' + (btn.getAttribute('data-test-id') || '') + ' ' + (btn.getAttribute('mattooltip') || '')).trim();
            if (excludedRe.test(meta)) return false;
            const r = btn.getBoundingClientRect();
            return r.bottom >= midY;
        });
        if (candidates.length === 0) return null;
        candidates.sort((a, b) => {
            const ra = a.getBoundingClientRect();
            const rb = b.getBoundingClientRect();
            if (Math.abs(rb.right - ra.right) > 4) return rb.right - ra.right;
            return rb.bottom - ra.bottom;
        });
        return candidates[0];
    }
};
"""


class GeminiBrainDriver:
    """Controls gemini.google.com via the local Argon Bridge."""

    def __init__(self, bridge_url: str = BRIDGE_URL, default_profile: Optional[str] = None):
        self.bridge_url = bridge_url
        self.default_profile = default_profile
        self.tab_id: Optional[int] = None
        self.registry = self._load_registry()

    def _load_registry(self) -> Dict[str, Any]:
        if REGISTRY_PATH.exists():
            try:
                with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_registry(self) -> None:
        try:
            with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
                json.dump(self.registry, f, indent=2)
        except Exception as e:
            print(f"[GeminiDriver] Warning saving registry: {e}", file=sys.stderr)

    @staticmethod
    def _get_current_desktop_name() -> str:
        if sys.platform != "win32":
            return "Default"
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            kernel32.GetCurrentThreadId.restype = wintypes.DWORD
            user32.GetThreadDesktop.argtypes = [wintypes.DWORD]
            user32.GetThreadDesktop.restype = wintypes.HANDLE
            user32.GetUserObjectInformationW.argtypes = [
                wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
            ]
            user32.GetUserObjectInformationW.restype = wintypes.BOOL
            hdesk = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
            buf = ctypes.create_unicode_buffer(256)
            needed = wintypes.DWORD()
            ok = hdesk and user32.GetUserObjectInformationW(hdesk, 2, buf, ctypes.sizeof(buf), ctypes.byref(needed))
            if ok and buf.value:
                return buf.value
        except Exception:
            pass
        return "unknown"

    def ensure_bridge_running(self) -> bool:
        """Checks GET /health -> GET /status with retries; refuses rogue exebox daemon launches."""
        for attempt in range(5):
            for ep in ("/health", "/status"):
                try:
                    req = urllib.request.Request(f"{self.bridge_url}{ep}", method="GET")
                    with urllib.request.urlopen(req, timeout=2.5) as resp:
                        if resp.status == 200:
                            return True
                except urllib.error.HTTPError as e:
                    if e.code == 404 and ep == "/health":
                        continue
                except Exception:
                    break
            if attempt < 4:
                time.sleep(0.5)

        desktop = self._get_current_desktop_name()
        if sys.platform == "win32" and desktop.lower() != "default" and os.environ.get("AGY_ALLOW_HEADLESS_BRIDGE") != "1":
            print(
                f"[GeminiDriver] Refusing to start non-interactive bridge daemon in WinSta0\\{desktop}. "
                "Start C:\\Users\\Flh\\Desktop\\Start_Gemini_Session.bat on Desktop.",
                file=sys.stderr,
            )
            return False

        print("[GeminiDriver] Bridge daemon not detected. Launching server.py daemon...")
        server_py = Path(__file__).parent / "server.py"
        subprocess.Popen([sys.executable, str(server_py)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(15):
            time.sleep(0.4)
            for ep in ("/health", "/status"):
                try:
                    req = urllib.request.Request(f"{self.bridge_url}{ep}", method="GET")
                    with urllib.request.urlopen(req, timeout=2.0) as resp:
                        if resp.status == 200:
                            print("[GeminiDriver] Bridge daemon started successfully.")
                            return True
                except Exception:
                    continue
        print("[GeminiDriver] Warning: Bridge daemon failed to respond within 6 seconds.", file=sys.stderr)
        return False

    def _ensure_daemon_running(self) -> None:
        self.ensure_bridge_running()

    @staticmethod
    def _is_stale_tab_error(res_or_err: Any) -> bool:
        """Checks if response or error message indicates a stale, missing, or closed tab."""
        if not res_or_err:
            return False
        if isinstance(res_or_err, dict):
            err_str = str(res_or_err.get("error", ""))
            msg_str = str(res_or_err.get("message", ""))
            full_str = f"{err_str} {msg_str} {res_or_err.get('code', '')}".lower()
        else:
            full_str = str(res_or_err).lower()
        return (
            "no tab with given id" in full_str
            or "tab not found" in full_str
            or "target closed" in full_str
        )

    def _call_api_raw(
        self,
        endpoint: str,
        payload: Dict[str, Any] | None = None,
        method: str = "POST",
        timeout: float = 30.0,
        profile: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._ensure_daemon_running()
        url = f"{self.bridge_url}{endpoint}"
        prof = profile or self.default_profile
        if payload and prof and "profile" not in payload:
            payload["profile"] = prof
        data = json.dumps(payload).encode("utf-8") if payload else None
        headers = {"Content-Type": "application/json"} if payload else {}
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as res:
                return json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read().decode("utf-8"))
            except Exception:
                return {"ok": False, "error": f"HTTP {e.code}: {e.reason}", "code": e.code}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _get_owned_tab_ids(self, profile: Optional[str] = None) -> set[str]:
        """Queries bridge GET /resources to obtain strictly agent-owned tab IDs for the profile."""
        prof = profile or self.default_profile
        res = self._call_api_raw("/resources", payload=None, method="GET", timeout=5.0)
        if not (isinstance(res, dict) and res.get("ok")):
            return set()
        owned_map = res.get("owned_tabs") or {}
        if prof:
            return {str(k) for k in (owned_map.get(prof) or {}).keys()}
        out: set[str] = set()
        for prof_tabs in owned_map.values():
            if isinstance(prof_tabs, dict):
                out.update(str(k) for k in prof_tabs.keys())
        return out

    def re_discover_gemini_tab(self, profile: Optional[str] = None) -> Optional[int]:
        """Calls LIST_TABS strictly for target profile, finds an AGENT-OWNED gemini.google.com tab, and updates self.tab_id."""
        prof = profile or self.default_profile
        owned_ids = self._get_owned_tab_ids(profile=prof)
        if not owned_ids:
            return None
        payload: Dict[str, Any] = {"action": "LIST_TABS"}
        if prof:
            payload["profile"] = prof
        tabs_res = self._call_api_raw("/command", payload, profile=prof)
        gemini_tabs = [
            t for t in tabs_res.get("tabs", [])
            if str(t.get("id")) in owned_ids and "gemini.google.com" in t.get("url", "")
        ]
        if not gemini_tabs:
            return None
        active_tab = next((t for t in gemini_tabs if t.get("active")), gemini_tabs[0])
        new_tab_id = active_tab.get("id")
        if new_tab_id:
            self.tab_id = new_tab_id
            for sdata in self.registry.values():
                if sdata.get("profile") == prof or (not sdata.get("profile") and not prof):
                    sdata["tab_id"] = new_tab_id
            self._save_registry()
            return new_tab_id
        return None

    def _call_api(
        self,
        endpoint: str,
        payload: Dict[str, Any] | None = None,
        method: str = "POST",
        timeout: float = 30.0,
        profile: Optional[str] = None,
        _can_heal: bool = True,
    ) -> Dict[str, Any]:
        prof = profile or self.default_profile
        res = self._call_api_raw(endpoint, payload=payload, method=method, timeout=timeout, profile=prof)

        # CDP Command / Tab operation dynamic self-healing (capped at exactly 1 retry)
        if _can_heal and payload and payload.get("action") in ("CDP_COMMAND", "ATTACH_TAB") and self._is_stale_tab_error(res):
            print("[SELF-HEAL] Stale tab_id on profile. Re-discovering Gemini tab...")
            new_tab_id = self.re_discover_gemini_tab(profile=prof)
            if new_tab_id and "params" in payload and "tabId" in payload["params"]:
                self.tab_id = new_tab_id
                payload["params"]["tabId"] = new_tab_id
                return self._call_api_raw(endpoint, payload=payload, method=method, timeout=timeout, profile=prof)

        return res

    def get_open_gemini_tab(self, profile: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Finds an existing AGENT-OWNED open Gemini tab for the target profile (never hijacks user tabs)."""
        prof = profile or self.default_profile
        owned_ids = self._get_owned_tab_ids(profile=prof)
        if not owned_ids:
            return None
        payload = {"action": "LIST_TABS"}
        if prof:
            payload["profile"] = prof
        res = self._call_api_raw("/command", payload, profile=prof)
        gemini_tabs = [
            t for t in res.get("tabs", [])
            if str(t.get("id")) in owned_ids and "gemini.google.com" in t.get("url", "")
        ]
        if not gemini_tabs:
            return None
        return next((t for t in gemini_tabs if t.get("active")), gemini_tabs[0])

    def call_cdp(
        self,
        tab_id: int,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 30.0,
        profile: Optional[str] = None,
        _retry: bool = False,
    ) -> Dict[str, Any]:
        """Executes a CDP command against the tab with dynamic tab self-healing."""
        prof = profile or self.default_profile
        target_tab = self.tab_id or tab_id
        cdp_payload: Dict[str, Any] = {
            "action": "CDP_COMMAND",
            "params": {"tabId": target_tab, "method": method},
            "timeout": timeout,
        }
        if params:
            cdp_payload["params"]["params"] = params
        if prof:
            cdp_payload["profile"] = prof

        res = self._call_api_raw("/command", cdp_payload, timeout=timeout + 5.0, profile=prof)
        if not _retry and self._is_stale_tab_error(res):
            print("[SELF-HEAL] Stale tab_id on profile. Re-discovering Gemini tab...")
            new_tab_id = self.re_discover_gemini_tab(profile=prof)
            if new_tab_id:
                self.tab_id = new_tab_id
                return self.call_cdp(new_tab_id, method, params=params, timeout=timeout, profile=prof, _retry=True)

        return res

    def execute_js(
        self,
        tab_id: int,
        js_code: str,
        timeout: float = 30.0,
        profile: Optional[str] = None,
        _retry: bool = False,
    ) -> Any:
        """Executes JavaScript inside the target tab via CDP Runtime.evaluate with dynamic tab self-healing."""
        target_tab = self.tab_id or tab_id
        full_code = f"(async function() {{\n{HELPER_JS}\n{js_code}\n}})()"
        payload = {
            "action": "EVAL_DOM",
            "params": {"tabId": target_tab, "code": full_code},
            "timeout": timeout,
        }
        prof = profile or self.default_profile
        if prof:
            payload["profile"] = prof
        res = self._call_api_raw(
            "/command",
            payload,
            timeout=timeout + 5.0,
            profile=prof,
        )

        if not _retry and self._is_stale_tab_error(res):
            print("[SELF-HEAL] Stale tab_id on profile. Re-discovering Gemini tab...")
            new_tab_id = self.re_discover_gemini_tab(profile=prof)
            if new_tab_id:
                self.tab_id = new_tab_id
                return self.execute_js(new_tab_id, js_code, timeout=timeout, profile=prof, _retry=True)

        if not isinstance(res, dict):
            return {"ok": False, "error": f"Invalid bridge response: {res}"}

        return res

    def inject_helper(self, tab_id: int, profile: Optional[str] = None) -> Dict[str, Any]:
        """Injects or re-verifies HELPER_JS inside the target tab context."""
        return self.execute_js(tab_id, "return (typeof window.__geminiDriver !== 'undefined');", profile=profile)

    def get_usage_limit(self, profile: Optional[str] = None) -> Dict[str, Any]:
        """Checks live Gemini usage limits in a clean background tab (gemini.google.com/usage)."""
        prof = profile or self.default_profile or "Profile 14"
        open_payload = {
            "action": "OPEN_TAB",
            "owner": "gemini_usage_check",
            "surface": "gemini_web",
            "agent_guarded": True,
            "params": {"url": "https://gemini.google.com/usage", "active": False},
        }
        if prof:
            open_payload["profile"] = prof

        open_res = self._call_api("/command", open_payload, profile=prof)
        tab_id = open_res.get("tabId")
        if not tab_id:
            return {"ok": False, "error": f"Failed to open usage tab on {prof}: {open_res}"}

        usage_data = {
            "ok": True,
            "profile": prof,
            "plan": "UNKNOWN",
            "current_usage_percent": None,
            "current_reset": None,
            "weekly_usage_percent": None,
            "weekly_reset": None,
            "should_rotate": False
        }

        try:
            for _ in range(10):
                time.sleep(0.7)
                check_code = """
                (() => {
                    const text = (document.body && document.body.innerText) ? document.body.innerText : '';
                    if (!text.includes('Usage limits') || !text.includes('% used')) {
                        return { ready: false };
                    }
                    const lines = text.split('\\n').map(l => l.trim()).filter(Boolean);
                    const usageIdx = lines.findIndex(l => l === 'Usage limits');
                    const relevantLines = usageIdx >= 0 ? lines.slice(usageIdx) : lines;

                    const pcts = [];
                    const resets = [];
                    for (const line of relevantLines) {
                        const mPct = line.match(/^(\\d+)%\\s*used$/i);
                        if (mPct) pcts.push(parseInt(mPct[1], 10));
                        const mReset = line.match(/^Resets?\\s*(?:at|on)?\\s*(.+)$/i);
                        if (mReset) resets.push(mReset[1]);
                    }

                    const isPro = relevantLines.some(l => l.toUpperCase() === 'PRO');
                    return {
                        ready: true,
                        plan: isPro ? 'PRO' : 'STANDARD',
                        currentUsagePercent: pcts[0] !== undefined ? pcts[0] : null,
                        currentReset: resets[0] || null,
                        weeklyUsagePercent: pcts[1] !== undefined ? pcts[1] : null,
                        weeklyReset: resets[1] || null
                    };
                })()
                """
                eval_payload = {
                    "action": "EVAL_DOM",
                    "params": {"tabId": tab_id, "code": check_code}
                }
                if prof:
                    eval_payload["profile"] = prof
                eval_res = self._call_api("/command", eval_payload, profile=prof)
                res_obj = eval_res.get("result")
                if res_obj and res_obj.get("ready"):
                    usage_data.update({
                        "plan": res_obj.get("plan"),
                        "current_usage_percent": res_obj.get("currentUsagePercent"),
                        "current_reset": res_obj.get("currentReset"),
                        "weekly_usage_percent": res_obj.get("weeklyUsagePercent"),
                        "weekly_reset": res_obj.get("weeklyReset")
                    })
                    curr_pct = res_obj.get("currentUsagePercent")
                    weekly_pct = res_obj.get("weeklyUsagePercent")
                    if (curr_pct is not None and curr_pct >= 85) or (weekly_pct is not None and weekly_pct >= 90):
                        usage_data["should_rotate"] = True
                    break
        finally:
            close_payload = {"action": "CLOSE_TAB", "agent_guarded": True, "params": {"tabId": tab_id}}
            if prof:
                close_payload["profile"] = prof
            self._call_api("/command", close_payload, profile=prof)

        return usage_data

    def take_screenshot(self, tab_id: int, save_path: str = "temp_read/gemini_live.png", profile: Optional[str] = None) -> str:
        """Captures a screenshot of the tab via CDP and saves to disk."""
        out_p = Path(save_path)
        if not out_p.is_absolute():
            out_p = Path("./") / out_p
        out_p.parent.mkdir(parents=True, exist_ok=True)

        prof = profile or self.default_profile
        # Ensure debugger is attached and tab is brought to front
        try:
            attach_payload = {"action": "ATTACH_TAB", "params": {"tabId": tab_id}}
            if prof:
                attach_payload["profile"] = prof
            self._call_api("/command", attach_payload, timeout=5.0, profile=prof)
            bring_payload = {"action": "CDP_COMMAND", "params": {"tabId": tab_id, "method": "Page.bringToFront"}}
            if prof:
                bring_payload["profile"] = prof
            self._call_api("/command", bring_payload, timeout=5.0, profile=prof)
        except Exception:
            pass

        cdp_payload = {
            "action": "CDP_COMMAND",
            "params": {
                "tabId": tab_id,
                "method": "Page.captureScreenshot",
                "params": {"format": "png"},
            },
        }
        if prof:
            cdp_payload["profile"] = prof
        res = self._call_api("/command", cdp_payload, timeout=15.0, profile=prof)
        b64_data = None
        if res and res.get("ok"):
            b64_data = res.get("result", {}).get("data") or res.get("data")

        if b64_data:
            import base64
            img_bytes = base64.b64decode(b64_data)
            out_p.write_bytes(img_bytes)
            print(f"[GeminiDriver] Screenshot saved: {out_p.as_posix()} ({len(img_bytes)} bytes)")
            return str(out_p.resolve())
        else:
            print(f"[GeminiDriver] Failed to capture screenshot: {res}", file=sys.stderr)
            return ""

    def _cdp_mouse_click(
        self, tab_id: int, x: float, y: float, profile: Optional[str] = None
    ) -> bool:
        """Dispatches a hardware-trusted CDP mouse click at (x, y) with fallback."""
        try:
            for event_type, click_count in [
                ("mouseMoved", 0),
                ("mousePressed", 1),
                ("mouseReleased", 1),
            ]:
                self.call_cdp(
                    tab_id,
                    "Input.dispatchMouseEvent",
                    params={
                        "type": event_type,
                        "x": float(x),
                        "y": float(y),
                        "button": "left" if event_type != "mouseMoved" else "none",
                        "buttons": 1 if event_type == "mousePressed" else 0,
                        "clickCount": click_count,
                    },
                    profile=profile,
                )
            return True
        except Exception:
            return False

    def _nudge_compositor(self, tab_id: int, profile: Optional[str] = None) -> None:
        """Triggers a tiny off-screen compositor paint so occluded/minimized tabs render Angular overlays without stealing focus."""
        try:
            self.call_cdp(
                tab_id,
                "Page.captureScreenshot",
                {"format": "jpeg", "quality": 1, "clip": {"x": 0, "y": 0, "width": 10, "height": 10, "scale": 1}},
                profile=profile,
            )
        except Exception:
            pass

    def wait_for_page_ready(
        self,
        tab_id: int,
        timeout_sec: float = 25.0,
        profile: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Waits up to timeout_sec for:
          - document.readyState === 'complete'
          - Prompt editor / rich-textarea AND mode picker button to mount & be visible
          - Auto-dismisses non-destructive dialogs/modals
        """
        start_ts = time.time()
        probe_js = r"""
        const isVis = (el) => {
            if (!el) return false;
            const r = el.getBoundingClientRect();
            const s = window.getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
        };

        // 1. Auto-dismiss non-destructive popups/dialogs (e.g. onboarding, promos)
        let dismissedModal = false;
        const dialogs = Array.from(document.querySelectorAll('mat-dialog-container, [role="dialog"]'));
        for (const dlg of dialogs) {
            if (!isVis(dlg)) continue;
            const dlgText = (dlg.innerText || '').toLowerCase();
            if (dlgText.includes('delete chat') || dlgText.includes('delete this chat')) continue;
            const closeBtn = Array.from(dlg.querySelectorAll('button')).find(b => {
                const t = ((b.innerText || '') + ' ' + (b.getAttribute('aria-label') || '')).toLowerCase();
                return /(dismiss|close|got it|not now|no thanks|skip|continue)/.test(t);
            });
            if (closeBtn && isVis(closeBtn)) {
                closeBtn.click();
                dismissedModal = true;
            }
        }

        // 2. Check auth redirect & document.readyState
        if (window.location.href.includes('accounts.google.com') || /\/signin/i.test(window.location.pathname)) {
            return { ready: false, needs_reauth: true, url: window.location.href };
        }
        const readyState = document.readyState;
        if (readyState !== 'complete') {
            return { ready: false, stage: 'document_loading', readyState, dismissedModal };
        }

        // 3. Check prompt editor mount
        const editor = document.querySelector(
            '.ql-editor, rich-textarea div[contenteditable="true"], div[role="textbox"][contenteditable="true"], textarea'
        );
        const editorReady = isVis(editor);

        // 4. Check mode picker button mount (zero-state handling)
        let pickerBtn = document.querySelector(
            'button[data-test-id="bard-mode-menu-button"], button.input-area-switch, button[aria-label*="mode picker" i], button[aria-label*="picker" i]'
        );
        if (!isVis(pickerBtn) && editorReady && editor) {
            editor.focus();
            try {
                document.execCommand('insertText', false, ' ');
            } catch (e) {}
            pickerBtn = document.querySelector(
                'button[data-test-id="bard-mode-menu-button"], button.input-area-switch, button[aria-label*="mode picker" i], button[aria-label*="picker" i]'
            );
        }
        const pickerReady = isVis(pickerBtn) || editorReady;

        return {
            ready: Boolean(editorReady && pickerReady),
            readyState,
            editorReady,
            pickerReady,
            dismissedModal,
            pickerLabel: pickerBtn ? (pickerBtn.getAttribute('aria-label') || '').trim() : null,
            pickerText: pickerBtn ? (pickerBtn.innerText || '').trim() : null
        };
        """

        last_res: Dict[str, Any] = {}
        while (time.time() - start_ts) < timeout_sec:
            try:
                res = self.execute_js(tab_id, probe_js, profile=profile)
                if isinstance(res, dict):
                    data = res.get("result") if res.get("ok") and isinstance(res.get("result"), dict) else res
                    last_res = data
                    if data.get("needs_reauth"):
                        return {
                            "ready": False,
                            "needs_reauth": True,
                            "url": data.get("url"),
                            "elapsed": round(time.time() - start_ts, 2),
                        }
                    if data.get("ready"):
                        return {
                            "ready": True,
                            "elapsed": round(time.time() - start_ts, 2),
                            **data,
                        }
            except Exception as exc:
                last_res = {"error": str(exc)}
            time.sleep(0.4)

        return {
            "ready": False,
            "elapsed": round(time.time() - start_ts, 2),
            "last_state": last_res,
        }

    def ensure_execution_mode(
        self,
        tab_id: int,
        mode: str = "chat",
        profile: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Ensures Gemini Web UI is on the target segmented mode ('chat' or 'task')
        via `.gem-segmented-button-action` buttons.
        """
        prof = profile or self.default_profile
        target_mode = (mode or "chat").strip().lower()
        if target_mode not in ("chat", "task"):
            return {"ok": False, "error": f"Unsupported mode '{mode}'. Use 'chat' or 'task'."}

        probe_mode_js = f"""
        return (() => {{
            const isVis = (el) => {{
                if (!el) return false;
                const r = el.getBoundingClientRect();
                const s = window.getComputedStyle(el);
                return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
            }};
            const btns = Array.from(document.querySelectorAll('.gem-segmented-button-action')).filter(isVis);
            const modes = btns.map(b => {{
                const wrap = b.closest('.gem-segmented-button');
                return {{
                    label: (b.innerText || b.getAttribute('aria-label') || '').trim().toLowerCase(),
                    selected: Boolean(wrap && wrap.classList.contains('gem-segmented-button-selected')),
                }};
            }});
            const targetBtn = btns.find(b => (b.innerText || b.getAttribute('aria-label') || '').trim().toLowerCase() === '{target_mode}');
            const already = Boolean(targetBtn && targetBtn.closest('.gem-segmented-button')?.classList.contains('gem-segmented-button-selected'));
            return {{
                hasToggle: btns.length > 0,
                hasTarget: Boolean(targetBtn),
                alreadySelected: already,
                modes: modes,
            }};
        }})()
        """
        raw = self.execute_js(tab_id, probe_mode_js, profile=prof)
        st = raw.get("result") if isinstance(raw, dict) and raw.get("ok") and isinstance(raw.get("result"), dict) else {}

        if not st.get("hasToggle"):
            if target_mode == "chat":
                return {"ok": True, "mode": "chat", "already_set": True, "note": "mode_toggle_absent_assume_chat"}
            return {"ok": False, "error": "Segmented Chat/Task toggle not visible on current Gemini page (Task mode only available on new/zero-state composer)"}

        if st.get("alreadySelected"):
            return {"ok": True, "mode": target_mode, "already_set": True, "modes": st.get("modes")}

        if not st.get("hasTarget"):
            return {"ok": False, "error": f"Target mode '{target_mode}' button not found in toggle", "modes": st.get("modes")}

        switch_js = f"""
        return (async () => {{
            const bd = document.querySelector('.cdk-overlay-backdrop');
            if (bd) bd.click();
            const isVis = (el) => {{
                if (!el) return false;
                const r = el.getBoundingClientRect();
                const s = window.getComputedStyle(el);
                return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
            }};
            const btns = Array.from(document.querySelectorAll('.gem-segmented-button-action')).filter(isVis);
            const targetBtn = btns.find(b => (b.innerText || b.getAttribute('aria-label') || '').trim().toLowerCase() === '{target_mode}');
            if (!targetBtn) return {{ ok: false, error: 'target button disappeared' }};
            targetBtn.click();
            await new Promise(r => setTimeout(r, 450));
            const wrap = targetBtn.closest('.gem-segmented-button');
            const selected = Boolean(wrap && wrap.classList.contains('gem-segmented-button-selected'));
            return {{ ok: selected, mode: '{target_mode}', selected: selected }};
        }})()
        """
        sw_raw = self.execute_js(tab_id, switch_js, profile=prof)
        sw = sw_raw.get("result") if isinstance(sw_raw, dict) and sw_raw.get("ok") and isinstance(sw_raw.get("result"), dict) else {}
        if sw.get("ok"):
            time.sleep(0.3)
            return {"ok": True, "mode": target_mode, "already_set": False}

        time.sleep(0.4)
        recheck = self.execute_js(tab_id, probe_mode_js, profile=prof)
        re_st = recheck.get("result") if isinstance(recheck, dict) and recheck.get("ok") and isinstance(recheck.get("result"), dict) else {}
        if re_st.get("alreadySelected"):
            return {"ok": True, "mode": target_mode, "already_set": False}

        return {"ok": False, "error": f"Failed to switch Gemini composer to '{target_mode}' mode", "state": sw or re_st}

    def ensure_model_and_thinking(
        self,
        tab_id: int,
        model: Optional[str] = None,
        thinking: Optional[str] = None,
        mode: str = "chat",
        profile: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Ensures the Gemini Web UI is set to the target segmented mode ('chat' or 'task'),
        model ('4 Argon', '4 Hydrogen', etc.), and thinking level ('Low', 'Medium', 'High').
        In 'task' mode (or on Flash-Lite), Thinking level is skipped because no Thinking
        submenu exists in Gemini's Task composer.
        """
        ready_info = self.wait_for_page_ready(tab_id, timeout_sec=25.0, profile=profile)
        if not ready_info.get("ready"):
            if ready_info.get("needs_reauth"):
                try:
                    import profile_lock_manager
                    if profile or self.default_profile:
                        profile_lock_manager.mark_profile_needs_reauth(profile or self.default_profile, "gemini_web")
                except Exception:
                    pass
                return {
                    "ok": False,
                    "code": "NEEDS_REAUTH",
                    "error": f"Profile '{profile or self.default_profile}' redirected to sign-in ({ready_info.get('url')}). Manual sign-in required.",
                    "ready_info": ready_info,
                }
            return {
                "ok": False,
                "error": "Page or model picker button did not become ready within 25s",
                "ready_info": ready_info,
            }

        prof = profile or self.default_profile
        route = resolve_execution_route(model=model, thinking=thinking, mode=mode, deep_research=False)
        mode_norm = route["mode"]
        model_norm = route["model_key"]
        model_test_id = route["test_id"]
        thinking_norm = route["thinking"].lower()

        mode_res = self.ensure_execution_mode(tab_id, mode=mode_norm, profile=prof)
        if not mode_res.get("ok"):
            return {
                "ok": False,
                "error": mode_res.get("error", f"Could not switch to mode '{mode_norm}'"),
                "mode_result": mode_res,
            }

        # Step 1: Check if already set
        check_js = r"""
        return (async () => {
            const bd = document.querySelector('.cdk-overlay-backdrop');
            if (bd) bd.click();
            let btn = document.querySelector(
                'button[data-test-id="bard-mode-menu-button"], button.input-area-switch, button[aria-label*="mode picker" i], button[aria-label*="picker" i]'
            );
            if (!btn || btn.offsetWidth === 0) {
                const ed = document.querySelector('.ql-editor, rich-textarea div[contenteditable="true"]');
                if (ed) {
                    ed.focus();
                    try {
                        document.execCommand('insertText', false, ' ');
                    } catch (e) {}
                    await new Promise(r => setTimeout(r, 300));
                    btn = document.querySelector(
                        'button[data-test-id="bard-mode-menu-button"], button.input-area-switch, button[aria-label*="mode picker" i], button[aria-label*="picker" i]'
                    );
                }
            }
            if (!btn || btn.offsetWidth === 0) return { hasBtn: false };
            const r = btn.getBoundingClientRect();
            const rawText = (btn.innerText || '').trim();
            const lines = rawText.split('\n').map(s => s.trim()).filter(Boolean);
            const aria = (btn.getAttribute('aria-label') || '').trim();
            const ariaLower = aria.toLowerCase();
            const firstLineLower = (lines[0] || '').toLowerCase();
            const secondLineLower = (lines[1] || '').toLowerCase();

            const targetModelKey = '""" + model_norm + r"""';
            const targetThinking = '""" + thinking_norm + r"""';

            const hasModel = ariaLower.includes('currently ' + targetModelKey) || ariaLower.includes(targetModelKey) || firstLineLower.includes(targetModelKey) || lines.some(l => l.toLowerCase() === targetModelKey);
            const hasThinking = !targetThinking || (
                targetThinking === 'low'
                    ? (!ariaLower.includes('high') && !ariaLower.includes('medium') && !lines.some(l => l.toLowerCase() === 'high' || l.toLowerCase() === 'medium'))
                    : (ariaLower.includes('currently ' + targetModelKey + ' ' + targetThinking) || secondLineLower === targetThinking || lines.some(l => l.toLowerCase() === targetThinking))
            );

            return {
                hasBtn: true,
                matches: Boolean(hasModel && hasThinking),
                text: rawText,
                aria: aria,
                cx: Math.round(r.left + r.width / 2),
                cy: Math.round(r.top + r.height / 2)
            };
        })()
        """

        raw_state = self.execute_js(tab_id, check_js, profile=prof)
        st = raw_state.get("result") if isinstance(raw_state, dict) and raw_state.get("ok") and isinstance(raw_state.get("result"), dict) else raw_state
        if not isinstance(st, dict) or not st.get("hasBtn"):
            # Check if UI is in zero-state (Where should we start? on /app) where model picker is deferred until first prompt submission
            zs_js = """
            const zeroState = document.querySelector('.is-zero-state, input-area-v2.single-line-input, chat-spark-toggle');
            const editor = document.querySelector('rich-textarea div[contenteditable="true"]');
            return { isZeroState: Boolean(zeroState && editor) };
            """
            zs_res = self.execute_js(tab_id, zs_js, profile=prof)
            if zs_res and zs_res.get("result", {}).get("isZeroState"):
                print(f"[GeminiDriver] UI is in zero-state on {prof or 'active'} (target: {route['model']} | mode: {mode_norm}). Ready for prompt.")
                return {
                    "ok": True,
                    "already_set": True,
                    "zero_state": True,
                    "mode": mode_norm,
                    "model": route["model"],
                    "thinking": route["thinking"],
                    "current_text": f"{route['model']} (Zero-State Default)",
                    "aria_label": "Zero-State"
                }
            return {"ok": False, "error": "Model picker button not found in DOM"}

        if st.get("matches"):
            return {
                "ok": True,
                "already_set": True,
                "mode": mode_norm,
                "model": route["model"],
                "thinking": route["thinking"],
                "current_text": st.get("text"),
                "aria_label": st.get("aria")
            }

        # Step 2: Open picker dropdown via trusted CDP mouse click
        picker_cx, picker_cy = st["cx"], st["cy"]
        inspect_items_js = r"""
        return (() => {
            const items = Array.from(document.querySelectorAll('gem-menu-item, [role="menuitem"], [role="menuitemradio"], button[data-test-id^="bard-mode-option-"]')).map(el => {
                const r = el.getBoundingClientRect();
                return {
                    text: (el.innerText || '').trim().replace(/\n+/g, ' '),
                    testId: el.getAttribute('data-test-id') || '',
                    tag: el.tagName,
                    role: el.getAttribute('role'),
                    disabled: Boolean(el.disabled || el.getAttribute('aria-disabled') === 'true' || el.classList.contains('disabled')),
                    cx: Math.round(r.left + r.width / 2),
                    cy: Math.round(r.top + r.height / 2),
                    w: r.width,
                    h: r.height,
                    selected: el.classList.contains('selected') || el.getAttribute('aria-selected') === 'true' || el.getAttribute('aria-checked') === 'true'
                };
            });
            return items;
        })()
        """

        self.execute_js(
            tab_id,
            "const bd = document.querySelector('.cdk-overlay-backdrop'); if (bd) bd.click(); const btn = document.querySelector('button[data-test-id=\"bard-mode-menu-button\"], button.input-area-switch'); if (btn) btn.click();",
            profile=prof,
        )
        time.sleep(0.45)
        raw_items = self.execute_js(tab_id, inspect_items_js, profile=prof)
        items = raw_items.get("result") if isinstance(raw_items, dict) and raw_items.get("ok") and isinstance(raw_items.get("result"), list) else []

        if not items:
            self._nudge_compositor(tab_id, profile=prof)
            time.sleep(0.2)
            raw_items = self.execute_js(tab_id, inspect_items_js, profile=prof)
            items = raw_items.get("result") if isinstance(raw_items, dict) and raw_items.get("ok") and isinstance(raw_items.get("result"), list) else []

        if not items:
            self._cdp_mouse_click(tab_id, picker_cx, picker_cy, profile=prof)
            time.sleep(0.35)
            self._nudge_compositor(tab_id, profile=prof)
            time.sleep(0.2)
            raw_items = self.execute_js(tab_id, inspect_items_js, profile=prof)
            items = raw_items.get("result") if isinstance(raw_items, dict) and raw_items.get("ok") and isinstance(raw_items.get("result"), list) else []

        if not items:
            return {"ok": False, "error": "Model picker overlay menu did not open"}

        # 3a. Select requested model if not selected
        target_model_item = next(
            (
                it for it in items
                if (model_test_id and it.get("testId") == model_test_id)
                or (model_norm and model_norm in it["text"].lower())
            ),
            None,
        )
        if not target_model_item:
            available_texts = [it["text"] for it in items]
            self.execute_js(tab_id, "const bd = document.querySelector('.cdk-overlay-backdrop'); if (bd) bd.click(); else document.body.click();", profile=prof)
            return {
                "ok": False,
                "error": f"Model '{route['model']}' not available in {mode_norm} mode picker",
                "available_items": available_texts,
            }

        if target_model_item.get("disabled"):
            low_txt = target_model_item["text"].lower()
            is_limit = any(k in low_txt for k in ("limit", "reset", "reached", "quota", "unavailable"))
            self.execute_js(tab_id, "const bd = document.querySelector('.cdk-overlay-backdrop'); if (bd) bd.click();", profile=prof)
            return {
                "ok": False,
                "rate_limited": is_limit,
                "message": target_model_item["text"],
                "error": f"Model '{route['model']}' option is disabled: {target_model_item['text']}",
            }

        if not target_model_item.get("selected") and target_model_item.get("w", 0) > 0:
            click_model_js = f"""
            (() => {{
                const items = Array.from(document.querySelectorAll('gem-menu-item, [role="menuitem"], [role="menuitemradio"], button[data-test-id^="bard-mode-option-"]'));
                const el = items.find(e =>
                    ('{model_test_id}' && e.getAttribute('data-test-id') === '{model_test_id}')
                    || (e.innerText || '').toLowerCase().includes('{model_norm}')
                );
                if (el) el.click();
            }})()
            """
            self.execute_js(tab_id, click_model_js, profile=prof)
            time.sleep(0.5)
            if thinking_norm:
                raw_items = self.execute_js(tab_id, inspect_items_js, profile=prof)
                items = raw_items.get("result") if isinstance(raw_items, dict) and raw_items.get("ok") and isinstance(raw_items.get("result"), list) else []
                if not items:
                    self.execute_js(
                        tab_id,
                        "const btn = document.querySelector('button[data-test-id=\"bard-mode-menu-button\"], button.input-area-switch'); if (btn) btn.click();",
                        profile=prof,
                    )
                    time.sleep(0.45)
                    raw_items = self.execute_js(tab_id, inspect_items_js, profile=prof)
                    items = raw_items.get("result") if isinstance(raw_items, dict) and raw_items.get("ok") and isinstance(raw_items.get("result"), list) else []

        # 3b. Expand "Thinking level" sub-menu ONLY if thinking requested (Chat mode + supporting model)
        thinking_menu_btn = None
        used_native_thinking = False
        if thinking_norm:
            thinking_menu_btn = next((it for it in items if "thinking level" in it["text"].lower()), None)
            if thinking_menu_btn and thinking_menu_btn.get("w", 0) > 0:
                self.execute_js(tab_id, """
                (() => {
                    const items = Array.from(document.querySelectorAll('gem-menu-item, [role="menuitem"]'));
                    const tl = items.find(el => (el.innerText || '').toLowerCase().includes('thinking level'));
                    if (tl) {
                        tl.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
                        tl.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                        tl.click();
                    }
                })()
                """, profile=prof)
                time.sleep(0.4)
                raw_items = self.execute_js(tab_id, inspect_items_js, profile=prof)
                items = raw_items.get("result") if isinstance(raw_items, dict) and raw_items.get("ok") and isinstance(raw_items.get("result"), list) else []

                if not any(it["text"].lower().startswith(thinking_norm) and it.get("w", 0) > 0 for it in items):
                    self._cdp_mouse_click(tab_id, thinking_menu_btn["cx"], thinking_menu_btn["cy"], profile=prof)
                    time.sleep(0.4)
                    raw_items = self.execute_js(tab_id, inspect_items_js, profile=prof)
                    items = raw_items.get("result") if isinstance(raw_items, dict) and raw_items.get("ok") and isinstance(raw_items.get("result"), list) else []

            # Find matching target thinking item (must have w > 0, h > 0)
            target_item = next(
                (it for it in items if it["text"].lower().startswith(thinking_norm) and it.get("w", 0) > 0),
                None
            )
            if target_item:
                self.execute_js(tab_id, f"""
                (() => {{
                    const items = Array.from(document.querySelectorAll('gem-menu-item, [role="menuitem"], [role="menuitemradio"]'));
                    const it = items.find(el => (el.innerText || '').trim().toLowerCase().startsWith('{thinking_norm}') && el.getBoundingClientRect().width > 0);
                    if (it) it.click();
                }})()
                """, profile=prof)
                time.sleep(0.5)
            elif target_model_item and (target_model_item.get("selected") or target_model_item.get("w", 0) > 0):
                used_native_thinking = True
                print(f"[GeminiDriver] Note: Thinking sub-menu not present; proceeding with {route['model']} native reasoning.")
            else:
                available_texts = [it["text"] for it in items]
                self.execute_js(tab_id, "document.body.click();", profile=prof)
                return {
                    "ok": False,
                    "error": f"Thinking level '{thinking_norm}' not found or not visible in mode picker submenu",
                    "available_items": available_texts
                }

        # Step 4: Close any lingering backdrop
        self.execute_js(tab_id, "const bd = document.querySelector('.cdk-overlay-backdrop'); if (bd) bd.click(); else document.body.click();", profile=prof)
        time.sleep(0.4)

        # Step 5: Post-click verification check
        verify_js = r"""
        return (() => {
            const picker = document.querySelector('button[data-test-id="bard-mode-menu-button"], button.input-area-switch, button[aria-label*="mode picker" i], button[aria-label*="picker" i]');
            if (!picker) return { hasBtn: false };
            const text = (picker.innerText || '').trim();
            const aria = (picker.getAttribute('aria-label') || '').trim();
            const ariaLower = aria.toLowerCase();
            const textLower = text.toLowerCase();
            const targetModelKey = '""" + model_norm + r"""';
            const targetThinking = '""" + thinking_norm + r"""';
            return {
                hasBtn: true,
                text: text,
                aria: aria,
                hasModel: ariaLower.includes(targetModelKey) || textLower.includes(targetModelKey),
                hasThinking: !targetThinking ? true : (
                    targetThinking === 'low'
                        ? (!ariaLower.includes('high') && !ariaLower.includes('medium') && !textLower.includes('high') && !textLower.includes('medium'))
                        : (ariaLower.includes(targetThinking) || textLower.includes(targetThinking))
                )
            };
        })()
        """
        raw_v = self.execute_js(tab_id, verify_js, profile=prof)
        v = raw_v.get("result") if isinstance(raw_v, dict) and raw_v.get("ok") and isinstance(raw_v.get("result"), dict) else {}
        if v.get("hasModel") and (v.get("hasThinking") or not thinking_menu_btn or used_native_thinking):
            return {
                "ok": True,
                "mode": mode_norm,
                "model": route["model"],
                "thinking": route["thinking"],
                "current_text": v.get("text"),
                "aria_label": v.get("aria")
            }

        return {
            "ok": False,
            "error": f"Verification failed for {route['model']} ({mode_norm}): button reads '{v.get('text')}' (aria: '{v.get('aria')}')",
            "current_text": v.get("text"),
            "aria_label": v.get("aria")
        }

    def ensure_deep_research(
        self, tab_id: int, profile: Optional[str] = None
    ) -> bool:
        """
        Ensures Deep Research mode is active in the prompt bar.
        Automatically switches segmented mode to Chat first (Deep Research does not exist in Task mode),
        then drives synchronous DOM steps with Python-side settling to avoid long async EVAL_DOM hangs:
        '+' (Upload & tools) -> 'More tools' -> 'Deep Research' -> verify [ ⚛ Deep research ] chip.
        """
        prof = profile or self.default_profile
        ready = self.wait_for_page_ready(tab_id, timeout_sec=25.0, profile=prof)
        if not ready.get("ready"):
            return False
        mode_res = self.ensure_execution_mode(tab_id, mode="chat", profile=prof)
        if not mode_res.get("ok"):
            return False

        chip_check_js = """
        const isVis = (el) => {
            if (!el) return false;
            const r = el.getBoundingClientRect();
            const s = window.getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
        };
        const inputArea = document.querySelector(
            'input-area-v2, input-container, .input-area-container, .text-input-field, form, rich-textarea'
        ) || document.body;
        const chips = Array.from(inputArea.querySelectorAll(
            'button, mat-chip, mat-chip-row, .tool-chip, [role="button"], .pill, [class*="chip"], [class*="tool"]'
        )).filter(isVis);
        for (const c of chips) {
            const txt = ((c.innerText || '') + ' ' + (c.getAttribute('aria-label') || '')).toLowerCase();
            if (txt.includes('deep research') && !c.closest('.cdk-overlay-container')) {
                return true;
            }
        }
        return false;
        """

        r_chk = self.execute_js(tab_id, chip_check_js, timeout=10.0, profile=prof)
        if isinstance(r_chk, dict) and r_chk.get("result") is True:
            return True

        # Zero-state composer ('Where should we start?') hides full toolbar & More tools items until editor is focused/woken
        wake_js = """
        const ed = document.querySelector('.ql-editor, rich-textarea div[contenteditable="true"], div[role="textbox"][contenteditable="true"]');
        if (ed && !(ed.innerText || '').trim()) {
            ed.focus();
            try { document.execCommand('insertText', false, ' '); } catch (e) {}
            return true;
        }
        return false;
        """
        self.execute_js(tab_id, wake_js, timeout=10.0, profile=prof)
        time.sleep(0.4)

        click_dr_js = """
        const isVis = (el) => {
            if (!el) return false;
            const r = el.getBoundingClientRect();
            const s = window.getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
        };
        const dr = Array.from(document.querySelectorAll(
            '.cdk-overlay-pane gem-menu-item, .cdk-overlay-container gem-menu-item, [role="menuitemcheckbox"], [role="menuitem"], .cdk-overlay-pane button, .cdk-overlay-container .mat-mdc-list-item, button, .mat-mdc-list-item'
        )).filter(isVis).find(b => {
            const t = ((b.innerText || '') + ' ' + (b.getAttribute('aria-label') || '')).toLowerCase().trim();
            return t === 'deep research' || t.includes('deep research');
        });
        if (!dr) return false;
        dr.click();
        return true;
        """

        def _verify_dr_chip() -> bool:
            self._nudge_compositor(tab_id, profile=prof)
            for _ in range(10):
                time.sleep(0.15)
                chk = self.execute_js(tab_id, chip_check_js, timeout=10.0, profile=prof)
                if isinstance(chk, dict) and chk.get("result") is True:
                    return True
            return False

        # Path 1: Direct visible Deep Research button/chip on updated Gemini composer
        direct_dr_js = """
        const isVis = (el) => {
            if (!el) return false;
            const r = el.getBoundingClientRect();
            const s = window.getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
        };
        const btn = Array.from(document.querySelectorAll('button, [role="button"], mat-chip')).filter(isVis).find(el => {
            if (el.closest('nav, aside, .conversation-list, gem-nav-list-item')) return false;
            const t = ((el.innerText || '') + ' ' + (el.getAttribute('aria-label') || '')).toLowerCase().trim();
            return t === 'deep research' || t.includes('deep research');
        });
        if (!btn) return false;
        btn.click();
        return true;
        """
        direct_res = self.execute_js(tab_id, direct_dr_js, timeout=10.0, profile=prof)
        if isinstance(direct_res, dict) and direct_res.get("result") is True and _verify_dr_chip():
            return True

        # Path 2: Gemini Web 'Tools' menu button -> Deep Research (or More tools -> Deep Research)
        click_tools_js = """
        const isVis = (el) => {
            if (!el) return false;
            const r = el.getBoundingClientRect();
            const s = window.getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
        };
        const toolsBtn = Array.from(document.querySelectorAll(
            'button[aria-label*="Tools" i], button[data-test-id*="tools" i], button.toolbox-drawer-button, input-area-v2 button, .input-area-container button'
        )).filter(isVis).find(b => {
            const t = (b.innerText || '').trim().toLowerCase();
            const a = (b.getAttribute('aria-label') || '').trim().toLowerCase();
            return t === 'tools' || a === 'tools' || (a.includes('tools') && !a.includes('upload'));
        });
        if (!toolsBtn) return false;
        const bd = document.querySelector('.cdk-overlay-backdrop');
        if (bd) bd.click();
        toolsBtn.click();
        return true;
        """
        t_res = self.execute_js(tab_id, click_tools_js, timeout=10.0, profile=prof)
        if isinstance(t_res, dict) and t_res.get("result") is True:
            self._nudge_compositor(tab_id, profile=prof)
            for _ in range(8):
                time.sleep(0.15)
                dr_res = self.execute_js(tab_id, click_dr_js, timeout=10.0, profile=prof)
                if isinstance(dr_res, dict) and dr_res.get("result") is True:
                    if _verify_dr_chip():
                        return True
                    break

        find_mt_js = """
        const isVis = (el) => {
            if (!el) return false;
            const r = el.getBoundingClientRect();
            const s = window.getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
        };
        const mt = Array.from(document.querySelectorAll(
            '.cdk-overlay-pane gem-menu-item, .cdk-overlay-container gem-menu-item, [role="menuitem"], [data-test-id="more-tools-button"], button.more-tools-button, button.toolbox-drawer-menu-item, button[aria-label="More tools"], .cdk-overlay-pane button'
        )).filter(isVis).find(b => ((b.innerText || '') + ' ' + (b.getAttribute('aria-label') || '')).toLowerCase().includes('more tools'));
        return Boolean(mt);
        """

        click_plus_js = """
        const isVis = (el) => {
            if (!el) return false;
            const r = el.getBoundingClientRect();
            const s = window.getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
        };
        const plusBtn = Array.from(document.querySelectorAll(
            'button[aria-label*="Upload & tools" i], button[aria-label*="Upload and tools" i], gem-icon-button.menu-button button, button[aria-label*="Upload" i]'
        )).find(isVis);
        if (!plusBtn) return { ok: false, error: 'Upload & tools button not found' };
        if (plusBtn.getAttribute('aria-expanded') !== 'true') {
            const bd = document.querySelector('.cdk-overlay-backdrop');
            if (bd) bd.click();
            plusBtn.click();
        }
        return { ok: true };
        """

        # Path 3: '+' (Upload & tools) -> direct Deep Research OR More tools -> Deep Research
        mt_ready = False
        for attempt in range(2):
            dr_direct = self.execute_js(tab_id, click_dr_js, timeout=10.0, profile=prof)
            if isinstance(dr_direct, dict) and dr_direct.get("result") is True and _verify_dr_chip():
                return True
            mt_res = self.execute_js(tab_id, find_mt_js, timeout=10.0, profile=prof)
            if isinstance(mt_res, dict) and mt_res.get("result") is True:
                mt_ready = True
                break
            p_res = self.execute_js(tab_id, click_plus_js, timeout=10.0, profile=prof)
            if not (isinstance(p_res, dict) and isinstance(p_res.get("result"), dict) and p_res["result"].get("ok")):
                print(f"[GeminiDriver] Deep Research '+' open error (attempt {attempt + 1}): {p_res}", file=sys.stderr)
                continue
            self._nudge_compositor(tab_id, profile=prof)
            for _ in range(10):
                time.sleep(0.15)
                dr_direct = self.execute_js(tab_id, click_dr_js, timeout=10.0, profile=prof)
                if isinstance(dr_direct, dict) and dr_direct.get("result") is True:
                    if _verify_dr_chip():
                        return True
                mt_res = self.execute_js(tab_id, find_mt_js, timeout=10.0, profile=prof)
                if isinstance(mt_res, dict) and mt_res.get("result") is True:
                    mt_ready = True
                    break
            if mt_ready:
                break

        if not mt_ready:
            print("[GeminiDriver] Deep Research toggle failed: More tools / Tools / Deep Research option not visible", file=sys.stderr)
            return False

        hover_mt_js = """
        const isVis = (el) => {
            if (!el) return false;
            const r = el.getBoundingClientRect();
            const s = window.getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
        };
        const mt = Array.from(document.querySelectorAll(
            '.cdk-overlay-pane gem-menu-item, .cdk-overlay-container gem-menu-item, [role="menuitem"], [data-test-id="more-tools-button"], button.more-tools-button, button.toolbox-drawer-menu-item, button[aria-label="More tools"], .cdk-overlay-pane button'
        )).filter(isVis).find(b => ((b.innerText || '') + ' ' + (b.getAttribute('aria-label') || '')).toLowerCase().includes('more tools'));
        if (!mt) return false;
        mt.dispatchEvent(new MouseEvent('pointerenter', { bubbles: true }));
        mt.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
        mt.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
        return true;
        """
        click_mt_fallback_js = hover_mt_js + "\n; const mt2 = Array.from(document.querySelectorAll('.cdk-overlay-pane gem-menu-item, .cdk-overlay-container gem-menu-item, [role=\"menuitem\"], button')).find(b => ((b.innerText || '') + ' ' + (b.getAttribute('aria-label') || '')).toLowerCase().includes('more tools')); if (mt2) mt2.click();"
        self.execute_js(tab_id, hover_mt_js, timeout=10.0, profile=prof)
        self._nudge_compositor(tab_id, profile=prof)

        dr_clicked = False
        for poll_i in range(12):
            time.sleep(0.18)
            dr_res = self.execute_js(tab_id, click_dr_js, timeout=10.0, profile=prof)
            if isinstance(dr_res, dict) and dr_res.get("result") is True:
                dr_clicked = True
                break
            if poll_i == 5:
                self.execute_js(tab_id, click_mt_fallback_js, timeout=10.0, profile=prof)
                self._nudge_compositor(tab_id, profile=prof)

        if not dr_clicked:
            print("[GeminiDriver] Deep Research toggle failed: Deep research option not found in More tools submenu", file=sys.stderr)
            return False

        if _verify_dr_chip():
            return True

        print("[GeminiDriver] Deep Research toggle failed: Deep Research chip not verified in prompt bar after clicking", file=sys.stderr)
        return False

    def create_session(
        self,
        session_id: str | None = None,
        subagent: str = "main",
        new_chat: bool = True,
        own_tab: bool = False,
        profile_dir: str | None = None,
    ) -> str:
        """Creates or registers a chat session with auto-browser profile boot if needed."""
        session_id = session_id or f"gemini_{subagent}_{int(time.time())}"
        prof = profile_dir or self.default_profile or "Profile 14"
        self.default_profile = prof

        # Reuse existing session if requested without triggering new chat
        if session_id in self.registry and not new_chat:
            meta = self.registry[session_id]
            tab_id = meta.get("tab_id")
            chat_url = meta.get("url")
            if tab_id and chat_url and chat_url.startswith("https://gemini.google.com/app/"):
                check_url_js = f"""
                if (window.location.href !== '{chat_url}') {{
                    window.location.href = '{chat_url}';
                    return {{ navigated: true }};
                }}
                return {{ navigated: false }};
                """
                try:
                    self.execute_js(tab_id, check_url_js, profile=prof)
                    time.sleep(1.0)
                except Exception:
                    pass
            print(f"[GeminiDriver] Continuing existing session '{session_id}' on Tab {tab_id} ({prof}).")
            return session_id

        # Check for an AGENT-OWNED Gemini tab; only boot Chrome if profile is actually disconnected from bridge
        tab = self.get_open_gemini_tab(profile=prof)
        if not tab:
            probe_res = self._call_api_raw("/command", {"action": "LIST_TABS", "profile": prof}, profile=prof)
            if not (isinstance(probe_res, dict) and probe_res.get("ok")):
                try:
                    open_prof_res = self._call_api_raw(
                        "/profile/open",
                        {"profile": prof, "url": "https://gemini.google.com/app", "auto_close_idle": True, "timeout": 15.0},
                        method="POST",
                        timeout=22.0,
                    )
                    if isinstance(open_prof_res, dict) and open_prof_res.get("code") == "AGENT_CAPACITY_REACHED":
                        raise RuntimeError(f"AGENT_CAPACITY_REACHED: {open_prof_res.get('error')}")
                    for _ in range(15):
                        time.sleep(0.5)
                        tab = self.get_open_gemini_tab(profile=prof)
                        if tab:
                            print(f"[GeminiDriver] Profile '{prof}' connected on agent tab {tab['id']}.")
                            break
                except RuntimeError:
                    raise
                except Exception as e:
                    print(f"[GeminiDriver] Auto-boot note: {e}", file=sys.stderr)

        if own_tab:
            # Spawn dedicated background tab (enforces MAX_AGENT_TABS=6 & registers ownership)
            open_res = self._call_api(
                "/command",
                {
                    "action": "OPEN_TAB",
                    "owner": f"gemini_driver:{session_id}",
                    "surface": "gemini_web",
                    "agent_guarded": True,
                    "params": {"url": "https://gemini.google.com/app", "active": False},
                },
                profile=prof,
            )
            if open_res.get("code") == "AGENT_CAPACITY_REACHED":
                raise RuntimeError(f"AGENT_CAPACITY_REACHED: {open_res.get('error')}")
            tab_id = open_res.get("tabId")
            time.sleep(3.0)
        else:
            if tab:
                tab_id = tab["id"]
                if new_chat:
                    # Click New chat button in sidebar
                    click_new = """
                    const d = window.__geminiDriver;
                    const newChatBtn = d.findByText('button, a', 'New chat');
                    if (newChatBtn) {
                        await d.smartClick(newChatBtn);
                        await d.sleep(800);
                    } else {
                        window.location.href = 'https://gemini.google.com/app';
                        await d.sleep(2000);
                    }
                    // Wait until old model-response nodes are cleared
                    for (let w = 0; w < 10; w++) {
                        if (document.querySelectorAll('model-response').length === 0) break;
                        await d.sleep(200);
                    }
                    // Clear any leftover Deep Research pill chip in input box on fresh session start
                    const inputScope = document.querySelector('.input-area-container, rich-textarea, .chat-input-area, form');
                    if (inputScope) {
                        const drChip = Array.from(inputScope.querySelectorAll('button, mat-chip')).find(el => {
                            const txt = ((el.innerText || '') + ' ' + (el.getAttribute('aria-label') || '')).toLowerCase();
                            return txt.includes('deep research');
                        });
                        if (drChip) {
                            drChip.click();
                            await d.sleep(300);
                        }
                    }
                    return { ok: true };
                    """
                    self.execute_js(tab_id, click_new, profile=prof)
                    self.wait_for_page_ready(tab_id, timeout_sec=25.0, profile=prof)
            else:
                reusable_blank = None
                owned_ids = self._get_owned_tab_ids(profile=prof)
                if owned_ids:
                    t_res = self._call_api_raw("/command", {"action": "LIST_TABS", "profile": prof}, profile=prof)
                    for t in (t_res.get("tabs", []) if isinstance(t_res, dict) else []):
                        if str(t.get("id")) in owned_ids:
                            tu = (t.get("url") or t.get("pendingUrl") or "").strip().lower()
                            if tu in ("", "about:blank", "chrome://newtab/", "chrome://newtab"):
                                reusable_blank = t
                                break
                if reusable_blank:
                    tab_id = reusable_blank["id"]
                    self._call_api(
                        "/command",
                        {
                            "action": "CDP_COMMAND",
                            "agent_guarded": True,
                            "params": {"tabId": tab_id, "method": "Page.navigate", "params": {"url": "https://gemini.google.com/app"}},
                        },
                        profile=prof,
                    )
                    self.wait_for_page_ready(tab_id, timeout_sec=25.0, profile=prof)
                else:
                    open_res = self._call_api(
                        "/command",
                        {
                            "action": "OPEN_TAB",
                            "owner": f"gemini_driver:{session_id}",
                            "surface": "gemini_web",
                            "agent_guarded": True,
                            "params": {"url": "https://gemini.google.com/app", "active": True},
                        },
                        profile=prof,
                    )
                    if open_res.get("code") == "AGENT_CAPACITY_REACHED":
                        raise RuntimeError(f"AGENT_CAPACITY_REACHED: {open_res.get('error')}")
                    tab_id = open_res.get("tabId")
                    self.wait_for_page_ready(tab_id, timeout_sec=25.0, profile=prof)

        self.registry[session_id] = {
            "session_id": session_id,
            "subagent": subagent,
            "profile": prof,
            "tab_id": tab_id,
            "own_tab": own_tab,
            "chat_id": None,
            "url": "https://gemini.google.com/app",
            "created_at": time.time(),
            "turns": 0,
        }
        self.tab_id = tab_id
        self._save_registry()
        print(f"[GeminiDriver] Session '{session_id}' initialized on Tab {tab_id} ({prof}).")
        return session_id

    def upload_files(self, session_id: str, file_paths: List[str], timeout_sec: int = 30) -> Dict[str, Any]:
        """Uploads local files (codebases, logs, context, images, PDFs) into Gemini chat prompt box."""
        if session_id not in self.registry:
            self.create_session(session_id=session_id)

        meta = self.registry[session_id]
        tab_id = self.tab_id or meta.get("tab_id")
        self.tab_id = tab_id
        prof = meta.get("profile") or self.default_profile

        abs_files = []
        for fp in file_paths:
            p = Path(fp)
            if not p.is_absolute():
                p = Path("./") / p
            if not p.exists():
                return {"ok": False, "error": f"File not found: {p}"}
            abs_files.append(str(p.resolve()))

        if not abs_files:
            return {"ok": False, "error": "No valid files specified"}

        print(f"[GeminiDriver] Attaching {len(abs_files)} file(s) on {prof or 'active'}: {[Path(f).name for f in abs_files]}...")

        # 1. Bring tab to front
        try:
            self._call_api("/command", {"action": "CDP_COMMAND", "params": {"tabId": tab_id, "method": "Page.bringToFront"}}, profile=prof)
        except Exception:
            pass

        # 2. Strategy A: Direct In-Memory DataTransfer Paste / Drop onto .ql-editor & xap-deferred-uploader
        # Works in <1s without opening native OS file dialogs or needing deferred <input type="file"> to mount
        import base64
        import mimetypes
        file_payloads = []
        for fp in abs_files:
            p_obj = Path(fp)
            mime, _ = mimetypes.guess_type(str(p_obj))
            if not mime:
                mime = "text/markdown" if p_obj.suffix.lower() in (".md", ".markdown") else "text/plain"
            raw_bytes = p_obj.read_bytes()
            file_payloads.append({
                "name": p_obj.name,
                "stem": p_obj.stem,
                "mime": mime,
                "b64": base64.b64encode(raw_bytes).decode("ascii"),
            })

        paste_drop_js = f"""
        const d = window.__geminiDriver;
        const payloads = {json.dumps(file_payloads)};
        const dt = new DataTransfer();
        for (const item of payloads) {{
            const binStr = atob(item.b64);
            const bytes = new Uint8Array(binStr.length);
            for (let i = 0; i < binStr.length; i++) bytes[i] = binStr.charCodeAt(i);
            const file = new File([bytes], item.name, {{ type: item.mime, lastModified: Date.now() }});
            dt.items.add(file);
        }}

        const hasAttachedChip = () => {{
            const scope = document.querySelector('input-area-v2, .input-area-container, chat-window') || document.body;
            const chips = scope.querySelectorAll('uploader-file-preview, gem-attachment, mat-basic-chip, .attachment-preview-wrapper, [data-test-id*="attachment"], [data-test-id*="file"], [class*="file-preview"], [class*="attachment-preview"]');
            if (chips.length > 0) return true;
            const scopeText = (document.body.innerText || '');
            return payloads.some(p => scopeText.includes(p.stem));
        }};

        // Try 1: ClipboardEvent('paste') on .ql-editor
        const editor = document.querySelector('rich-textarea .ql-editor, .ql-editor, rich-textarea div[contenteditable="true"]');
        if (editor) {{
            editor.focus();
            const pasteEvt = new ClipboardEvent('paste', {{ bubbles: true, cancelable: true, clipboardData: dt }});
            editor.dispatchEvent(pasteEvt);
            await d.sleep(1000);
        }}

        // Try 2: DragEvent('drop') on xap-deferred-uploader / .input-area-container if paste didn't trigger uploader
        if (!hasAttachedChip()) {{
            const dropTarget = document.querySelector('xap-deferred-uploader, .input-area-container, rich-textarea') || editor || document.body;
            for (const evtType of ['dragenter', 'dragover', 'drop']) {{
                const dragEvt = new DragEvent(evtType, {{ bubbles: true, cancelable: true, dataTransfer: dt }});
                dropTarget.dispatchEvent(dragEvt);
                await d.sleep(150);
            }}
            await d.sleep(1000);
        }}

        // Try 3: Open '+' -> 'Upload files' if still not attached so <input type="file"> mounts
        if (!hasAttachedChip() && document.querySelectorAll('input[type="file"]').length === 0) {{
            let plusBtn = document.querySelector('button[aria-label*="Upload & tools" i], button[aria-label*="Upload and tools" i], button[aria-label*="tools" i], button[aria-label*="Upload" i]');
            if (plusBtn) {{
                plusBtn.focus();
                await d.smartClick(plusBtn);
                await d.sleep(500);
                let upBtn = document.querySelector('button[data-test-id="local-images-files-uploader-button"], [aria-label*="Upload files"] button, button[aria-label*="Upload files"]') ||
                    Array.from(document.querySelectorAll('button, [role="menuitem"]')).find(b => /upload files/i.test((b.innerText || '').trim()));
                if (upBtn) {{
                    await d.smartClick(upBtn);
                    await d.sleep(500);
                }}
            }}
        }}
        return {{ ok: true, attached: hasAttachedChip(), inputs: document.querySelectorAll('input[type="file"]').length }};
        """
        pd_res = self.execute_js(tab_id, paste_drop_js, profile=prof)
        attached = bool(pd_res and pd_res.get("ok") and (pd_res.get("result") or {}).get("attached"))

        if not attached:
            # 3. Enable DOM domain in CDP
            self._call_api("/command", {"action": "CDP_COMMAND", "params": {"tabId": tab_id, "method": "DOM.enable"}}, profile=prof)

            # 4. Find the best file input element (prefer input under images-files-uploader or document accepts)
            find_best_inp_js = """
            (() => {
                const inps = Array.from(document.querySelectorAll('input[type="file"]'));
                if (inps.length === 0) return null;
                const docInpIdx = inps.findIndex(i => {
                    const parent = i.parentElement ? i.parentElement.tagName.toLowerCase() : '';
                    const accept = i.accept || '';
                    return parent.includes('images-files') || parent.includes('file') || accept.includes('.md') || accept.includes('.txt') || accept === '';
                });
                return docInpIdx >= 0 ? docInpIdx : 0;
            })()
            """
            inp_idx_res = self.execute_js(tab_id, find_best_inp_js, profile=prof)
            target_idx = inp_idx_res.get("result") if inp_idx_res and inp_idx_res.get("result") is not None else 0

            # Evaluate target input objectId
            eval_res = self._call_api(
                "/command",
                {
                    "action": "CDP_COMMAND",
                    "params": {
                        "tabId": tab_id,
                        "method": "Runtime.evaluate",
                        "params": {
                            "expression": f"document.querySelectorAll('input[type=\"file\"]')[{target_idx}] || document.querySelector('input[type=\"file\"]')",
                            "returnByValue": False,
                        },
                    },
                },
                profile=prof,
            )
            obj_id = eval_res.get("result", {}).get("result", {}).get("objectId")

            if obj_id:
                set_res = self._call_api(
                    "/command",
                    {
                        "action": "CDP_COMMAND",
                        "params": {
                            "tabId": tab_id,
                            "method": "DOM.setFileInputFiles",
                            "params": {"files": abs_files, "objectId": obj_id},
                        },
                    },
                    profile=prof,
                )
                if set_res and set_res.get("ok"):
                    attached = True

            # 5. Trigger Angular change events on input and dismiss menu backdrop
            trigger_js = f"""
            const inps = document.querySelectorAll('input[type="file"]');
            if (inps[{target_idx}]) {{
                inps[{target_idx}].dispatchEvent(new Event('input', {{ bubbles: true }}));
                inps[{target_idx}].dispatchEvent(new Event('change', {{ bubbles: true }}));
            }} else {{
                inps.forEach(i => {{
                    i.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    i.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }});
            }}
            Array.from(document.querySelectorAll('.cdk-overlay-backdrop')).forEach(b => b.click());
            document.body.click();
            """
            self.execute_js(tab_id, trigger_js, profile=prof)
            time.sleep(1.0)

        # 6. Wait for file chips/cards to settle and any upload progress indicators to unmount
        stem_names = [Path(f).stem for f in abs_files]
        start_wait = time.time()
        while time.time() - start_wait < timeout_sec:
            check_js = f"""
            (() => {{
                const stems = {json.dumps(stem_names)};
                const scope = document.querySelector('input-area-v2, .input-area-container, chat-window') || document.body;
                const chips = Array.from(scope.querySelectorAll('uploader-file-preview, gem-attachment, mat-basic-chip, .attachment-preview-wrapper, [data-test-id*="attachment"], [data-test-id*="file"], [class*="file-preview"], [class*="attachment-preview"]'));
                const scopeText = (document.body.innerText || '');
                const stemMatched = stems.some(s => scopeText.includes(s));
                const progress = Array.from(scope.querySelectorAll('mat-progress-bar, mat-progress-spinner, [role="progressbar"], .progress-bar, .uploading'));
                const count = Math.max(chips.length, stemMatched ? stems.length : 0);
                return {{
                    chipsCount: count,
                    progressCount: progress.length,
                    ready: count >= 1 && progress.length === 0
                }};
            }})()
            """
            c_res = self.execute_js(tab_id, check_js, profile=prof)
            data = (c_res.get("result") or {}) if c_res else {}
            if data.get("ready"):
                print(f"[GeminiDriver] Successfully attached {data.get('chipsCount')} file card(s) in {round(time.time() - start_wait, 1)}s.")
                return {"ok": True, "files": abs_files, "chipsCount": data.get("chipsCount")}
            time.sleep(0.5)

        print(f"[GeminiDriver] Upload attachment dispatched ({len(abs_files)} file(s)).")
        return {"ok": attached, "files": abs_files}

    def _dispatch_cdp_click(self, tab_id: int, x: int, y: int, randomize: bool = True) -> None:
        """Dispatches a realistic human-like curved trajectory with micro-jitter and trusted CDP click."""
        dispatch_stealth_click(self._call_api, tab_id, x, y, randomize_target=randomize)

    def harvest_rich_response(self, tab_id: int, profile: str | None = None) -> Dict[str, Any]:
        """Harvests structured response data: formatted text, tables (markdown & JSON), code blocks, images, canvas, and sources."""
        res = self.execute_js(tab_id, RICH_HARVEST_JS, profile=profile)
        return (res.get("result") or {}) if res and res.get("ok") else {}

    def ask(
        self,
        session_id: str,
        prompt: str,
        files: List[str] | None = None,
        deep_research: bool = False,
        model: Optional[str] = None,
        thinking: Optional[str] = None,
        mode: str = "chat",
        check_usage: bool = True,
        timeout_sec: int = 300,
        poll_interval_sec: float = 2.5,
        max_recovery_retries: int = 2,
        clean: bool = False,
        keep_tab: bool = True,
    ) -> Dict[str, Any]:
        """
        Executes a strict 5-Step Pre-Send Sequence:
        1. Verify Mode (Chat vs Task), Model ('4 Argon' for Chat consulting, '4 Hydrogen' for Deep Research or Task offloading), & Thinking level
        2. Toggle Deep Research (if enabled in Chat mode) & verify '[ ⚛ Deep research ]' pill chip
        3. Attach Context/Code Files (-f)
        4. Insert Prompt Text into Quill (<p> nodes, preserving chips & avoiding raw '\\n' Enter-submit)
        5. Dispatch Trusted Send Click & Poll Completion (with Deep Research Plan-Card Guard & Task-mode step guard)
        """
        if session_id not in self.registry:
            self.create_session(session_id=session_id)

        meta = self.registry[session_id]
        tab_id = meta["tab_id"]
        prof = meta.get("profile") or self.default_profile

        route = resolve_execution_route(
            model=model,
            thinking=thinking,
            mode=mode,
            deep_research=deep_research,
        )
        target_mode = route["mode"]
        target_model = route["model"]
        target_thinking = route["thinking"]

        # STEP 1: Ensure Segmented Mode + Model + Thinking Level
        print(
            f"[GeminiDriver] [Step 1/5] Ensuring Mode={target_mode}, Model={target_model}, "
            f"Thinking={target_thinking or 'N/A (Task/Flash)'} on {prof or 'active'}..."
        )
        ensure_res = self.ensure_model_and_thinking(
            tab_id,
            model=target_model,
            thinking=target_thinking,
            mode=target_mode,
            profile=prof,
        )
        if self.tab_id and self.tab_id != tab_id:
            tab_id = self.tab_id
            meta["tab_id"] = tab_id
            self._save_registry()
        if not ensure_res.get("ok"):
            if ensure_res.get("needs_reauth"):
                return {"ok": False, "code": "NEEDS_REAUTH", "error": ensure_res.get("error")}
            if ensure_res.get("rate_limited"):
                # 1x transient rate-limit verification retry before marking gemini_web_neon cooldown
                time.sleep(2.5)
                retry_res = self.ensure_model_and_thinking(
                    tab_id,
                    model=target_model,
                    thinking=target_thinking,
                    mode=target_mode,
                    profile=prof,
                )
                if retry_res.get("ok"):
                    ensure_res = retry_res
                else:
                    print(f"[GeminiDriver] ⚠️ Model {target_model} is rate limited on {prof}: {retry_res.get('message') or ensure_res.get('message')}", file=sys.stderr)
                    try:
                        from profile_manager import mark_profile_cooldown
                        import profile_lock_manager
                        if prof:
                            profile_lock_manager.mark_bucket_cooldown(prof, "gemini_web_neon", cooldown_seconds=1800, reason=str(retry_res.get("message") or ensure_res.get("message") or "rate_limited"))
                            mark_profile_cooldown(prof, cooldown_seconds=1800)
                    except Exception:
                        pass
                    return {"ok": False, "rate_limited": True, "error": f"Model {target_model} rate limited: {retry_res.get('message') or ensure_res.get('message')}"}

            if not ensure_res.get("ok"):
                print(f"[GeminiDriver] Model/mode switch unverified ({ensure_res.get('error')}). Retrying...", file=sys.stderr)
                time.sleep(1.0)
                ensure_res = self.ensure_model_and_thinking(
                    tab_id,
                    model=target_model,
                    thinking=target_thinking,
                    mode=target_mode,
                    profile=prof,
                )
                if not ensure_res.get("ok"):
                    return {"ok": False, "error": f"Pre-send model verification gate failed: UI is not on {target_model} ({target_mode}) ({ensure_res.get('error')}). Aborting prompt send."}

        # Baseline count of existing model responses before sending
        is_fresh_session = (meta.get("turns", 0) == 0)
        if is_fresh_session:
            # Check if existing chat turns need clearing on fresh session
            count_js = "return Array.from(document.querySelectorAll('model-response')).length;"
            count_res = self.execute_js(tab_id, count_js, profile=prof)
            existing_count = (count_res.get("result") or 0) if count_res else 0
            if existing_count > 0:
                print(f"[GeminiDriver] Fresh session with {existing_count} existing response(s). Resetting to new chat...")
                reset_js = """
                const newChatBtn = Array.from(document.querySelectorAll('a, button')).find(el => {
                    const t = (el.innerText || '') + ' ' + (el.getAttribute('aria-label') || '');
                    return /new chat/i.test(t) || el.getAttribute('href') === '/app';
                });
                if (newChatBtn) {
                    newChatBtn.click();
                } else if (window.location.pathname !== '/app') {
                    window.location.href = 'https://gemini.google.com/app';
                }
                """
                self.execute_js(tab_id, reset_js, profile=prof)
                self.wait_for_page_ready(tab_id, timeout_sec=25.0, profile=prof)
            baseline = 0
        else:
            count_js = "return Array.from(document.querySelectorAll('model-response')).length;"
            count_res = self.execute_js(tab_id, count_js, profile=prof)
            baseline = (count_res.get("result") or 0) if count_res else 0

        # STEP 2: Toggle Deep Research if requested (activate container BEFORE inserting text!)
        actual_deep_research = False
        if deep_research:
            print("[GeminiDriver] [Step 2/5] Activating Deep Research pill chip...")
            dr_ok = self.ensure_deep_research(tab_id, profile=prof)
            if not dr_ok:
                print("[GeminiDriver] Retrying Deep Research toggle...", file=sys.stderr)
                time.sleep(1.0)
                dr_ok = self.ensure_deep_research(tab_id, profile=prof)
            if not dr_ok:
                raise RuntimeError("Failed to activate Deep Research mode in Gemini UI. Aborting prompt submission to prevent unwanted regular chat execution.")
            actual_deep_research = True
            print("[GeminiDriver] ✅ Deep Research pill chip confirmed active.")
            time.sleep(0.4)

        # STEP 3: Attach Context/Code Files (-f)
        if files:
            print(f"[GeminiDriver] [Step 3/5] Attaching {len(files)} file(s)...")
            up_res = self.upload_files(session_id, files)
            if not up_res.get("ok"):
                print(f"[GeminiDriver] File upload warning: {up_res.get('error')}", file=sys.stderr)
            time.sleep(0.5)

        # Run 3-Stage Popup Self-Healer before inserting prompt text
        if popup_healer:
            heal_res = popup_healer.dismiss_blocking_popups(
                eval_fn=lambda code: self.execute_js(tab_id, code, profile=prof),
                screenshot_fn=lambda out_p: self.take_screenshot(tab_id, save_path=out_p, profile=prof),
                surface="gemini_web",
                target_point=(0.5, 0.85),
            )
            if heal_res.get("blocked"):
                return {
                    "ok": False,
                    "code": "POPUP_BLOCKING_INPUT",
                    "error": f"Unknown blocking overlay on Gemini Web. Snapshot saved to {heal_res.get('anomaly_screenshot')}",
                    "anomaly": heal_res,
                }

        # STEP 4: Insert Prompt Text into Quill editor (<p> nodes via textContent — 100% immune to OS window focus & preserves chips!)
        print(f"[GeminiDriver] [Step 4/5] Inserting prompt ({len(prompt)} chars) into Quill editor...")
        prep_js = f"""
        const box = document.querySelector('rich-textarea div[contenteditable="true"], div[role="textbox"][contenteditable="true"], textarea');
        if (!box) return {{ ok: false, error: 'Prompt textbox not found' }};
        box.focus();

        const rawPrompt = {json.dumps(prompt)};
        const lines = rawPrompt.split(/\\r?\\n/);

        // Clear only <p> text nodes inside Quill editor so Deep Research chip & file cards are never touched
        const existingPs = Array.from(box.querySelectorAll('p'));
        existingPs.forEach(p => p.remove());

        let lastP = null;
        for (const line of lines) {{
            const p = document.createElement('p');
            p.textContent = line.length > 0 ? line : '\\u200b';
            box.appendChild(p);
            lastP = p;
        }}
        if (lastP) {{
            const range = document.createRange();
            range.selectNodeContents(lastP);
            range.collapse(false);
            const sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
            document.execCommand('insertText', false, ' ');
        }}

        box.classList.remove('ql-blank');
        box.dispatchEvent(new InputEvent('input', {{ bubbles: true, inputType: 'insertText', data: ' ' }}));
        box.dispatchEvent(new Event('change', {{ bubbles: true }}));
        return {{ ok: true, boxTextLen: (box.innerText || '').trim().length, lineCount: lines.length }};
        """
        prep_res = self.execute_js(tab_id, prep_js, profile=prof)
        time.sleep(0.3)

        # Wait until prompt box height reflow settles and submit/send button appears
        settle_box_js = """
        const d = window.__geminiDriver;
        let prevH = 0;
        for (let i = 0; i < 15; i++) {
            const box = document.querySelector('rich-textarea, input-area-v2');
            const btn = d.findSubmitButton();
            const h = box ? box.offsetHeight : 0;
            const btnReady = Boolean(btn && btn.getBoundingClientRect().width > 0);
            if (h > 0 && h === prevH && btnReady) break;
            prevH = h;
            await new Promise(r => setTimeout(r, 100));
        }
        return { settled: true };
        """
        self.execute_js(tab_id, settle_box_js, profile=prof)
        time.sleep(0.2)

        # STEP 5: Locate & Click Send/Task Submit button (explicit selectors + Task-mode rightmost button + CDP click + Ctrl+Enter fallback)
        print(f"[GeminiDriver] [Step 5/5] Submitting prompt via Send/Task button on {prof or 'active'}...")
        click_send_js = """
        const d = window.__geminiDriver;
        for (let i = 0; i < 15; i++) {
            const btn = d.findSubmitButton();
            if (btn && !btn.disabled && btn.getAttribute('aria-disabled') !== 'true') {
                const r = btn.getBoundingClientRect();
                const cx = Math.round(r.left + r.width / 2);
                const cy = Math.round(r.top + r.height / 2);
                btn.focus();
                await d.smartClick(btn);
                btn.click();
                const g = btn.closest("gem-icon-button");
                if (g) g.click();
                return {
                    ok: true,
                    clicked: true,
                    cx: cx,
                    cy: cy,
                    aria: btn.getAttribute('aria-label') || '',
                    testId: btn.getAttribute('data-test-id') || ''
                };
            }
            await new Promise(r => setTimeout(r, 100));
        }
        return { ok: false, error: 'Send/Submit button not ready' };
        """
        send_res = self.execute_js(tab_id, click_send_js, profile=prof)
        send_info = (send_res.get("result") or {}) if isinstance(send_res, dict) else {}
        time.sleep(0.5)

        time.sleep(0.8)
        check_submitted_js = """
        const d = window.__geminiDriver;
        const box = document.querySelector('rich-textarea div[contenteditable="true"], div[role="textbox"][contenteditable="true"], textarea');
        const text = box ? (box.innerText || '').trim() : '';
        const stopBtn = document.querySelector('button[aria-label*="Stop" i]');
        const btn = d.findSubmitButton();
        const r = btn ? btn.getBoundingClientRect() : null;
        return {
            stillHasText: Boolean(text.length > 0),
            isGenerating: Boolean(stopBtn && stopBtn.offsetWidth > 0),
            btnCx: r ? Math.round(r.left + r.width / 2) : null,
            btnCy: r ? Math.round(r.top + r.height / 2) : null
        };
        """
        sub_check = self.execute_js(tab_id, check_submitted_js, profile=prof)
        sub_res = sub_check.get("result") if isinstance(sub_check, dict) and isinstance(sub_check.get("result"), dict) else {}

        if sub_res.get("stillHasText") and not sub_res.get("isGenerating"):
            # Fallback 1: Hardware-trusted CDP click on the detected submit/up-arrow button
            btn_cx = sub_res.get("btnCx") or send_info.get("cx")
            btn_cy = sub_res.get("btnCy") or send_info.get("cy")
            if btn_cx and btn_cy:
                print(f"[GeminiDriver] Input text still present: dispatching hardware CDP click on submit button ({btn_cx}, {btn_cy})...")
                self._cdp_mouse_click(tab_id, btn_cx, btn_cy, profile=prof)
                time.sleep(0.7)
                sub_check2 = self.execute_js(tab_id, check_submitted_js, profile=prof)
                sub_res = sub_check2.get("result") if isinstance(sub_check2, dict) and isinstance(sub_check2.get("result"), dict) else {}

        if sub_res.get("stillHasText") and not sub_res.get("isGenerating"):
            # Fallback 2: Ctrl+Enter (Task mode / multi-line submit) followed by Enter
            print("[GeminiDriver] Input text still present: executing Ctrl+Enter + Enter key submission fallback...")
            try:
                self.call_cdp(tab_id, "Input.dispatchKeyEvent", params={"type": "rawKeyDown", "modifiers": 2, "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13, "key": "Enter", "code": "Enter", "text": "\r"}, profile=prof)
                self.call_cdp(tab_id, "Input.dispatchKeyEvent", params={"type": "keyUp", "modifiers": 2, "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13, "key": "Enter", "code": "Enter"}, profile=prof)
                time.sleep(0.4)
                self.call_cdp(tab_id, "Input.dispatchKeyEvent", params={"type": "rawKeyDown", "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13, "key": "Enter", "code": "Enter", "text": "\r"}, profile=prof)
                self.call_cdp(tab_id, "Input.dispatchKeyEvent", params={"type": "char", "text": "\r", "key": "Enter", "code": "Enter"}, profile=prof)
                self.call_cdp(tab_id, "Input.dispatchKeyEvent", params={"type": "keyUp", "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13, "key": "Enter", "code": "Enter"}, profile=prof)
            except Exception:
                pass

        # Poll for response completion (with Deep Research Plan-Card vs Final-Report state machine & bounded network/popup recovery)
        print(f"[GeminiDriver] Awaiting response (deep_research={deep_research}, timeout: {timeout_sec}s)...")
        start_time = time.time()
        last_change_time = time.time()
        response_started = False
        reentered_after_stall = False
        recovery_attempts = 0
        last_text = ""
        stable_count = 0
        last_heartbeat = time.time()
        screenshot_taken = False
        plan_confirmed = False
        plan_confirmed_at = 0.0
        plan_turn_count = baseline

        while time.time() - start_time < timeout_sec:
            time.sleep(max(0.0, poll_interval_sec))

            # Heartbeat lease renewal to prevent eviction during long reasoning/research
            if time.time() - last_heartbeat > 25.0:
                try:
                    with profile_lock_context(timeout=8.0):
                        from profile_lock_manager import renew_profile_lease
                        renew_profile_lease(prof or "Profile 14", agent_id=session_id, extend_seconds=180.0)
                except Exception:
                    pass
                last_heartbeat = time.time()

            poll_js = f"""
            const d = window.__geminiDriver;
            // 1. Auto-confirm Deep Research plan card if 'Start research' button appears (only once)
            const alreadyConfirmed = { 'true' if plan_confirmed else 'false' };
            const startResBtn = !alreadyConfirmed ? Array.from(document.querySelectorAll('button')).find(b => {{
                const t = ((b.innerText || '') + ' ' + (b.getAttribute('aria-label') || '')).toLowerCase().trim();
                return t.includes('start research') && !b.disabled && b.getAttribute('aria-disabled') !== 'true' && b.offsetWidth > 0;
            }}) : null;
            if (startResBtn) {{
                startResBtn.click();
                await d.smartClick(startResBtn);
                await d.sleep(600);
                const curResponses = document.querySelectorAll('model-response').length;
                return {{ status: 'clicked_start_research', count: curResponses, url: window.location.href }};
            }}

            // Check if stop button or progress bar is visible & active right away
            const stopBtn = document.querySelector('button[aria-label*="Stop" i]:not([disabled])');
            const isStopBtnVisible = Boolean(stopBtn && stopBtn.getBoundingClientRect().width > 0 && window.getComputedStyle(stopBtn).display !== 'none');
            const activeProgressEl = document.querySelector('button[aria-label*="Stop" i]:not([disabled]), mat-progress-bar, mat-spinner, [role="progressbar"]');
            const isResearchInProgress = Boolean(
                activeProgressEl && activeProgressEl.getBoundingClientRect().width > 0 && window.getComputedStyle(activeProgressEl).display !== 'none'
            );

            const responses = Array.from(document.querySelectorAll('model-response'));
            const count = responses.length;
            const immersive = document.querySelector('deep-research-immersive-panel, immersive-panel, [data-test-id*="immersive"], .deep-research-report');
            let currentChatId = null;
            if (window.location.href.includes('/app/')) {{
                const p = window.location.href.split('/app/')[1].split('?')[0].split('/');
                if (p[0]) currentChatId = p[0];
            }}

            if ((count === 0 || count <= {baseline}) && !immersive) {{
                return {{
                    status: 'waiting_for_node',
                    isGenerating: isStopBtnVisible || isResearchInProgress,
                    isStopBtnVisible: isStopBtnVisible,
                    isResearchInProgress: isResearchInProgress,
                    count: count,
                    chatId: currentChatId,
                    baseline: {baseline},
                    url: window.location.href
                }};
            }}

            const latest = responses[count - 1] || immersive;
            const mainArea = document.querySelector('main, .chat-container, .conversation-container') || document.body;
            const mainTail = mainArea ? (mainArea.innerText || '').slice(-5000) : '';
            const subagentsRunning = /\\b\\d+\\s+subagents?\\s+running\\b|\\bsubagents?\\s+running\\b/i.test(mainTail);
            const stepsPending = /\\b\\d+\\/\\d+\\s+steps\\b/i.test(mainTail) && !/\\bcompleted\\b/i.test(mainTail.slice(-400));

            // Harvest from Canvas/immersive panel if open, else pick the longest/final response turn (Task Mode spawns Turn 1 + Turn 2)
            let bestTurnText = '';
            for (const respNode of responses) {{
                const ansNode = respNode.querySelector('message-content, .model-response-text, .markdown') || respNode.querySelector('.response-content') || respNode;
                const candTxt = (ansNode.innerText || '').trim();
                if (candTxt.length > bestTurnText.length) {{
                    bestTurnText = candTxt;
                }}
            }}
            const taskStepsNode = latest ? latest.querySelector('spark-thinking-steps') : null;
            const explicitAnswerNode = latest ? latest.querySelector('message-content, .model-response-text, .markdown') : null;
            const contentNode = explicitAnswerNode || (latest ? latest.querySelector('.response-content') : null) || latest;
            let cleanText = contentNode ? (contentNode.innerText || '').trim() : '';
            if (bestTurnText.length > cleanText.length) {{
                cleanText = bestTurnText;
            }}
            if (immersive && (immersive.innerText || '').trim().length > cleanText.length) {{
                cleanText = (immersive.innerText || '').trim();
            }}
            if (taskStepsNode) {{
                if (/\\bgemini said\\b/i.test(cleanText)) {{
                    cleanText = cleanText.replace(/^[\\s\\S]*?\\bGemini said\\s*/i, '').trim();
                }} else {{
                    const stepsTxt = (taskStepsNode.innerText || '').trim();
                    if (stepsTxt && cleanText.startsWith(stepsTxt)) {{
                        cleanText = cleanText.slice(stepsTxt.length).trim();
                    }}
                }}
            }}
            cleanText = cleanText.replace(/^Gemini said\\s*/i, '').trim();
            const isTaskStepsOnly = Boolean(
                taskStepsNode && !explicitAnswerNode && !/\\bgemini said\\b/i.test((latest ? latest.innerText : '') || '')
            );
            const isTaskStepsDone = Boolean(
                taskStepsNode && /\\bcomplete\\b/i.test((taskStepsNode.innerText || ''))
            );
            if (!cleanText || cleanText.toLowerCase() === 'show code' || cleanText.toLowerCase() === 'analyzing') {{
                const codeResult = latest ? latest.querySelector('.code-result-container, code-block, pre') : null;
                if (codeResult && (codeResult.textContent || '').trim()) {{
                    cleanText = (codeResult.textContent || '').trim();
                }} else if (latest && !isTaskStepsOnly) {{
                    const rawText = (latest.textContent || '').replace(/^(?:Analyzing\\s*|Show code\\s*|Gemini said\\s*)+/i, '').trim();
                    if (rawText) cleanText = rawText;
                }}
            }}

            // (stopBtn and isStopBtnVisible already evaluated at top of poll_js)

            // Check for transient network/error overlays or Chrome offline page
            const netErrRe = /ERR_INTERNET_DISCONNECTED|network error|failed to fetch|connection lost|something went wrong|no internet/i;
            let transientNetworkError = null;
            const bodyPreview = ((document.body && document.body.innerText) || '').slice(0, 1200);
            if (/ERR_INTERNET_DISCONNECTED|No internet|This site can.?t be reached/i.test(bodyPreview)) {{
                transientNetworkError = bodyPreview.split('\\n')[0].trim() || 'ERR_INTERNET_DISCONNECTED';
            }} else {{
                const alertNodes = Array.from(document.querySelectorAll('mat-snack-bar-container, [role="alert"], .error-banner, .error-message, snack-bar-container'));
                for (const an of alertNodes) {{
                    const ar = an.getBoundingClientRect();
                    if (ar.width <= 0 || ar.height <= 0) continue;
                    const atxt = (an.innerText || '').trim();
                    if (atxt && netErrRe.test(atxt)) {{
                        transientNetworkError = atxt.slice(0, 300);
                        break;
                    }}
                }}
            }}

            // Check if Send/Submit button is back in the DOM and ready
            const sendBtn = d.findSubmitButton();
            const isSendBtnReady = Boolean(sendBtn && sendBtn.getBoundingClientRect().width > 0 && !sendBtn.disabled);

            // Ground-truth completion check on latest response or immersive panel
            const copyBtn = latest ? latest.querySelector('button[aria-label*="Copy" i], [data-test-id*="copy"]') : null;
            const actionBtns = latest ? latest.querySelectorAll('message-actions button, [aria-label*="Good response" i], [aria-label*="Bad response" i]') : [];
            const exportBtn = Array.from(document.querySelectorAll('button')).find(b => /export to docs|share & export/i.test((b.innerText || '') + ' ' + (b.getAttribute('aria-label') || '')));
            const hasFinishedActions = Boolean(copyBtn || actionBtns.length > 0 || exportBtn);

            // Detect if latest turn is still an unconfirmed Research Plan card ('Edit plan' or 'Start research' button visible & enabled)
            const isPlanCard = Boolean(
                Array.from((latest || document).querySelectorAll('button')).some(el => {{
                    if (el.disabled || el.getAttribute('aria-disabled') === 'true' || el.offsetWidth === 0) return false;
                    const t = (el.innerText || '').toLowerCase().trim();
                    return t === 'edit plan' || t === 'start research';
                }})
            );

            // (activeProgressEl and isResearchInProgress already evaluated at top of poll_js)

            // Extract chat ID from URL or top sidebar link
            let chatId = null;
            if (window.location.href.includes('/app/')) {{
                const p = window.location.href.split('/app/')[1].split('?')[0].split('/');
                if (p[0]) chatId = p[0];
            }}
            if (!chatId) {{
                const topLink = Array.from(document.querySelectorAll('a[href*="/app/"]')).find(a => !a.href.includes('accounts.google.com'));
                if (topLink && topLink.href.includes('/app/')) {{
                    const p = topLink.href.split('/app/')[1].split('?')[0].split('/');
                    if (p[0]) chatId = p[0];
                }}
            }}

            return {{
                hasFinishedActions: hasFinishedActions && !isResearchInProgress && !subagentsRunning && !stepsPending,
                hasExportBtn: Boolean(exportBtn),
                isPlanCard: isPlanCard,
                isResearchInProgress: isResearchInProgress || subagentsRunning || stepsPending,
                subagentsRunning: subagentsRunning,
                isStopBtnVisible: isStopBtnVisible || isResearchInProgress || subagentsRunning || stepsPending,
                isSendBtnReady: isSendBtnReady && !isResearchInProgress && !subagentsRunning && !stepsPending,
                isTaskStepsOnly: isTaskStepsOnly,
                isTaskStepsDone: isTaskStepsDone && !subagentsRunning && !stepsPending,
                transientNetworkError: transientNetworkError,
                text: cleanText,
                chatId: chatId,
                count: count,
                baseline: {baseline},
                url: window.location.href
            }};
            """
            current_poll_tab = self.tab_id or tab_id
            poll_res = self.execute_js(current_poll_tab, poll_js, profile=prof)
            if self.tab_id and self.tab_id != tab_id:
                tab_id = self.tab_id
                meta["tab_id"] = tab_id
                self._save_registry()

            if not (isinstance(poll_res, dict) and poll_res.get("ok") and isinstance(poll_res.get("result"), dict)):
                if recovery_attempts < max_recovery_retries:
                    recovery_attempts += 1
                    print(f"[GeminiDriver] ⚠️ Transient EVAL_DOM poll failure #{recovery_attempts}: {poll_res}. Running popup_healer + recovery...", file=sys.stderr)
                    if popup_healer:
                        try:
                            popup_healer.dismiss_blocking_popups(
                                eval_fn=lambda code: self.execute_js(tab_id, code, profile=prof),
                                screenshot_fn=lambda out_p: self.take_screenshot(tab_id, save_path=out_p, profile=prof),
                                surface="gemini_web",
                                target_point=(0.5, 0.85),
                            )
                        except Exception:
                            pass
                    self._execute_sidebar_reentry(tab_id, prof, expected_chat_id=meta.get("chat_id"))
                    last_change_time = time.time()
                    continue
                return {
                    "ok": False,
                    "code": "TRANSIENT_POLL_FAILURE",
                    "error": f"Bridge EVAL_DOM failed {recovery_attempts + 1} times during poll: {poll_res}",
                    "recovery_attempts": recovery_attempts,
                }

            data = poll_res.get("result") or {}
            if data.get("transientNetworkError"):
                net_err = str(data["transientNetworkError"])
                if recovery_attempts < max_recovery_retries:
                    recovery_attempts += 1
                    print(f"[GeminiDriver] ⚠️ Transient network/DOM error detected (#{recovery_attempts}): {net_err}. Reloading & healing popups...", file=sys.stderr)
                    self._execute_sidebar_reentry(tab_id, prof, expected_chat_id=meta.get("chat_id"))
                    if popup_healer:
                        try:
                            popup_healer.dismiss_blocking_popups(
                                eval_fn=lambda code: self.execute_js(tab_id, code, profile=prof),
                                screenshot_fn=lambda out_p: self.take_screenshot(tab_id, save_path=out_p, profile=prof),
                                surface="gemini_web",
                                target_point=(0.5, 0.85),
                            )
                        except Exception:
                            pass
                    last_change_time = time.time()
                    continue
                return {
                    "ok": False,
                    "code": "TRANSIENT_NETWORK_FAILURE",
                    "error": f"Transient network error persisted after {recovery_attempts} recovery retries: {net_err}",
                    "recovery_attempts": recovery_attempts,
                }

            # Update chat_id from polled data
            c_id = data.get("chatId")
            if c_id and not meta["chat_id"]:
                meta["chat_id"] = c_id
                meta["url"] = f"https://gemini.google.com/app/{c_id}"
                self._save_registry()

            if data.get("status") == "clicked_start_research":
                plan_confirmed = True
                plan_confirmed_at = time.time()
                plan_turn_count = data.get("count") or (baseline + 1)
                print(f"[GeminiDriver] ✅ Confirmed Deep Research Plan Card ('Start research' clicked at {round(plan_confirmed_at - start_time, 1)}s). Now awaiting multi-source synthesis...")
                try:
                    snap_p = self.take_screenshot(tab_id, save_path="temp_read/gemini_dr_started.png", profile=prof)
                    print(f"[GeminiDriver] 📸 Captured Deep Research start screenshot: {snap_p}")
                except Exception:
                    pass
                stable_count = 0
                continue

            curr_text = data.get("text", "")
            clean_body = curr_text.replace("Gemini said", "").strip()
            has_act = data.get("hasFinishedActions", False)
            has_export = data.get("hasExportBtn", False)
            is_plan_card = data.get("isPlanCard", False)
            is_stop_visible = data.get("isStopBtnVisible", False)
            is_send_ready = data.get("isSendBtnReady", False)
            turn_count = data.get("count", 0)


            # Automated visual diagnostic screenshot at 20s if still processing
            elapsed = time.time() - start_time
            if elapsed > 20.0 and not screenshot_taken:
                screenshot_taken = True
                try:
                    snap_p = self.take_screenshot(tab_id, save_path="temp_read/gemini_live.png", profile=prof)
                    print(f"[GeminiDriver] 📸 Diagnostic screenshot captured at {round(elapsed, 1)}s: {snap_p}")
                except Exception as e:
                    print(f"[GeminiDriver] Note on screenshot: {e}", file=sys.stderr)

            is_complete = False
            if actual_deep_research:
                # Deep Research Completion Guard:
                # NEVER exit before 'Start research' is confirmed (or final report 'Share & Export' / completion banner appears)!
                report_done_banner = "i've completed your research" in curr_text.lower()
                if (plan_confirmed and (time.time() - plan_confirmed_at > 15.0)) or has_export or report_done_banner:
                    # After plan confirmation, wait for either a new response turn OR a substantial report (>1200 chars)
                    # with no active research progress indicators.
                    post_plan_ready = (turn_count > plan_turn_count) or (len(clean_body) > 300 and not is_plan_card) or has_export or report_done_banner
                    if post_plan_ready and not is_stop_visible:
                        if has_export or report_done_banner or (has_act and len(clean_body) > 300):
                            stable_count += 1
                            if stable_count >= 2:
                                is_complete = True
                        elif curr_text == last_text and len(clean_body) > 300:
                            stable_count += 1
                            if stable_count >= 3:
                                is_complete = True
                        else:
                            stable_count = 0
                    else:
                        stable_count = 0
            else:
                # Standard Chat or Task Mode Completion Resolution
                is_task_steps_only = bool(data.get("isTaskStepsOnly", False))
                is_task_steps_done = bool(data.get("isTaskStepsDone", False))
                is_thinking_only = (
                    is_task_steps_only
                    or clean_body.lower() in ("analyzing", "show code", "thinking it through...", "")
                    or clean_body.strip() == ""
                )
                if len(clean_body) > 0 and turn_count > baseline and not is_stop_visible and not is_thinking_only:
                    if curr_text == last_text:
                        stable_count += 1
                        # Task mode omits Copy/feedback buttons cleanly; finish once stop disappears & text stabilizes
                        if stable_count >= 2 or has_act or (target_mode == "task" and is_task_steps_done and stable_count >= 1):
                            is_complete = True
                    else:
                        stable_count = 0
                elif turn_count > baseline and not is_stop_visible and has_act:
                    stable_count += 1
                    if stable_count >= 2:
                        is_complete = True
                else:
                    stable_count = 0

            # Recovery Check: If stop button, generating indicator, plan card, or response text is present
            is_generating = bool(data.get("isGenerating", False) or is_stop_visible or data.get("isTaskStepsOnly", False))
            if is_stop_visible or is_generating or is_plan_card or len(clean_body) > 0:
                response_started = True

            if curr_text != last_text or is_generating:
                last_change_time = time.time()

            last_text = curr_text

            if is_complete:
                meta["turns"] += 1
                self._save_registry()
                rich_data = self.harvest_rich_response(tab_id, profile=prof)

                u_info = None
                if check_usage:
                    try:
                        print(f"[GeminiDriver] Auditing live usage limits on '{prof or 'default'}' in background tab...")
                        u_info = self.get_usage_limit(profile=prof)
                        meta["last_usage"] = u_info
                        self._save_registry()
                        if u_info.get("ok"):
                            try:
                                from profile_manager import update_profile_usage_telemetry
                                if prof:
                                    update_profile_usage_telemetry(prof, u_info)
                            except Exception:
                                pass
                            curr = f"{u_info.get('current_usage_percent')}% used"
                            c_reset = f" (Resets {u_info.get('current_reset')})" if u_info.get('current_reset') else ""
                            wk = f"{u_info.get('weekly_usage_percent')}% used"
                            w_reset = f" (Resets {u_info.get('weekly_reset')})" if u_info.get('weekly_reset') else ""
                            print(f"[GeminiDriver] 📊 Usage Status ({prof or 'current'}): Current: {curr}{c_reset} | Weekly: {wk}{w_reset}")
                            if u_info.get("should_rotate"):
                                print(f"[GeminiDriver] ⚠️ High usage quota reached on {prof}! Recommend rotating profiles.", file=sys.stderr)
                    except Exception as e:
                        print(f"[GeminiDriver] Note on usage check: {e}", file=sys.stderr)
                        u_info = {"ok": False, "error": str(e)}

                out_res = {
                    "ok": True,
                    "session_id": session_id,
                    "profile": prof,
                    "chat_id": meta["chat_id"],
                    "mode": target_mode,
                    "model": target_model,
                    "thinking": target_thinking,
                    "response": (rich_data.get("markdown") if isinstance(rich_data, dict) and rich_data.get("markdown") else clean_body),
                    "text": (rich_data.get("markdown") if isinstance(rich_data, dict) and rich_data.get("markdown") else clean_body),
                    "rich": rich_data,
                    "usage": u_info,
                    "duration_seconds": round(time.time() - start_time, 1),
                }
                if clean:
                    print(f"[GeminiDriver] Auto-cleaning session '{session_id}' (keep_tab={keep_tab})...")
                    self.delete_session(session_id, profile=prof, close_tab=not keep_tab)
                return out_res

            elapsed_since_start = time.time() - start_time
            time_since_last_token = time.time() - last_change_time

            # Condition A: Loading animation & generation failed to appear after 30s
            if not response_started and not is_generating and elapsed_since_start > 30.0 and not reentered_after_stall:
                print("[GeminiDriver] ⚠️ Loading animation / response failed to appear after 30s. Executing page refresh & sidebar re-entry...", file=sys.stderr)
                reentered_after_stall = True
                self._execute_sidebar_reentry(tab_id, prof, expected_chat_id=meta.get("chat_id"))
                start_time = time.time()
                last_change_time = time.time()
                continue

            # Condition B: Response stopped midway (no new tokens for 120s / 2 minutes)
            if response_started and not is_complete and time_since_last_token > 120.0 and not reentered_after_stall:
                print("[GeminiDriver] ⚠️ Mid-stream response stall detected (no new tokens for 120s). Executing page refresh & sidebar re-entry...", file=sys.stderr)
                reentered_after_stall = True
                self._execute_sidebar_reentry(tab_id, prof)
                start_time = time.time()
                last_change_time = time.time()
                continue

        if clean:
            print(f"[GeminiDriver] Auto-cleaning session '{session_id}' after timeout (keep_tab={keep_tab})...")
            self.delete_session(session_id, profile=prof, close_tab=not keep_tab)
        return {"ok": False, "error": "Timeout waiting for response", "partial": last_text}


    def _execute_sidebar_reentry(self, tab_id: int, profile: Optional[str] = None, expected_chat_id: Optional[str] = None) -> bool:
        """Refreshes the page and clicks the matching/topmost conversation in the sidebar to resume harvesting after a stall."""
        try:
            print("[GeminiDriver] 🔄 Refreshing page via CDP to recover from stall...", file=sys.stderr)
            self.call_cdp(tab_id, "Page.reload", profile=profile)
            import time
            time.sleep(5.0)
            self.wait_for_page_ready(tab_id, timeout_sec=25.0, profile=profile)
            import json
            reenter_js = f"""
            const expectedId = {json.dumps(expected_chat_id or '')};
            if (expectedId) {{
                window.location.href = 'https://gemini.google.com/app/' + expectedId;
                return {{ ok: true, navigatedToExpected: expectedId }};
            }}
            const convLinks = Array.from(document.querySelectorAll('a[href*="/app/"]')).filter(a => !a.href.includes('accounts.google.com') && a.offsetWidth > 0);
            let target = convLinks.length > 0 ? convLinks[0] : null;
            if (target) {{
                target.click();
                return {{ ok: true, href: target.href, text: (target.innerText || '').trim() }};
            }}
            return {{ ok: true, note: 'Staying on current reloaded page' }};
            """
            res = self.execute_js(tab_id, reenter_js, profile=profile)
            print(f"[GeminiDriver] 🔄 Re-entry result: {res}")
            time.sleep(3.0)
            return bool(res and res.get("ok"))
        except Exception as e:
            print(f"[GeminiDriver] Warning during sidebar re-entry: {e}", file=sys.stderr)
            return False

    def purge_automated_test_chats(self, profile: Optional[str] = None, max_chats: int = 20) -> int:
        """Purges leftover automated test chats from the sidebar using hover -> 3-dots -> Delete -> Confirm."""
        tab = self.get_open_gemini_tab(profile=profile)
        if not tab:
            return 0
        tab_id = tab["id"]

        purge_js = r"""
        async function purgeChats() {
            const sleep = (ms) => new Promise(r => setTimeout(r, ms));
            const isVis = (el) => el && el.getBoundingClientRect().width > 0;
            const testPatterns = ['calculating seven cubed', 'google flow architecture', 'test_', 'cube of 7'];
            let deletedCount = 0;

            for (let loop = 0; loop < """ + str(max_chats) + r"""; loop++) {
                const convLinks = Array.from(document.querySelectorAll('a[href*="/app/"]')).filter(a => !a.href.includes('accounts.google.com') && isVis(a));
                let targetLink = null;
                for (const a of convLinks) {
                    const txt = (a.innerText || '').toLowerCase().trim();
                    if (testPatterns.some(p => txt.includes(p))) {
                        targetLink = a;
                        break;
                    }
                }
                if (!targetLink) break;

                const row = targetLink.closest('gem-nav-list-item, li') || targetLink.parentElement;
                row.scrollIntoView({ block: 'center' });
                row.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
                row.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                await sleep(200);

                const dotsBtn = row.querySelector('button[aria-label*="More options" i], [data-test-id="actions-menu-button"] button, button.actions-menu-button, button[aria-label*="More" i]');
                if (!dotsBtn) break;
                dotsBtn.click();
                await sleep(350);

                const items = Array.from(document.querySelectorAll('.mat-mdc-menu-item, [role="menuitem"], button'));
                const deleteOption = items.find(el => (el.innerText || '').trim().toLowerCase() === 'delete');
                if (!deleteOption) {
                    document.body.click();
                    await sleep(200);
                    break;
                }
                deleteOption.click();
                await sleep(350);

                const dialog = document.querySelector('mat-dialog-container, [role="dialog"]') || document.body;
                const confirmBtn = Array.from(dialog.querySelectorAll('button')).find(b => (b.innerText || '').trim().toLowerCase() === 'delete');
                if (confirmBtn) {
                    confirmBtn.click();
                    deletedCount++;
                    await sleep(600);
                } else {
                    document.body.click();
                    await sleep(200);
                    break;
                }
            }
            return { ok: true, deleted: deletedCount };
        }
        return await purgeChats();
        """
        res = self.execute_js(tab_id, purge_js, profile=profile)
        del_count = res.get("result", {}).get("deleted", 0) if res else 0
        print(f"[GeminiDriver] 🧹 Purged {del_count} automated test chats from sidebar on {profile or 'active'}.")
        return del_count

    def delete_chat(self, chat_id: str, profile: Optional[str] = None, max_retries: int = 2, close_tab: bool = False) -> Dict[str, Any]:
        """Deletes a chat by session_id or chat_id from sidebar. Alias for delete_session."""
        return self.delete_session(session_id=chat_id, profile=profile, max_retries=max_retries, close_tab=close_tab)

    def delete_session(self, session_id: str, profile: Optional[str] = None, max_retries: int = 2, close_tab: bool = False) -> Dict[str, Any]:
        """Deletes chat from sidebar (Hover -> 3-dots -> Delete -> Confirm modal). Retries on failure."""
        meta = self.registry.get(session_id)
        turns_sent = int(meta.get("turns", 0) or 0) if meta else 0
        if meta:
            tab_id = self.tab_id or meta.get("tab_id")
            chat_id = meta.get("chat_id")
            prof = profile or meta.get("profile") or self.default_profile
            own_tab = meta.get("own_tab", False)
        else:
            prof = profile or self.default_profile
            gem_tab = self.get_open_gemini_tab(profile=prof)
            if not gem_tab:
                return {"ok": False, "error": f"No open Gemini tab found for profile {prof}"}
            tab_id = gem_tab["id"]
            chat_id = session_id
            own_tab = False

        target_cid = chat_id or ""
        if meta and turns_sent == 0 and not target_cid:
            # No prompt/turn was ever completed; check URL only before deciding sidebar delete
            url_probe = self.execute_js(tab_id, "return window.location.href || '';", profile=prof) if tab_id else {}
            cur_url = str(url_probe.get("result") or "") if isinstance(url_probe, dict) and url_probe.get("ok") else ""
            if "/app/" in cur_url:
                extracted = cur_url.split("/app/", 1)[1].split("?", 1)[0].split("/", 1)[0].strip()
                if extracted:
                    target_cid = extracted
            if not target_cid:
                if (close_tab or own_tab) and tab_id:
                    try:
                        self._call_api("/command", {"action": "CLOSE_TAB", "agent_guarded": True, "params": {"tabId": tab_id}}, profile=prof)
                        print(f"[GeminiDriver] Closed unused agent tab {tab_id} on {prof} (skipped sidebar delete).")
                    except Exception as close_e:
                        print(f"[GeminiDriver] Could not close unused agent tab {tab_id}: {close_e}")
                if session_id in self.registry:
                    del self.registry[session_id]
                    self._save_registry()
                return {"ok": True, "skipped_sidebar_delete": True, "reason": "no_chat_created"}

        print(f"[GeminiDriver] Deleting chat {target_cid or 'latest'} from sidebar on {prof or 'active'}...")
        try:
            self._call_api("/command", {"action": "CDP_COMMAND", "params": {"tabId": tab_id, "method": "Page.bringToFront"}}, timeout=5.0, profile=prof)
        except Exception:
            pass

        del_js = f"""
        const d = window.__geminiDriver;
        const getConvLinks = () => Array.from(document.querySelectorAll('a[href*="/app/"]')).filter(a => !a.href.includes('accounts.google.com') && a.offsetWidth > 0);

        // 1. Ensure sidebar is open ONLY if conversation links are currently hidden/collapsed
        if (getConvLinks().length === 0) {{
            const closeImmersiveBtn = document.querySelector('deep-research-immersive-panel button[aria-label*="Close" i], immersive-panel button[aria-label*="Close" i]');
            if (closeImmersiveBtn && closeImmersiveBtn.offsetWidth > 0) {{
                closeImmersiveBtn.click();
                await d.sleep(300);
            }}
        }}
        if (getConvLinks().length === 0) {{
            const openSidebarBtn = document.querySelector('button[aria-label*="Open sidebar" i], button[aria-label*="Main menu" i], button[aria-label*="Expand" i]');
            if (openSidebarBtn && openSidebarBtn.offsetWidth > 0) {{
                openSidebarBtn.click();
                await d.sleep(450);
            }}
        }}

        // 2. Find conversation row in sidebar
        const convLinks = getConvLinks();
        let chatLink = null;
        let cId = '{target_cid}';
        if (!cId && window.location.href.includes('/app/')) {{
            const p = window.location.href.split('/app/')[1].split('?')[0].split('/');
            if (p[0]) cId = p[0];
        }}

        if (cId) {{
            chatLink = convLinks.find(a => a.href.includes(cId));
        }}
        if (!chatLink && convLinks.length > 0) {{
            chatLink = convLinks[0];
        }}
        if (!chatLink) return {{ ok: false, error: 'Chat row ' + (cId || 'latest') + ' not found in sidebar', totalLinks: convLinks.length }};

        const row = chatLink.closest('gem-nav-list-item, li') || chatLink.parentElement;
        row.scrollIntoView({{ block: 'center' }});
        await d.sleep(150);

        // 3. Find 3-dots More options button
        let dotsBtn = row.querySelector('button[aria-label*="More options" i], [data-test-id="actions-menu-button"] button, button[aria-label*="More" i]');
        if (!dotsBtn) return {{ ok: false, error: '3-dots menu button not found on row' }};

        dotsBtn.click();
        await d.sleep(350);

        // 4. Click 'Delete' in popup menu
        const items = Array.from(document.querySelectorAll('.mat-mdc-menu-item, [role="menuitem"], button'));
        const deleteOption = items.find(el => (el.innerText || '').trim().toLowerCase() === 'delete');
        if (!deleteOption) {{
            document.body.click();
            return {{ ok: false, error: 'Delete option not found in menu' }};
        }}
        deleteOption.click();
        await d.sleep(350);

        // 5. Click confirm 'Delete' in dialog
        const dialog = document.querySelector('mat-dialog-container, [role="dialog"]') || document.body;
        const confirmBtn = Array.from(dialog.querySelectorAll('button')).find(b => (b.innerText || '').trim().toLowerCase() === 'delete');
        if (confirmBtn) {{
            confirmBtn.click();
            await d.sleep(450);
        }} else {{
            document.body.click();
            return {{ ok: false, error: 'Confirm delete button not found in dialog' }};
        }}

        // Clean any lingering backdrops and navigate back to clean /app
        Array.from(document.querySelectorAll('.cdk-overlay-backdrop')).forEach(b => b.click());
        if (!window.location.href.endsWith('/app')) {{
            window.location.href = 'https://gemini.google.com/app';
        }}
        return {{ ok: true, deleted_chat_id: cId || 'latest' }};
        """

        res: Dict[str, Any] = {"ok": False, "error": "Not executed"}
        for attempt in range(max_retries + 1):
            if attempt > 0:
                print(f"[GeminiDriver] Deletion attempt {attempt}/{max_retries} failed or timed out. Navigating to https://gemini.google.com/app and re-injecting helper...")
                try:
                    self._call_api("/command", {"action": "CDP_COMMAND", "params": {"tabId": tab_id, "method": "Page.navigate", "params": {"url": "https://gemini.google.com/app"}}}, timeout=10.0, profile=prof)
                except Exception as nav_e:
                    print(f"[GeminiDriver] Navigation error: {nav_e}")
                time.sleep(3.0)
                try:
                    self.inject_helper(tab_id, profile=prof)
                except Exception as inj_e:
                    print(f"[GeminiDriver] Helper re-injection error: {inj_e}")
                time.sleep(0.5)

            res = self.execute_js(tab_id, del_js, profile=prof)
            if res and res.get("ok"):
                inner = res.get("result")
                if isinstance(inner, dict) and inner.get("ok"):
                    break
                err_detail = inner.get("error") if isinstance(inner, dict) else res.get("error")
                print(f"[GeminiDriver] Deletion JS reported failure on attempt {attempt}: {err_detail}")
            else:
                print(f"[GeminiDriver] execute_js failed on attempt {attempt}: {res.get('error') if res else 'None'}")

        print(f"[GeminiDriver] Deletion result: {res}")

        if close_tab or own_tab:
            try:
                self._call_api("/command", {"action": "CLOSE_TAB", "agent_guarded": True, "params": {"tabId": tab_id}}, profile=prof)
                print(f"[GeminiDriver] Closed finished agent tab {tab_id} on {prof}.")
            except Exception as close_e:
                print(f"[GeminiDriver] Could not close finished agent tab {tab_id}: {close_e}")

        if session_id in self.registry:
            del self.registry[session_id]
            self._save_registry()
        return res

    def cleanup_all(self) -> Dict[str, Any]:
        """Deletes all tracked sessions created during the tasks."""
        results = {}
        for sid in list(self.registry.keys()):
            results[sid] = self.delete_session(sid)
        return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gemini 4 Neon High Driver for gemini.google.com (Chat, Deep Research & Task)")
    parser.add_argument("prompt", nargs="?", default=None, help="Prompt to send")
    parser.add_argument("--profile", default=None, help="Target specific Chrome profile (e.g. 'Profile 13', 'Profile 14')")
    parser.add_argument("--upload", "--files", nargs="+", dest="upload", help="File paths to upload to Gemini before sending prompt")
    parser.add_argument("--model", default=None, help="Target Gemini Web model (defaults to '4 Neon' across Chat, Deep Research & Task; 4 Hydrogen/4 Carbon are blocked).")
    parser.add_argument("--mode", default="chat", choices=["chat", "task"], help="Gemini segmented execution mode: 'chat' or 'task'")
    parser.add_argument("--task", action="store_true", help="Shortcut for --mode task (parallel cloud subagent Task mode on 4 Neon High)")
    parser.add_argument("--thinking", default="High", choices=["Low", "Medium", "High"], help="Thinking level (default: High)")
    parser.add_argument("--deep-research", action="store_true", help="Enable Deep research mode (Chat mode; runs on 4 Neon High)")
    parser.add_argument("--new-chat", action="store_true", help="Open a fresh new chat session")
    parser.add_argument("--auto-clean", "--clean", action="store_true", dest="auto_clean", help="Automatically delete chat from sidebar after response")
    parser.add_argument("--keep-tab", action="store_true", help="Keep the browser tab open after auto-clean (default: closes tab on clean)")
    parser.add_argument("--usage", action="store_true", help="Audit and display live usage quota on profile without sending prompt")
    parser.add_argument("--no-usage", action="store_true", help="Skip post-request usage check")
    parser.add_argument("--session", default="main", help="Session identifier for multi-turn")
    parser.add_argument("--delete", metavar="SESSION_ID", help="Delete a specific session")
    parser.add_argument("--cleanup", action="store_true", help="Delete all tracked sessions created during tasks")
    parser.add_argument("--list", action="store_true", help="List active tracked sessions")
    parser.add_argument("--screenshot", nargs="?", const="temp_read/gemini_live.png", default=None, help="Capture live screenshot")

    args = parser.parse_args()
    driver = GeminiBrainDriver(default_profile=args.profile)
    effective_mode = "task" if args.task else args.mode

    if args.usage:
        prof = args.profile or "Profile 14"
        info = driver.get_usage_limit(profile=prof)
        print(f"\n" + "=" * 60)
        print(f" LIVE GEMINI QUOTA AUDIT: {prof}")
        print("=" * 60)
        print(f"Plan:                  {info.get('plan')}")
        print(f"Current Usage:         {info.get('current_usage_percent')}% used")
        print(f"Current Window Resets: {info.get('current_reset')}")
        print(f"Weekly Limit:          {info.get('weekly_usage_percent')}% used")
        print(f"Weekly Resets:         {info.get('weekly_reset')}")
        print(f"Should Rotate:         {info.get('should_rotate')}")
        print("=" * 60 + "\n")
        sys.exit(0)
    elif args.screenshot:
        tab = driver.get_open_gemini_tab(profile=args.profile)
        if tab:
            p = driver.take_screenshot(tab["id"], save_path=args.screenshot, profile=args.profile)
            print(f"Screenshot captured: {p}")
        else:
            print("No open Gemini tab found to screenshot.")
    elif args.list:
        print(json.dumps(driver.registry, indent=2))
    elif args.cleanup:
        res = driver.cleanup_all()
        print("Cleanup results:", json.dumps(res, indent=2))
    elif args.delete:
        res = driver.delete_session(args.delete, close_tab=not args.keep_tab)
        print("Delete result:", json.dumps(res, indent=2))
    elif args.prompt:
        sid = driver.create_session(subagent=args.session, new_chat=args.new_chat, profile_dir=args.profile)
        res = driver.ask(
            sid,
            args.prompt,
            files=args.upload,
            deep_research=args.deep_research,
            model=args.model,
            thinking=args.thinking,
            mode=effective_mode,
            check_usage=not args.no_usage,
            clean=args.auto_clean,
            keep_tab=args.keep_tab,
        )
        if res.get("ok"):
            print("\n" + "=" * 80)
            m_disp = (res.get("model") or "4 Argon").upper()
            mode_disp = (res.get("mode") or effective_mode).upper()
            print(f" GEMINI {m_disp} [{mode_disp}] RESPONSE (Session: {sid} | Chat ID: {res.get('chat_id')} | Profile: {res.get('profile')})")
            print("=" * 80)
            print(res.get("response"))
            print("=" * 80)
            print(f"Completed in {res.get('duration_seconds')}s\n")
            if res.get("usage"):
                u = res.get("usage")
                print(f"Live Quota: {u.get('current_usage_percent')}% used ({u.get('current_reset')}) | Weekly: {u.get('weekly_usage_percent')}% used")
            if args.auto_clean and sid in driver.registry:
                print(f"[GeminiDriver] Auto-cleaning session '{sid}'...")
                driver.delete_session(sid, close_tab=not args.keep_tab)
        else:
            print("Error:", res.get("error"))
    else:
        parser.print_help()
