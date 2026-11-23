#!/usr/bin/env python3
"""popup_healer.py - 3-Stage Popup Defense & Self-Healing UI Guardian.

Stage 1 (Liveness Guard): Detects active thinking/generating/cloud-subagents so drivers
never mistake live work for a stalled modal.
Stage 2 (Safe Dismiss): Runs elementFromPoint(x, y) & overlay scans; clicks ONLY
whitelisted dismiss verbs and strictly refuses forbidden consent/upgrade/Drive verbs.
Stage 3 (Telemetry & Self-Heal): Captures ui_anomaly_<surface>_<ts>.{png,json} when
an unknown blocking overlay remains, and can append validated selectors to popup_rules.json.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

RULES_PATH = Path(__file__).parent / "popup_rules.json"

DEFAULT_RULES: Dict[str, Any] = {
    "version": 1,
    "safe_dismiss_labels": [
        "close",
        "dismiss",
        "no thanks",
        "not now",
        "skip",
        "got it",
        "ok",
        "maybe later",
        "no, thanks",
        "×",
        "x",
    ],
    "forbidden_labels": [
        "connect drive",
        "connect google drive",
        "turn on",
        "accept",
        "upgrade",
        "allow",
        "sign in",
        "delete",
        "continue",
        "subscribe",
        "get started",
        "try ultra",
        "enable",
    ],
    "known_selectors": [],
}


def load_popup_rules() -> Dict[str, Any]:
    if RULES_PATH.exists():
        try:
            data = json.loads(RULES_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return dict(DEFAULT_RULES)


def append_popup_rule(selector: str, surface: str, note: str = "") -> Dict[str, Any]:
    """Appends a newly discovered safe-dismiss selector to popup_rules.json."""
    rules = load_popup_rules()
    known = rules.setdefault("known_selectors", [])
    entry = {"surface": surface, "selector": selector, "note": note or f"Added {time.strftime('%Y-%m-%d')}"}
    if not any(isinstance(item, dict) and item.get("selector") == selector and item.get("surface") == surface for item in known):
        known.append(entry)
        RULES_PATH.write_text(json.dumps(rules, indent=2), encoding="utf-8")
    return rules


def is_active_work_js() -> str:
    """Stage 1 Liveness Guard JS: returns {active: bool, reasons: [...]}."""
    return r"""(() => {
        const reasons = [];
        const stopSel = "button[aria-label*='Stop' i], button[mattooltip*='Stop' i], .stop-button, button.send-button[aria-label*='Stop' i]";
        const stopEl = document.querySelector(stopSel);
        if (stopEl && stopEl.offsetWidth > 0 && getComputedStyle(stopEl).display !== 'none') {
            reasons.push("stop_button_visible");
        }
        const main = document.querySelector("main, .chat-container, .conversation-container") || document.body;
        const txt = (main && main.innerText) ? main.innerText.slice(-4000) : "";
        if (/\b\d+\s+subagents?\s+running\b/i.test(txt) || /\bsubagents?\s+running\b/i.test(txt)) {
            reasons.push("subagents_running");
        }
        if (/\b\d+\/\d+\s+steps\b/i.test(txt) && !/\bcompleted\b/i.test(txt.slice(-300))) {
            reasons.push("steps_in_progress");
        }
        const spinners = Array.from(document.querySelectorAll("main mat-progress-spinner, main [role='progressbar'], .thinking-indicator"));
        if (spinners.some(s => s.offsetWidth > 0 && getComputedStyle(s).display !== 'none')) {
            reasons.push("active_spinner");
        }
        return { active: reasons.length > 0, reasons };
    })()"""


def check_liveness(eval_fn: Callable[[str], Any]) -> Dict[str, Any]:
    """Runs Stage 1 Liveness Guard via caller's eval function."""
    try:
        res = eval_fn(is_active_work_js())
        if isinstance(res, dict) and isinstance(res.get("result"), dict):
            return res["result"]
        if isinstance(res, dict) and "active" in res:
            return res
    except Exception as e:
        return {"active": False, "reasons": [], "error": str(e)}
    return {"active": False, "reasons": []}


def build_safe_dismiss_js(surface: str, target_point: Tuple[float, float] = (0.5, 0.85), rules: Optional[Dict[str, Any]] = None) -> str:
    """Builds Stage 2 JS: inspects overlays & elementFromPoint, dismisses strictly safe modals."""
    cfg = rules or load_popup_rules()
    safe_labels = [str(s).lower() for s in cfg.get("safe_dismiss_labels", DEFAULT_RULES["safe_dismiss_labels"])]
    forbidden = [str(s).lower() for s in cfg.get("forbidden_labels", DEFAULT_RULES["forbidden_labels"])]
    selectors = [
        item["selector"]
        for item in cfg.get("known_selectors", [])
        if isinstance(item, dict) and item.get("selector") and item.get("surface") in (surface, "all", "*")
    ]
    return f"""(() => {{
        const safeLabels = {json.dumps(safe_labels)};
        const forbidden = {json.dumps(forbidden)};
        const knownSelectors = {json.dumps(selectors)};
        const vw = window.innerWidth || 1280;
        const vh = window.innerHeight || 800;
        const tx = Math.max(1, Math.min(vw - 2, Math.round(vw * {float(target_point[0])})));
        const ty = Math.max(1, Math.min(vh - 2, Math.round(vh * {float(target_point[1])})));

        function isVisible(el) {{
            if (!el) return false;
            const st = getComputedStyle(el);
            if (st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0') return false;
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
        }}

        function normLabel(el) {{
            const raw = (el.getAttribute('aria-label') || el.innerText || el.textContent || el.getAttribute('title') || '').trim().toLowerCase();
            return raw.replace(/\\s+/g, ' ');
        }}

        function isForbidden(lbl) {{
            if (!lbl) return true;
            return forbidden.some(f => lbl.includes(f));
        }}

        function isSafe(lbl) {{
            if (!lbl || isForbidden(lbl)) return false;
            return safeLabels.some(s => lbl === s || lbl.startsWith(s + ' ') || (s.length >= 2 && lbl === s));
        }}

        const clicked = [];
        // 1. Try known selectors inside active dialogs/overlays first
        for (const sel of knownSelectors) {{
            try {{
                const els = Array.from(document.querySelectorAll(sel));
                for (const el of els) {{
                    if (!isVisible(el)) continue;
                    const lbl = normLabel(el);
                    if (!lbl || !isForbidden(lbl)) {{
                        el.click();
                        clicked.push({{ method: 'known_selector', selector: sel, label: lbl }});
                    }}
                }}
            }} catch (e) {{}}
        }}

        // 2. Scan active dialog / modal / overlay panes (exclude normal model/menu pickers)
        const dialogNodes = Array.from(document.querySelectorAll("mat-dialog-container, [role='dialog'], [role='alertdialog'], .cdk-overlay-pane dialog, .modal-dialog"));
        const visibleDialogs = dialogNodes.filter(d => isVisible(d));
        for (const dlg of visibleDialogs) {{
            const btns = Array.from(dlg.querySelectorAll("button, [role='button'], a[role='button']"));
            for (const b of btns) {{
                if (!isVisible(b) || b.disabled) continue;
                const lbl = normLabel(b);
                if (isSafe(lbl)) {{
                    b.click();
                    clicked.push({{ method: 'safe_whitelist', label: lbl }});
                    break;
                }}
            }}
        }}

        // 3. Check if an overlay still blocks the target interaction coordinate
        const topEl = document.elementFromPoint(tx, ty);
        const blockingOverlay = topEl ? topEl.closest("mat-dialog-container, [role='dialog'], [role='alertdialog'], .cdk-overlay-backdrop, .cdk-overlay-pane") : null;
        let anomaly = null;
        if (blockingOverlay && isVisible(blockingOverlay)) {{
            const r = blockingOverlay.getBoundingClientRect();
            const btns = Array.from(blockingOverlay.querySelectorAll("button, [role='button']")).slice(0, 8).map(b => ({{
                label: normLabel(b),
                aria: b.getAttribute('aria-label') || '',
                classes: b.className || ''
            }}));
            anomaly = {{
                tag: blockingOverlay.tagName,
                ariaLabel: blockingOverlay.getAttribute('aria-label') || '',
                rect: {{ x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }},
                buttons: btns,
                htmlSnippet: (blockingOverlay.outerHTML || '').slice(0, 800)
            }};
        }}

        return {{
            ok: true,
            dismissed_count: clicked.length,
            clicked,
            blocked: Boolean(anomaly),
            anomaly
        }};
    }})()"""


def dismiss_blocking_popups(
    eval_fn: Callable[[str], Any],
    screenshot_fn: Optional[Callable[[str], Any]] = None,
    surface: str = "gemini_web",
    target_point: Tuple[float, float] = (0.5, 0.85),
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Runs the 3-Stage Popup Defense pipeline. Returns {blocked, dismissed_count, ...}."""
    # Stage 1: Liveness guard (do not interfere if actively generating)
    liveness = check_liveness(eval_fn)
    if liveness.get("active"):
        return {"ok": True, "blocked": False, "liveness_active": True, "reasons": liveness.get("reasons", [])}

    # Stage 2: Safe whitelist dismissal
    js = build_safe_dismiss_js(surface=surface, target_point=target_point)
    raw = eval_fn(js)
    res = raw.get("result", raw) if isinstance(raw, dict) and isinstance(raw.get("result"), dict) else raw
    if not isinstance(res, dict):
        res = {"ok": False, "blocked": False, "raw": str(raw)}

    # Stage 3: Unknown modal capture for self-healing
    if res.get("blocked") and res.get("anomaly"):
        root = Path(project_root) if project_root else Path(r"./")
        temp_dir = root / "temp_read"
        temp_dir.mkdir(parents=True, exist_ok=True)
        ts = int(time.time())
        json_path = temp_dir / f"ui_anomaly_{surface}_{ts}.json"
        png_path = temp_dir / f"ui_anomaly_{surface}_{ts}.png"
        json_path.write_text(json.dumps({"surface": surface, "timestamp": ts, **res}, indent=2), encoding="utf-8")
        if screenshot_fn:
            try:
                screenshot_fn(str(png_path))
                res["anomaly_screenshot"] = str(png_path)
            except Exception as e:
                res["screenshot_error"] = str(e)
        res["anomaly_json"] = str(json_path)

    return res
