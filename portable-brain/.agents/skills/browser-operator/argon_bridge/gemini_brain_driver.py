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

BRIDGE_URL = "http://127.0.0.1:9229"
REGISTRY_PATH = Path(__file__).parent / "gemini_sessions_registry.json"


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

    def _ensure_daemon_running(self) -> None:
        """Ensures the local server.py bridge daemon is running, launching it if offline."""
        try:
            req = urllib.request.Request(f"{self.bridge_url}/command", data=json.dumps({"action": "PING"}).encode("utf-8"), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=1.5):
                return
        except Exception:
            pass

        print("[GeminiDriver] Bridge daemon not detected. Launching server.py daemon...")
        server_py = Path(__file__).parent / "server.py"
        subprocess.Popen([sys.executable, str(server_py)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(15):
            time.sleep(0.4)
            try:
                req = urllib.request.Request(f"{self.bridge_url}/command", data=json.dumps({"action": "PING"}).encode("utf-8"), headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=1.0):
                    print("[GeminiDriver] Bridge daemon started successfully.")
                    return
            except Exception:
                pass
        print("[GeminiDriver] Warning: Bridge daemon failed to respond within 6 seconds.", file=sys.stderr)

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

    def re_discover_gemini_tab(self, profile: Optional[str] = None) -> Optional[int]:
        """Calls LIST_TABS strictly for target profile, finds active gemini.google.com tab, and updates self.tab_id."""
        prof = profile or self.default_profile
        payload: Dict[str, Any] = {"action": "LIST_TABS"}
        if prof:
            payload["profile"] = prof
        tabs_res = self._call_api_raw("/command", payload, profile=prof)
        gemini_tabs = [
            t for t in tabs_res.get("tabs", [])
            if "gemini.google.com" in t.get("url", "")
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
        """Finds an existing open Gemini tab for the target profile."""
        payload = {"action": "LIST_TABS"}
        if profile:
            payload["profile"] = profile
        res = self._call_api_raw("/command", payload, profile=profile)
        gemini_tabs = [
            t for t in res.get("tabs", [])
            if "gemini.google.com" in t.get("url", "")
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

    def get_usage_limit(self, profile: Optional[str] = None) -> Dict[str, Any]:
        """Checks live Gemini usage limits in a clean background tab (gemini.google.com/usage)."""
        prof = profile or self.default_profile or "Profile 14"
        open_payload = {"action": "OPEN_TAB", "params": {"url": "https://gemini.google.com/usage", "active": False}}
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
            close_payload = {"action": "CLOSE_TAB", "params": {"tabId": tab_id}}
            if prof:
                close_payload["profile"] = prof
            self._call_api("/command", close_payload, profile=prof)

        return usage_data

    def take_screenshot(self, tab_id: int, save_path: str = "temp_read/gemini_live.png", profile: Optional[str] = None) -> str:
        """Captures a screenshot of the tab via CDP and saves to disk."""
        out_p = Path(save_path)
        if not out_p.is_absolute():
            out_p = Path("<BRAIN_ROOT>") / out_p
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

        // 2. Check document.readyState
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

    def ensure_model_and_thinking(
        self,
        tab_id: int,
        model: str = "4 Argon",
        thinking: str = "High",
        profile: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Ensures the Gemini Web UI is set to the target model (default '4 Argon')
        and thinking level ('Low', 'Medium', 'High').
        Uses trusted CDP mouse clicks for opening picker, selecting model,
        and expanding the Thinking level sub-menu.
        """
        ready_info = self.wait_for_page_ready(tab_id, timeout_sec=25.0, profile=profile)
        if not ready_info.get("ready"):
            return {
                "ok": False,
                "error": "Page or model picker button did not become ready within 25s",
                "ready_info": ready_info,
            }

        prof = profile or self.default_profile
        model_norm = "argon" if "argon" in model.lower() else model.strip().lower()
        thinking_norm = (thinking or "High").strip().lower()

        # Step 1: Check if already set
        check_js = r"""
        return (async () => {
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

            const hasModel = ariaLower.includes('currently ' + targetModelKey) || firstLineLower === targetModelKey;
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
                print(f"[GeminiDriver] UI is in zero-state on {prof or 'active'} (account active tier: {model}). Ready for prompt.")
                return {
                    "ok": True,
                    "already_set": True,
                    "zero_state": True,
                    "model": model,
                    "thinking": thinking,
                    "current_text": f"{model} (Zero-State Default)",
                    "aria_label": "Zero-State"
                }
            return {"ok": False, "error": "Model picker button not found in DOM"}

        if st.get("matches"):
            return {
                "ok": True,
                "already_set": True,
                "current_text": st.get("text"),
                "aria_label": st.get("aria")
            }

        # Step 2: Open picker dropdown via trusted CDP mouse click
        picker_cx, picker_cy = st["cx"], st["cy"]
        self._cdp_mouse_click(tab_id, picker_cx, picker_cy, profile=prof)
        time.sleep(0.5)

        # Step 3: Scan overlay items and handle model + thinking selection
        inspect_items_js = r"""
        return (() => {
            const items = Array.from(document.querySelectorAll('gem-menu-item, [role="menuitem"], [role="menuitemradio"]')).map(el => {
                const r = el.getBoundingClientRect();
                return {
                    text: (el.innerText || '').trim().replace('\n', ' '),
                    tag: el.tagName,
                    role: el.getAttribute('role'),
                    cx: Math.round(r.left + r.width / 2),
                    cy: Math.round(r.top + r.height / 2),
                    w: r.width,
                    h: r.height,
                    selected: el.classList.contains('selected') || el.getAttribute('aria-selected') === 'true'
                };
            });
            return items;
        })()
        """
        raw_items = self.execute_js(tab_id, inspect_items_js, profile=prof)
        items = raw_items.get("result") if isinstance(raw_items, dict) and raw_items.get("ok") and isinstance(raw_items.get("result"), list) else []

        if not items:
            # Fallback to direct DOM .click() to bypass DPR scaling offsets
            self.execute_js(tab_id, "const btn = document.querySelector('button[data-test-id=\"bard-mode-menu-button\"], button.input-area-switch'); if (btn) btn.click();", profile=prof)
            time.sleep(0.5)
            raw_items = self.execute_js(tab_id, inspect_items_js, profile=prof)
            items = raw_items.get("result") if isinstance(raw_items, dict) and raw_items.get("ok") and isinstance(raw_items.get("result"), list) else []

        if not items:
            self._cdp_mouse_click(tab_id, picker_cx, picker_cy, profile=prof)
            time.sleep(0.5)
            raw_items = self.execute_js(tab_id, inspect_items_js, profile=prof)
            items = raw_items.get("result") if isinstance(raw_items, dict) and raw_items.get("ok") and isinstance(raw_items.get("result"), list) else []

        if not items:
            return {"ok": False, "error": "Model picker overlay menu did not open"}

        # 3a. Select 4 Argon if not selected
        argon_item = next((it for it in items if "argon" in it["text"].lower()), None)
        if argon_item and not argon_item.get("selected") and argon_item.get("w", 0) > 0:
            self._cdp_mouse_click(tab_id, argon_item["cx"], argon_item["cy"], profile=prof)
            time.sleep(0.5)
            raw_items = self.execute_js(tab_id, inspect_items_js, profile=prof)
            items = raw_items.get("result") if isinstance(raw_items, dict) and raw_items.get("ok") and isinstance(raw_items.get("result"), list) else []
            if not items:
                self._cdp_mouse_click(tab_id, picker_cx, picker_cy, profile=prof)
                time.sleep(0.5)
                raw_items = self.execute_js(tab_id, inspect_items_js, profile=prof)
                items = raw_items.get("result") if isinstance(raw_items, dict) and raw_items.get("ok") and isinstance(raw_items.get("result"), list) else []

        # 3b. Expand "Thinking level" sub-menu if thinking requested
        thinking_menu_btn = None
        used_native_argon = False
        if thinking_norm:
            thinking_menu_btn = next((it for it in items if "thinking level" in it["text"].lower()), None)
            if thinking_menu_btn and thinking_menu_btn.get("w", 0) > 0:
                # Dispatch CDP click and mouseenter/mouseover DOM events to guarantee submenu expansion
                self._cdp_mouse_click(tab_id, thinking_menu_btn["cx"], thinking_menu_btn["cy"], profile=prof)
                self.execute_js(tab_id, """
                (() => {
                    const items = Array.from(document.querySelectorAll('gem-menu-item, [role="menuitem"]'));
                    const tl = items.find(el => el.innerText.toLowerCase().includes('thinking level'));
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

            # Find matching target thinking item (must have w > 0, h > 0)
            target_item = next(
                (it for it in items if it["text"].lower().startswith(thinking_norm) and it.get("w", 0) > 0),
                None
            )
            if target_item:
                self._cdp_mouse_click(tab_id, target_item["cx"], target_item["cy"], profile=prof)
                self.execute_js(tab_id, f"""
                (() => {{
                    const items = Array.from(document.querySelectorAll('gem-menu-item, [role="menuitem"], [role="menuitemradio"]'));
                    const it = items.find(el => el.innerText.toLowerCase().startsWith('{thinking_norm}') && el.getBoundingClientRect().width > 0);
                    if (it) it.click();
                }})()
                """, profile=prof)
                time.sleep(0.5)
            elif argon_item and (argon_item.get("selected") or argon_item.get("w", 0) > 0):
                # In zero-state / compact mode picker, Argon is selected and has native deep reasoning active
                used_native_argon = True
                print(f"[GeminiDriver] Note: Thinking sub-menu not present in zero-state UI; proceeding with Argon native reasoning.")
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
            return {
                hasBtn: true,
                text: text,
                aria: aria,
                hasArgon: ariaLower.includes('argon') || textLower.includes('argon'),
                hasThinking: '""" + thinking_norm + r"""' === 'low' ? (!ariaLower.includes('high') && !ariaLower.includes('medium') && !textLower.includes('high') && !textLower.includes('medium')) : ('""" + thinking_norm + r"""' ? (ariaLower.includes('""" + thinking_norm + r"""') || textLower.includes('""" + thinking_norm + r"""')) : true)
            };
        })()
        """
        raw_v = self.execute_js(tab_id, verify_js, profile=prof)
        v = raw_v.get("result") if isinstance(raw_v, dict) and raw_v.get("ok") and isinstance(raw_v.get("result"), dict) else {}
        if v.get("hasArgon") and (v.get("hasThinking") or not thinking_menu_btn or used_native_argon):
            return {
                "ok": True,
                "model": model,
                "thinking": thinking,
                "current_text": v.get("text"),
                "aria_label": v.get("aria")
            }

        return {
            "ok": False,
            "error": f"Verification failed: button reads '{v.get('text')}' (aria: '{v.get('aria')}')",
            "current_text": v.get("text"),
            "aria_label": v.get("aria")
        }

    def ensure_deep_research(
        self, tab_id: int, profile: Optional[str] = None
    ) -> bool:
        """
        Ensures Deep Research mode is active in the prompt bar.
        Accurately navigates: '+' (Upload & tools) -> 'More tools' -> 'Deep Research'
        and confirms the [ ⚛ Deep research ] pill chip is active.
        """
        ready = self.wait_for_page_ready(tab_id, timeout_sec=25.0, profile=profile)
        if not ready.get("ready"):
            return False

        activate_js = r"""
        const sleep = (ms) => new Promise(r => setTimeout(r, ms));
        const isVis = (el) => {
            if (!el) return false;
            const r = el.getBoundingClientRect();
            const s = window.getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
        };

        // 1. Check if Deep research pill chip is already active in prompt bar
        const inputArea = document.querySelector(
            'input-container, .input-area-container, .text-input-field, form, rich-textarea'
        ) || document.body;
        const existingChips = Array.from(inputArea.querySelectorAll(
            'button, mat-chip, .tool-chip, [role="button"], .pill'
        )).filter(isVis);

        for (const c of existingChips) {
            const txt = ((c.innerText || '') + ' ' + (c.getAttribute('aria-label') || '')).toLowerCase();
            if (txt.includes('deep research') && !c.closest('.cdk-overlay-container')) {
                return { ok: true, mode: 'deep_research', note: 'already_active' };
            }
        }

        // 2. Click '+' (Upload & tools) button
        const plusBtn = Array.from(document.querySelectorAll(
            'button[aria-label*="Upload & tools" i], ' +
            'button[aria-label*="Upload and tools" i], ' +
            'gem-icon-button.menu-button button, ' +
            'button[aria-label*="Upload" i]'
        )).find(isVis);

        if (!plusBtn) {
            return { ok: false, error: 'Upload & tools button not found' };
        }

        plusBtn.click();
        await sleep(500);

        // 3. Find and click 'More tools' button in the tools drawer
        let moreToolsBtn = null;
        for (let attempt = 0; attempt < 12; attempt++) {
            moreToolsBtn = Array.from(document.querySelectorAll(
                'button.more-tools-button, ' +
                'button.toolbox-drawer-menu-item, ' +
                'button[aria-label="More tools"], ' +
                '.cdk-overlay-pane button'
            )).filter(isVis).find(b => {
                const t = ((b.innerText || '') + ' ' + (b.getAttribute('aria-label') || '')).toLowerCase().trim();
                return t.includes('more tools');
            });
            if (moreToolsBtn) break;
            await sleep(150);
        }

        if (!moreToolsBtn) {
            return { ok: false, error: 'More tools button not found in tools drawer' };
        }

        moreToolsBtn.click();
        await sleep(500);

        // 4. Find and click 'Deep research' button in the submenu
        let deepResearchBtn = null;
        for (let attempt = 0; attempt < 12; attempt++) {
            deepResearchBtn = Array.from(document.querySelectorAll(
                '.cdk-overlay-pane button, ' +
                'button, ' +
                '[role="menuitem"], ' +
                '.mat-mdc-list-item'
            )).filter(isVis).find(b => {
                const t = ((b.innerText || '') + ' ' + (b.getAttribute('aria-label') || '')).toLowerCase().trim();
                return t === 'deep research' || t.includes('deep research');
            });
            if (deepResearchBtn) break;
            await sleep(150);
        }

        if (!deepResearchBtn) {
            return { ok: false, error: 'Deep research option not found in More tools submenu' };
        }

        deepResearchBtn.click();
        await sleep(600);

        // 5. Verify the pill chip is mounted in the input area
        const chipsAfter = Array.from(inputArea.querySelectorAll(
            'button, mat-chip, .tool-chip, [role="button"], .pill'
        )).filter(isVis);

        for (const c of chipsAfter) {
            const txt = ((c.innerText || '') + ' ' + (c.getAttribute('aria-label') || '')).toLowerCase();
            if (txt.includes('deep research') && !c.closest('.cdk-overlay-container')) {
                return { ok: true, mode: 'deep_research' };
            }
        }

        return { ok: false, error: 'Deep Research chip not verified in prompt bar after clicking' };
        """

        raw_res = self.execute_js(tab_id, activate_js, profile=profile)
        res_data = raw_res.get("result") if isinstance(raw_res, dict) and raw_res.get("ok") and isinstance(raw_res.get("result"), dict) else raw_res
        return bool(isinstance(res_data, dict) and res_data.get("ok"))

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

        # Auto-boot Chrome if no Gemini tab is currently open on this profile
        tab = self.get_open_gemini_tab(profile=prof)
        if not tab:
            try:
                from profile_manager import get_next_available_profile, launch_profile_window
                target_p = get_next_available_profile(preferred=prof)
                p_dir = target_p.dir_name if target_p else prof
                print(f"[GeminiDriver] No active Gemini tab detected for '{p_dir}'. Booting Chrome profile window...")
                launch_profile_window(p_dir, "https://gemini.google.com/app")
                for _ in range(25):
                    time.sleep(0.5)
                    tab = self.get_open_gemini_tab(profile=prof)
                    if tab:
                        print(f"[GeminiDriver] Profile '{p_dir}' connected on Tab {tab['id']}.")
                        break
            except Exception as e:
                print(f"[GeminiDriver] Auto-boot note: {e}", file=sys.stderr)

        if own_tab:
            # Spawn dedicated background tab
            open_res = self._call_api("/command", {"action": "OPEN_TAB", "params": {"url": "https://gemini.google.com/app", "active": False}}, profile=prof)
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
                open_res = self._call_api("/command", {"action": "OPEN_TAB", "params": {"url": "https://gemini.google.com/app", "active": True}}, profile=prof)
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
                p = Path("<BRAIN_ROOT>") / p
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
        model: str = "4 Argon",
        thinking: str = "High",
        check_usage: bool = True,
        timeout_sec: int = 300,
    ) -> Dict[str, Any]:
        """
        Executes a strict 5-Step Pre-Send Sequence:
        1. Verify Model=Argon & Thinking=High
        2. Insert Prompt Text into Quill (<p> nodes, preserving chips & avoiding raw '\\n' Enter-submit)
        3. Attach Context/Code Files (-f)
        4. Toggle Deep Research (if enabled) & verify '[ ⚛ Deep research ]' pill chip
        5. Dispatch Trusted Send Click & Poll Completion (with Deep Research Plan-Card Guard)
        """
        if session_id not in self.registry:
            self.create_session(session_id=session_id)

        meta = self.registry[session_id]
        tab_id = meta["tab_id"]
        prof = meta.get("profile") or self.default_profile

        # STEP 1: Ensure Model = 4 Argon & Thinking = High
        print(f"[GeminiDriver] [Step 1/5] Ensuring Model={model} and Thinking={thinking} on {prof or 'active'}...")
        ensure_res = self.ensure_model_and_thinking(tab_id, model=model, thinking=thinking, profile=prof)
        if self.tab_id and self.tab_id != tab_id:
            tab_id = self.tab_id
            meta["tab_id"] = tab_id
            self._save_registry()
        if not ensure_res.get("ok"):
            if ensure_res.get("rate_limited"):
                print(f"[GeminiDriver] ⚠️ Model {model} is rate limited on {prof}: {ensure_res.get('message')}", file=sys.stderr)
                try:
                    from profile_manager import mark_profile_cooldown
                    if prof:
                        mark_profile_cooldown(prof, cooldown_seconds=1800)
                except Exception:
                    pass
                return {"ok": False, "rate_limited": True, "error": f"Model {model} rate limited: {ensure_res.get('message')}"}

            print(f"[GeminiDriver] Model switch unverified ({ensure_res.get('error')}). Retrying...", file=sys.stderr)
            time.sleep(1.0)
            ensure_res = self.ensure_model_and_thinking(tab_id, model=model, thinking=thinking, profile=prof)
            if not ensure_res.get("ok"):
                return {"ok": False, "error": f"Pre-send model verification gate failed: UI is not on {model} ({ensure_res.get('error')}). Aborting prompt send."}

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

        # Wait until prompt box height reflow settles and send button slides in
        settle_box_js = """
        let prevH = 0;
        for (let i = 0; i < 15; i++) {
            const box = document.querySelector('rich-textarea');
            const btn = document.querySelector('button[aria-label="Send message"], gem-icon-button.send-button button, button[aria-label*="Send" i]');
            const h = box ? box.offsetHeight : 0;
            const btnReady = btn && btn.getBoundingClientRect().width > 0;
            if (h > 0 && h === prevH && btnReady) break;
            prevH = h;
            await new Promise(r => setTimeout(r, 100));
        }
        return { settled: true };
        """
        self.execute_js(tab_id, settle_box_js, profile=prof)
        time.sleep(0.2)

        # STEP 5: Locate & Click Send button (direct DOM .click() + Enter fallback)
        print(f"[GeminiDriver] [Step 5/5] Submitting prompt via Send button on {prof or 'active'}...")
        click_send_js = """
        for (let i = 0; i < 15; i++) {
            const btn = document.querySelector('button[aria-label="Send message"], gem-icon-button.send-button button, button[aria-label*="Send" i]');
            if (btn && !btn.disabled && btn.getAttribute('aria-disabled') !== 'true') {
                btn.focus();
                btn.click();
                const g = btn.closest("gem-icon-button");
                if (g) g.click();
                return { ok: true, clicked: true };
            }
            await new Promise(r => setTimeout(r, 100));
        }
        return { ok: false, error: 'Send button not ready' };
        """
        send_res = self.execute_js(tab_id, click_send_js, profile=prof)
        time.sleep(0.5)

        time.sleep(0.8)
        check_submitted_js = """
        const box = document.querySelector('rich-textarea div[contenteditable="true"], div[role="textbox"][contenteditable="true"], textarea');
        const text = box ? (box.innerText || '').trim() : '';
        const stopBtn = document.querySelector('button[aria-label*="Stop" i]');
        return { stillHasText: Boolean(text.length > 0), isGenerating: Boolean(stopBtn && stopBtn.offsetWidth > 0) };
        """
        sub_check = self.execute_js(tab_id, check_submitted_js, profile=prof)
        sub_res = sub_check.get("result") if sub_check else {}

        if sub_res.get("stillHasText") and not sub_res.get("isGenerating"):
            print("[GeminiDriver] Input text still present: executing Enter key submission fallback...")
            try:
                self.call_cdp(tab_id, "Input.dispatchKeyEvent", params={"type": "rawKeyDown", "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13, "key": "Enter", "code": "Enter", "text": "\r"}, profile=prof)
                self.call_cdp(tab_id, "Input.dispatchKeyEvent", params={"type": "char", "text": "\r", "key": "Enter", "code": "Enter"}, profile=prof)
                self.call_cdp(tab_id, "Input.dispatchKeyEvent", params={"type": "keyUp", "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13, "key": "Enter", "code": "Enter"}, profile=prof)
            except Exception:
                pass

        # Poll for response completion (with Deep Research Plan-Card vs Final-Report state machine)
        print(f"[GeminiDriver] Awaiting response (deep_research={deep_research}, timeout: {timeout_sec}s)...")
        start_time = time.time()
        last_change_time = time.time()
        response_started = False
        reentered_after_stall = False
        last_text = ""
        stable_count = 0
        last_heartbeat = time.time()
        screenshot_taken = False
        plan_confirmed = False
        plan_confirmed_at = 0.0
        plan_turn_count = baseline

        while time.time() - start_time < timeout_sec:
            time.sleep(2.5)

            # Heartbeat lease renewal to prevent eviction during long reasoning/research
            if time.time() - last_heartbeat > 25.0:
                try:
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
            const contentNode = latest ? (latest.querySelector('message-content, .model-response-text, .response-content, .markdown') || latest) : null;
            let cleanText = contentNode ? (contentNode.innerText || '').trim() : '';
            if (immersive && (immersive.innerText || '').trim().length > cleanText.length) {{
                cleanText = (immersive.innerText || '').trim();
            }}
            cleanText = cleanText.replace(/^Gemini said\\s*/i, '').trim();
            if (!cleanText || cleanText.toLowerCase() === 'show code' || cleanText.toLowerCase() === 'analyzing') {{
                const codeResult = latest ? latest.querySelector('.code-result-container, code-block, pre') : null;
                if (codeResult && (codeResult.textContent || '').trim()) {{
                    cleanText = (codeResult.textContent || '').trim();
                }} else if (latest) {{
                    const rawText = (latest.textContent || '').replace(/^(?:Analyzing\\s*|Show code\\s*|Gemini said\\s*)+/i, '').trim();
                    if (rawText) cleanText = rawText;
                }}
            }}

            // (stopBtn and isStopBtnVisible already evaluated at top of poll_js)

            // Check if Send button is back in the DOM and ready
            const sendBtn = document.querySelector('button[aria-label="Send message"], gem-icon-button.send-button button, button[aria-label*="Send" i]');
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
                hasFinishedActions: hasFinishedActions && !isResearchInProgress,
                hasExportBtn: Boolean(exportBtn),
                isPlanCard: isPlanCard,
                isResearchInProgress: isResearchInProgress,
                isStopBtnVisible: isStopBtnVisible || isResearchInProgress,
                isSendBtnReady: isSendBtnReady && !isResearchInProgress,
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
            data = (poll_res.get("result") or {}) if poll_res else {}

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
                # Standard Argon High-Thinking Completion Resolution
                is_thinking_only = clean_body.lower() in ("analyzing", "show code", "") or clean_body.strip() == ""
                if len(clean_body) > 0 and turn_count > baseline and not is_stop_visible and not is_thinking_only:
                    if curr_text == last_text:
                        stable_count += 1
                        if stable_count >= 2 or has_act:
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
            is_generating = bool(data.get("isGenerating", False) or is_stop_visible)
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

                return {
                    "ok": True,
                    "session_id": session_id,
                    "profile": prof,
                    "chat_id": meta["chat_id"],
                    "response": (rich_data.get("markdown") if isinstance(rich_data, dict) and rich_data.get("markdown") else clean_body),
                    "text": (rich_data.get("markdown") if isinstance(rich_data, dict) and rich_data.get("markdown") else clean_body),
                    "rich": rich_data,
                    "usage": u_info,
                    "duration_seconds": round(time.time() - start_time, 1),
                }

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

    def delete_session(self, session_id: str, profile: Optional[str] = None) -> Dict[str, Any]:
        """Deletes chat from sidebar (Hover -> 3-dots -> Delete -> Confirm modal)."""
        meta = self.registry.get(session_id)
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
        res = self.execute_js(tab_id, del_js, profile=prof)
        print(f"[GeminiDriver] Deletion result: {res}")

        if meta and meta.get("own_tab"):
            try:
                self._call_api("/command", {"action": "CLOSE_TAB", "params": {"tabId": tab_id}}, profile=prof)
            except Exception:
                pass

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
    parser = argparse.ArgumentParser(description="Gemini 4 Argon Driver for gemini.google.com")
    parser.add_argument("prompt", nargs="?", default=None, help="Prompt to send")
    parser.add_argument("--profile", default=None, help="Target specific Chrome profile (e.g. 'Profile 13', 'Profile 14')")
    parser.add_argument("--upload", "--files", nargs="+", dest="upload", help="File paths to upload to Gemini before sending prompt")
    parser.add_argument("--thinking", default="High", choices=["Low", "Medium", "High"], help="Thinking level")
    parser.add_argument("--deep-research", action="store_true", help="Enable Deep research mode")
    parser.add_argument("--new-chat", action="store_true", help="Open a fresh new chat session")
    parser.add_argument("--auto-clean", action="store_true", help="Automatically delete chat from sidebar after response")
    parser.add_argument("--usage", action="store_true", help="Audit and display live usage quota on profile without sending prompt")
    parser.add_argument("--no-usage", action="store_true", help="Skip post-request usage check")
    parser.add_argument("--session", default="main", help="Session identifier for multi-turn")
    parser.add_argument("--delete", metavar="SESSION_ID", help="Delete a specific session")
    parser.add_argument("--cleanup", action="store_true", help="Delete all tracked sessions created during tasks")
    parser.add_argument("--list", action="store_true", help="List active tracked sessions")
    parser.add_argument("--screenshot", nargs="?", const="temp_read/gemini_live.png", default=None, help="Capture live screenshot")

    args = parser.parse_args()
    driver = GeminiBrainDriver(default_profile=args.profile)

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
        res = driver.delete_session(args.delete)
        print("Delete result:", json.dumps(res, indent=2))
    elif args.prompt:
        sid = driver.create_session(subagent=args.session, new_chat=args.new_chat, profile_dir=args.profile)
        res = driver.ask(sid, args.prompt, files=args.upload, deep_research=args.deep_research, thinking=args.thinking, check_usage=not args.no_usage)
        if res.get("ok"):
            print("\n" + "=" * 80)
            print(f" GEMINI 4 ARGON RESPONSE (Session: {sid} | Chat ID: {res.get('chat_id')} | Profile: {res.get('profile')})")
            print("=" * 80)
            print(res.get("response"))
            print("=" * 80)
            print(f"Completed in {res.get('duration_seconds')}s\n")
            if res.get("usage"):
                u = res.get("usage")
                print(f"Live Quota: {u.get('current_usage_percent')}% used ({u.get('current_reset')}) | Weekly: {u.get('weekly_usage_percent')}% used")
            if args.auto_clean:
                print(f"[GeminiDriver] Auto-cleaning session '{sid}'...")
                driver.delete_session(sid)
        else:
            print("Error:", res.get("error"))
    else:
        parser.print_help()
