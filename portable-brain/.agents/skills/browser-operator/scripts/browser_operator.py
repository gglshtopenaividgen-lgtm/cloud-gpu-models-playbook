#!/usr/bin/env python3
"""browser_operator.py - Generalized Full Browser Operation & Multi-Profile CDP CLI.

Part of the browser-operator universal skill.
Controls authentic user Chrome profiles via the local WebSocket/CDP bridge daemon
(http://127.0.0.1:9229) across ANY arbitrary website (SPAs, cloud consoles,
enterprise portals, e-commerce, local dev apps, and Google apps) with:
  - Tab & window lifecycle management (tabs, new-tab, switch-tab, close-tab, back, forward, reload)
  - Rich navigation & waiting (URL, selector, text, element disappearance, DOM/network settle)
  - Zero-vision observation across main DOM, open Shadow DOM, and same-origin iframes
  - Structured extraction (markdown, tables, KPIs, links, forms, metadata, console/network errors)
  - Trusted CDP hardware input, React/Angular-safe value setters, stealth motion, arbitrary hotkeys
  - Virtualized container scanning, 3-tier file upload, JS dialog handling, 2FA/CAPTCHA circuit breaker
  - Single-process multi-step `run-goal` pipelines
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import io
import json
import os
import struct
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

VERSION = "3.1.0"
BRIDGE_URL = os.environ.get("ARGON_BRIDGE_URL", "http://127.0.0.1:9229")
SKILL_DIR = Path(__file__).resolve().parent.parent
ARGON_BRIDGE_DIR = SKILL_DIR / "argon_bridge"
SERVER_PY = ARGON_BRIDGE_DIR / "server.py"

if str(ARGON_BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(ARGON_BRIDGE_DIR))

try:
    import stealth_input  # type: ignore
except Exception:
    stealth_input = None  # type: ignore


# ==============================================================================
# KEYBOARD & MODIFIER MAPPINGS (CDP Input.dispatchKeyEvent)
# ==============================================================================

MODIFIER_BITS = {
    "alt": 1,
    "option": 1,
    "ctrl": 2,
    "control": 2,
    "meta": 4,
    "cmd": 4,
    "command": 4,
    "win": 4,
    "shift": 8,
}

SPECIAL_KEYS: Dict[str, Tuple[str, str, int]] = {
    "enter": ("Enter", "Enter", 13),
    "return": ("Enter", "Enter", 13),
    "esc": ("Escape", "Escape", 27),
    "escape": ("Escape", "Escape", 27),
    "tab": ("Tab", "Tab", 9),
    "backspace": ("Backspace", "Backspace", 8),
    "delete": ("Delete", "Delete", 46),
    "del": ("Delete", "Delete", 46),
    "space": (" ", "Space", 32),
    "arrowup": ("ArrowUp", "ArrowUp", 38),
    "up": ("ArrowUp", "ArrowUp", 38),
    "arrowdown": ("ArrowDown", "ArrowDown", 40),
    "down": ("ArrowDown", "ArrowDown", 40),
    "arrowleft": ("ArrowLeft", "ArrowLeft", 37),
    "left": ("ArrowLeft", "ArrowLeft", 37),
    "arrowright": ("ArrowRight", "ArrowRight", 39),
    "right": ("ArrowRight", "ArrowRight", 39),
    "home": ("Home", "Home", 36),
    "end": ("End", "End", 35),
    "pageup": ("PageUp", "PageUp", 33),
    "pagedown": ("PageDown", "PageDown", 34),
    "period": (".", "Period", 190),
    ".": (".", "Period", 190),
    ",": (",", "Comma", 188),
    "/": ("/", "Slash", 191),
    "-": ("-", "Minus", 189),
    "=": ("=", "Equal", 187),
}
for _fn in range(1, 13):
    SPECIAL_KEYS[f"f{_fn}"] = (f"F{_fn}", f"F{_fn}", 111 + _fn)


def parse_key_combo(combo: str) -> Tuple[str, str, int, int]:
    """Parses a key combo like 'Control+Shift+R' or 'Enter' into (key, code, vk, modifiers)."""
    raw = (combo or "").strip()
    if not raw:
        raise ValueError("Empty key combination")
    if raw == "+":
        return "+", "Equal", 187, 8

    parts = [p.strip() for p in raw.split("+") if p.strip()]
    modifiers = 0
    key_part = parts[-1]
    for mod in parts[:-1]:
        bit = MODIFIER_BITS.get(mod.lower())
        if bit is None:
            raise ValueError(f"Unknown modifier '{mod}' in '{combo}'")
        modifiers |= bit

    lower_k = key_part.lower()
    if lower_k in SPECIAL_KEYS:
        k, c, vk = SPECIAL_KEYS[lower_k]
        return k, c, vk, modifiers

    if len(key_part) == 1:
        ch = key_part
        upper = ch.upper()
        if "A" <= upper <= "Z":
            return ch, f"Key{upper}", ord(upper), modifiers
        if "0" <= ch <= "9":
            return ch, f"Digit{ch}", ord(ch), modifiers
        return ch, "", ord(upper), modifiers

    return key_part, key_part, 0, modifiers


# ==============================================================================
# DAEMON & PROFILE BRIDGE LAYER
# ==============================================================================

def send_http(
    endpoint: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """Sends JSON HTTP request to local bridge daemon."""
    url = f"{BRIDGE_URL}{endpoint}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except Exception as e:
        return {"ok": False, "error": str(e)}


def ensure_daemon_running() -> bool:
    """Verifies that bridge server is running on 9229; boots server.py if offline."""
    res = send_http("/status", timeout=2.0)
    if res.get("status") == "online" or res.get("ok"):
        return True

    print("[BrowserOperator] Bridge daemon not detected on port 9229. Booting server.py...", file=sys.stderr)
    if not SERVER_PY.exists():
        print(f"[!] Error: server.py not found at {SERVER_PY}", file=sys.stderr)
        return False

    subprocess.Popen(
        [sys.executable, str(SERVER_PY)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )
    for _ in range(15):
        time.sleep(0.5)
        res = send_http("/status", timeout=1.0)
        if res.get("status") == "online" or res.get("ok"):
            print("[BrowserOperator] Bridge daemon online.", file=sys.stderr)
            return True

    print("[!] Error: Timed out waiting for bridge daemon to boot.", file=sys.stderr)
    return False


def normalize_profile_name(profile_target: Optional[str]) -> Optional[str]:
    """Normalizes shorthand profile identifiers (e.g. '8' -> 'Profile 8', 'Default' -> 'Default')."""
    if not profile_target:
        return None
    val = profile_target.strip()
    if val.lower() == "default" or "@" in val or val.startswith("Profile "):
        return val
    if val.isdigit():
        return f"Profile {val}"
    return f"Profile {val}"


def resolve_profile_connection(profile_target: Optional[str] = None, launch_url: str = "about:blank") -> Optional[str]:
    """Ensures target profile is connected; boots Chrome window if offline."""
    if not ensure_daemon_running():
        return None

    profile_target = normalize_profile_name(profile_target)
    if not profile_target:
        status = send_http("/status")
        clients = status.get("connected_extensions", status.get("connected_clients", []))
        if clients:
            return clients[0].get("dir_name")
        locks = send_http("/locks")
        profs = locks.get("profiles", {})
        for p_name, p_data in profs.items():
            if p_data.get("status") == "IDLE":
                profile_target = p_name
                break
        if not profile_target:
            profile_target = "Profile 14"

    ping_res = send_http(f"/ping_profile?profile={urllib.parse.quote(profile_target)}", timeout=3.0)
    if ping_res.get("ok") and ping_res.get("connected"):
        return profile_target

    print(f"[BrowserOperator] Profile '{profile_target}' is not active. Booting Chrome window...", file=sys.stderr)
    launch_res = send_http("/launch", method="POST", payload={"profile": profile_target, "url": launch_url}, timeout=5.0)
    if not launch_res.get("ok"):
        print(f"[!] Warning: Launch returned {launch_res}", file=sys.stderr)

    for _ in range(20):
        time.sleep(0.5)
        ping_res = send_http(f"/ping_profile?profile={urllib.parse.quote(profile_target)}", timeout=1.5)
        if ping_res.get("ok") and ping_res.get("connected"):
            print(f"[BrowserOperator] Profile '{profile_target}' connected to bridge.", file=sys.stderr)
            return profile_target

    print(f"[!] Error: Timed out waiting for profile '{profile_target}' extension connection.", file=sys.stderr)
    return None


def get_tabs_list(profile: str) -> List[Dict[str, Any]]:
    """Lists all tabs on the specified connected profile."""
    res = send_http("/command", method="POST", payload={"action": "LIST_TABS", "profile": profile}, timeout=10.0)
    return res.get("tabs", []) if res.get("ok") else []


def get_active_tab_id(profile: str) -> Optional[int]:
    """Retrieves active tab ID for the specified profile."""
    tabs = get_tabs_list(profile)
    if not tabs:
        return None
    for t in tabs:
        if t.get("active"):
            return t.get("id")
    return tabs[0].get("id")


def resolve_tab_id(
    profile: str,
    tab_arg: Optional[int] = None,
    url_match: Optional[str] = None,
    title_match: Optional[str] = None,
) -> Optional[int]:
    """Resolves a tab ID by explicit ID, URL substring, title substring, or active tab."""
    if tab_arg is not None:
        return int(tab_arg)
    tabs = get_tabs_list(profile)
    if url_match:
        q = url_match.lower()
        for t in tabs:
            if q in (t.get("url") or "").lower():
                return t.get("id")
        return None
    if title_match:
        q = title_match.lower()
        for t in tabs:
            if q in (t.get("title") or "").lower():
                return t.get("id")
        return None
    for t in tabs:
        if t.get("active"):
            return t.get("id")
    return tabs[0].get("id") if tabs else None


def execute_browser_command(
    action: str,
    params: Optional[Dict[str, Any]] = None,
    profile: Optional[str] = None,
    timeout: float = 30.0,
    require_tab: bool = True,
) -> Dict[str, Any]:
    """Executes a command via the bridge server ensuring profile and tab are resolved."""
    if not ensure_daemon_running():
        return {"ok": False, "error": "Bridge daemon unavailable"}

    active_profile = resolve_profile_connection(profile)
    if not active_profile:
        return {"ok": False, "error": f"Failed to connect to profile '{profile}'"}

    p = dict(params or {})
    if require_tab and not p.get("tabId"):
        tab_id = get_active_tab_id(active_profile)
        if tab_id:
            p["tabId"] = tab_id

    payload = {
        "action": action,
        "profile": active_profile,
        "params": p,
        "timeout": timeout,
    }
    return send_http("/command", method="POST", payload=payload, timeout=timeout + 5.0)


def eval_tab_js(
    code: str,
    profile: Optional[str] = None,
    tab_id: Optional[int] = None,
    timeout: float = 30.0,
) -> Any:
    """Evaluates JavaScript in tab context via CDP Runtime.evaluate."""
    params: Dict[str, Any] = {"code": code}
    if tab_id:
        params["tabId"] = tab_id
    res = execute_browser_command("EVAL_DOM", params=params, profile=profile, timeout=timeout)
    if res.get("ok"):
        return res.get("result")
    return {"__eval_error__": res.get("error", "EVAL_DOM failed")}


def cdp_send(
    method: str,
    cdp_params: Optional[Dict[str, Any]] = None,
    profile: Optional[str] = None,
    tab_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Dispatches raw Chrome DevTools Protocol command."""
    params: Dict[str, Any] = {"method": method, "params": cdp_params or {}}
    if tab_id:
        params["tabId"] = tab_id
    return execute_browser_command("CDP_COMMAND", params=params, profile=profile)


def make_bridge_caller(profile: str) -> Callable[[str, Dict[str, Any]], Dict[str, Any]]:
    """Builds a bridge caller function compatible with stealth_input helpers."""
    def _call(endpoint: str, body: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(body)
        payload.setdefault("profile", profile)
        return send_http(endpoint, method="POST", payload=payload, timeout=15.0)
    return _call


# ==============================================================================
# INJECTED DOM & TRAVERSAL JAVASCRIPT ENGINES
# ==============================================================================

SHARED_DOM_HELPERS_JS = r"""
  const collectRoots = (rootDoc, frameOffsetX = 0, frameOffsetY = 0, frameDepth = 0, out = []) => {
    out.push({ root: rootDoc, offsetX: frameOffsetX, offsetY: frameOffsetY, frameDepth });
    const walkShadow = (node) => {
      if (!node || !node.querySelectorAll) return;
      const all = node.querySelectorAll('*');
      for (const el of all) {
        if (el.shadowRoot) {
          out.push({ root: el.shadowRoot, offsetX: frameOffsetX, offsetY: frameOffsetY, frameDepth, isShadow: true });
          walkShadow(el.shadowRoot);
        }
      }
    };
    walkShadow(rootDoc);

    if (frameDepth < 3 && rootDoc.querySelectorAll) {
      const iframes = rootDoc.querySelectorAll('iframe');
      for (const iframe of iframes) {
        try {
          const ir = iframe.getBoundingClientRect();
          if (ir.width === 0 || ir.height === 0) continue;
          const doc = iframe.contentDocument || (iframe.contentWindow && iframe.contentWindow.document);
          if (doc && doc.documentElement) {
            collectRoots(doc, frameOffsetX + ir.left, frameOffsetY + ir.top, frameDepth + 1, out);
          }
        } catch (e) {
          // Cross-origin iframe; safely skipped
        }
      }
    }
    return out;
  };

  const getAbsRect = (el, offsetX, offsetY) => {
    const r = el.getBoundingClientRect();
    return {
      left: r.left + offsetX,
      top: r.top + offsetY,
      right: r.right + offsetX,
      bottom: r.bottom + offsetY,
      width: r.width,
      height: r.height,
      cx: Math.round(r.left + offsetX + r.width / 2),
      cy: Math.round(r.top + offsetY + r.height / 2)
    };
  };

  const isElementVisible = (el, offsetX = 0, offsetY = 0) => {
    if (!el || !el.isConnected) return false;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity || '1') === 0) return false;
    const r = getAbsRect(el, offsetX, offsetY);
    return r.width > 0 && r.height > 0;
  };

  const isInViewport = (rect) => {
    return rect.cx >= 0 && rect.cx <= window.innerWidth && rect.cy >= 0 && rect.cy <= window.innerHeight;
  };

  const detectAuthChallenge = () => {
    const text = (document.body && document.body.innerText ? document.body.innerText : '').slice(0, 6000);
    const reasons = [];
    if (document.querySelector('#authCode, input[autocomplete="one-time-code"], input[name*="totp" i], input[name*="otp" i]')) {
      reasons.push('2FA / OTP input detected');
    }
    if (/\b(enter\s+(the\s+)?6-digit\s+code|two-factor\s+authentication|verify\s+your\s+identity|confirm\s+it\s+is\s+still\s+you|authenticator\s+app)\b/i.test(text)) {
      reasons.push('2FA / identity verification prompt detected');
    }
    if (document.querySelector('.cf-turnstile, .g-recaptcha, .h-captcha, iframe[src*="turnstile"], iframe[src*="recaptcha"], iframe[src*="hcaptcha"]')) {
      reasons.push('CAPTCHA / Turnstile widget detected');
    }
    if (/\b(verify\s+you\s+are\s+human|checking\s+your\s+browser|complete\s+the\s+captcha)\b/i.test(text)) {
      reasons.push('Anti-bot human verification gate detected');
    }
    return { triggered: reasons.length > 0, reasons };
  };
"""


def build_extraction_js(root_selector: Optional[str] = None, max_interactive: int = 120) -> str:
    """Builds the structured extraction + Shadow DOM/iframe-aware indexer script."""
    return f"""
(() => {{
{SHARED_DOM_HELPERS_JS}
  const scopeSel = {json.dumps(root_selector or "")};
  const scopeRoot = scopeSel ? (document.querySelector(scopeSel) || document) : document;
  const result = {{
    title: document.title || '',
    url: window.location.href,
    readyState: document.readyState,
    viewport: {{
      width: window.innerWidth,
      height: window.innerHeight,
      scrollX: Math.round(window.scrollX),
      scrollY: Math.round(window.scrollY),
      scrollHeight: document.body ? document.body.scrollHeight : 0
    }},
    hydration: {{
      settled: false,
      activeOverlays: 0,
      hasSpinners: false
    }},
    auth_challenge: detectAuthChallenge(),
    kpi_cards: [],
    tables: [],
    links: [],
    forms: [],
    markdown_content: '',
    interactive_index: []
  }};

  // 1. Hydration status
  const spinners = Array.from(document.querySelectorAll('.spinner, [role="progressbar"], mat-progress-bar, .loading, .mat-progress-spinner, .mat-mdc-progress-bar'));
  const visibleSpinners = spinners.filter(s => s.offsetWidth > 0 && s.offsetHeight > 0);
  result.hydration.hasSpinners = visibleSpinners.length > 0;
  result.hydration.activeOverlays = document.querySelectorAll('.cdk-overlay-backdrop, .modal.show, [role="dialog"]').length;
  result.hydration.settled = !result.hydration.hasSpinners && document.readyState === 'complete';

  // 2. KPI / Metrics extraction
  const kpiCandidates = Array.from(scopeRoot.querySelectorAll('.card, [role="region"], .metric, .kpi-card, .summary-card, [data-metric], div[class*="metric" i]'));
  kpiCandidates.forEach(card => {{
    if (card.offsetWidth === 0) return;
    const text = (card.innerText || '').trim();
    const lines = text.split('\\n').map(l => l.trim()).filter(Boolean);
    if (lines.length >= 2 && lines.length <= 6) {{
      const valIdx = lines.findIndex(l => /^[$€£¥₹]?[-+]?[0-9,]+(\\.[0-9]+)?(%| hrs| TB| GB| MB)?$/i.test(l));
      if (valIdx !== -1) {{
        const label = lines.slice(0, valIdx).join(' ') || lines[0];
        const value = lines[valIdx];
        const delta = lines.slice(valIdx + 1).join(' ') || null;
        result.kpi_cards.push({{ label: label.slice(0, 60), value: value, delta: delta ? delta.slice(0, 60) : null }});
      }}
    }}
  }});
  result.kpi_cards = result.kpi_cards.filter((v, i, a) => a.findIndex(t => t.label === v.label && t.value === v.value) === i).slice(0, 15);

  // 3. Tables Extraction
  const tableEls = Array.from(scopeRoot.querySelectorAll('table, [role="table"], [role="grid"], mat-table, cdk-table'));
  tableEls.forEach((tbl, idx) => {{
    if (tbl.offsetWidth === 0) return;
    const headers = [];
    const rows = [];
    tbl.querySelectorAll('th, [role="columnheader"]').forEach(th => {{
      const hText = (th.innerText || '').trim().replace(/\\s+/g, ' ');
      if (hText) headers.push(hText);
    }});
    tbl.querySelectorAll('tr, [role="row"], mat-row, cdk-row').forEach(tr => {{
      if (tr.querySelector('th, [role="columnheader"]')) return;
      const cells = Array.from(tr.querySelectorAll('td, [role="cell"], [role="gridcell"], mat-cell, cdk-cell'));
      if (cells.length > 0) {{
        const rowData = cells.map(c => (c.innerText || '').trim().replace(/\\s+/g, ' '));
        if (rowData.some(Boolean)) rows.push(rowData);
      }}
    }});
    if (headers.length > 0 || rows.length > 0) {{
      let caption = '';
      const capEl = tbl.querySelector('caption, h2, h3, .table-title');
      if (capEl) caption = (capEl.innerText || '').trim();
      result.tables.push({{
        table_id: 'tbl_' + idx,
        caption: caption || ('Table ' + (idx + 1)),
        headers: headers,
        rows: rows.slice(0, 60)
      }});
    }}
  }});

  // 4. Interactive Elements Indexing (Main DOM + Shadow DOM + Same-Origin Iframes)
  const interactiveSelectors = [
    'button',
    'a[href]',
    'input:not([type="hidden"])',
    'textarea',
    'select',
    'summary',
    '[role="button"]',
    '[role="link"]',
    '[role="combobox"]',
    '[role="tab"]',
    '[role="menuitem"]',
    '[role="checkbox"]',
    '[role="radio"]',
    '[role="switch"]',
    '[role="option"]',
    'mat-select',
    '[contenteditable="true"]',
    '[tabindex]:not([tabindex="-1"])'
  ].join(', ');

  window.__agyElements = {{}};
  const seenEls = new Set();
  const roots = collectRoots(scopeRoot);
  let elId = 1;

  for (const ctx of roots) {{
    if (elId > {max_interactive}) break;
    const found = Array.from(ctx.root.querySelectorAll(interactiveSelectors));
    for (const el of found) {{
      if (elId > {max_interactive}) break;
      if (seenEls.has(el)) continue;
      seenEls.add(el);
      if (!isElementVisible(el, ctx.offsetX, ctx.offsetY)) continue;

      const r = getAbsRect(el, ctx.offsetX, ctx.offsetY);
      if (r.bottom < -200 || r.top > window.innerHeight * 2.5) continue;

      try {{ el.setAttribute('data-agy-id', String(elId)); }} catch(e) {{}}
      window.__agyElements[elId] = {{ el, offsetX: ctx.offsetX, offsetY: ctx.offsetY, frameDepth: ctx.frameDepth, isShadow: Boolean(ctx.isShadow) }};

      const tag = el.tagName.toLowerCase();
      const inputType = (el.getAttribute('type') || '').toLowerCase();
      const role = el.getAttribute('role') || tag;
      const aria = el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.getAttribute('title') || '';
      const rawVal = (tag === 'input' || tag === 'textarea' || tag === 'select') ? (inputType === 'password' ? '***' : (el.value || '')) : '';
      const text = (el.innerText || rawVal || '').trim().replace(/\\s+/g, ' ').slice(0, 60);
      const checked = el.checked !== undefined ? Boolean(el.checked) : (el.getAttribute('aria-checked') === 'true' ? true : (el.getAttribute('aria-checked') === 'false' ? false : null));
      const disabled = Boolean(el.disabled || el.getAttribute('aria-disabled') === 'true');
      const inVp = isInViewport(r);

      let displayStr = '[' + elId + '] <' + tag;
      if (inputType) displayStr += ' type="' + inputType + '"';
      if (role && role !== tag) displayStr += ' role="' + role + '"';
      if (aria) displayStr += ' aria-label="' + aria.slice(0, 40) + '"';
      if (ctx.frameDepth > 0) displayStr += ' iframe:' + ctx.frameDepth;
      if (ctx.isShadow) displayStr += ' shadow';
      if (disabled) displayStr += ' disabled';
      if (checked !== null) displayStr += ' checked=' + checked;
      displayStr += '>' + (text || (tag === 'input' ? aria : '')) + '</' + tag + '> @(' + r.cx + ',' + r.cy + ')' + (inVp ? '' : ' [offscreen]');

      result.interactive_index.push({{
        id: elId,
        tag,
        type: inputType,
        role,
        aria,
        text,
        value: String(rawVal).slice(0, 60),
        checked,
        disabled,
        inViewport: inVp,
        frameDepth: ctx.frameDepth,
        isShadow: Boolean(ctx.isShadow),
        x: r.cx,
        y: r.cy,
        display: displayStr
      }});

      if (tag === 'a' && el.getAttribute('href') && !el.getAttribute('href').startsWith('javascript:')) {{
        result.links.push({{
          id: elId,
          text: text || aria || el.getAttribute('href'),
          href: el.href || el.getAttribute('href')
        }});
      }}
      if (['input', 'textarea', 'select'].includes(tag) || el.getAttribute('contenteditable') === 'true') {{
        let labelText = aria || el.getAttribute('name') || el.id || '';
        if (!labelText && el.id) {{
          const lbl = ctx.root.querySelector('label[for="' + CSS.escape(el.id) + '"]');
          if (lbl) labelText = (lbl.innerText || '').trim();
        }}
        result.forms.push({{
          id: elId,
          tag,
          type: inputType || (el.getAttribute('contenteditable') === 'true' ? 'contenteditable' : tag),
          name: el.getAttribute('name') || '',
          label: labelText.slice(0, 80),
          value: String(rawVal).slice(0, 80),
          checked,
          disabled
        }});
      }}
      elId++;
    }}
  }}
  result.links = result.links.slice(0, 100);
  result.forms = result.forms.slice(0, 60);

  // 5. Clean Readable Markdown Text
  const textNode = scopeSel ? scopeRoot : document.body;
  if (textNode) {{
    const clone = textNode.cloneNode(true);
    const removeSelectors = ['script', 'style', 'svg', 'noscript', 'nav', 'header', 'footer', '.cdk-overlay-container'];
    clone.querySelectorAll(removeSelectors.join(', ')).forEach(n => n.remove());
    const rawText = (clone.innerText || '').split('\\n').map(l => l.trim()).filter(Boolean);
    result.markdown_content = rawText.slice(0, 200).join('\\n');
  }}

  return result;
}})()
"""


def build_resolve_element_js(
    target: Optional[str] = None,
    role: Optional[str] = None,
    name: Optional[str] = None,
    scroll_into_view: bool = True,
    viewport_only: bool = False,
    inputs_only: bool = False,
) -> str:
    """Builds a unified JS element resolver supporting [id], CSS selector, ARIA role/name, and visible text across Shadow DOM & same-origin iframes."""
    target_str = "" if target is None else str(target)
    is_numeric = target_str.isdigit()
    is_css = target_str.startswith(("#", ".", "[")) or (">" in target_str and not role)

    return f"""
(() => {{
{SHARED_DOM_HELPERS_JS}
  const target = {json.dumps(target_str)};
  const isNumeric = {json.dumps(is_numeric)};
  const isCss = {json.dumps(is_css)};
  const roleFilter = {json.dumps((role or "").lower())};
  const nameFilter = {json.dumps((name or "").lower())};
  const viewportOnly = {json.dumps(viewport_only)};
  const inputsOnly = {json.dumps(inputs_only)};
  const roots = collectRoots(document);

  let chosen = null;
  let chosenCtx = null;

  // 1. Numeric [id] resolution (cache first, then attribute scan across roots)
  if (isNumeric && window.__agyElements && window.__agyElements[Number(target)]) {{
    const entry = window.__agyElements[Number(target)];
    if (entry.el && entry.el.isConnected) {{
      chosen = entry.el;
      chosenCtx = entry;
    }}
  }}
  if (!chosen && isNumeric) {{
    for (const ctx of roots) {{
      const el = ctx.root.querySelector('[data-agy-id="' + target + '"]');
      if (el) {{ chosen = el; chosenCtx = ctx; break; }}
    }}
  }}

  // 2. CSS Selector resolution across roots
  if (!chosen && isCss && target) {{
    for (const ctx of roots) {{
      try {{
        const candidates = Array.from(ctx.root.querySelectorAll(target));
        const vis = candidates.find(el => isElementVisible(el, ctx.offsetX, ctx.offsetY));
        if (vis) {{ chosen = vis; chosenCtx = ctx; break; }}
        if (candidates[0]) {{ chosen = candidates[0]; chosenCtx = ctx; break; }}
      }} catch(e) {{}}
    }}
  }}

  // 3. ARIA role + name OR visible text resolution (interactive & viewport-prioritized)
  if (!chosen) {{
    const selectorList = inputsOnly
      ? 'input:not([type="hidden"]), textarea, select, [contenteditable="true"], [role="textbox"], [role="combobox"], [role="searchbox"]'
      : 'button, a, [role="button"], [role="tab"], [role="menuitem"], [role="option"], [role="checkbox"], [role="radio"], [role="switch"], [role="combobox"], input, textarea, select, summary, label, span, div, tr, td';

    const txtMatch = (nameFilter || target).toLowerCase();
    const candidates = [];

    for (const ctx of roots) {{
      const els = Array.from(ctx.root.querySelectorAll(selectorList));
      for (const el of els) {{
        if (!isElementVisible(el, ctx.offsetX, ctx.offsetY)) continue;
        const r = getAbsRect(el, ctx.offsetX, ctx.offsetY);
        if (viewportOnly && !isInViewport(r)) continue;

        const elRole = (el.getAttribute('role') || el.tagName).toLowerCase();
        if (roleFilter && elRole !== roleFilter) continue;

        const labelBlob = [
          el.innerText || '',
          el.value || '',
          el.getAttribute('aria-label') || '',
          el.getAttribute('placeholder') || '',
          el.getAttribute('title') || '',
          el.getAttribute('name') || ''
        ].join(' ').toLowerCase().trim();

        if (txtMatch && !labelBlob.includes(txtMatch)) continue;

        // Score priority: toolbar/interactive tags & viewport visibility & exact text match
        let score = 0;
        const tag = el.tagName.toLowerCase();
        if (['button', 'a', 'input', 'select', 'textarea'].includes(tag) || el.hasAttribute('role')) score += 50;
        if (el.closest('[role="toolbar"], header, nav')) score += 20;
        if (isInViewport(r)) score += 30;
        if ((el.innerText || '').trim().toLowerCase() === txtMatch) score += 40;
        score -= (el.innerText || '').length * 0.05; // prefer tighter element over outer container
        candidates.push({{ el, ctx, score }});
      }}
    }}

    candidates.sort((a, b) => b.score - a.score);
    if (candidates.length > 0) {{
      chosen = candidates[0].el;
      chosenCtx = candidates[0].ctx;
    }}
  }}

  if (!chosen) return {{ found: false }};

  if ({json.dumps(scroll_into_view)}) {{
    try {{ chosen.scrollIntoView({{ block: 'center', inline: 'center', behavior: 'instant' }}); }} catch(e) {{}}
  }}

  // Recompute offsetX/Y in case outer page scrolled
  const rect = getAbsRect(chosen, chosenCtx ? chosenCtx.offsetX : 0, chosenCtx ? chosenCtx.offsetY : 0);
  const inVp = isInViewport(rect);
  const tag = chosen.tagName.toLowerCase();
  const checked = chosen.checked !== undefined ? Boolean(chosen.checked) : (chosen.getAttribute('aria-checked') === 'true' ? true : (chosen.getAttribute('aria-checked') === 'false' ? false : null));
  const disabled = Boolean(chosen.disabled || chosen.getAttribute('aria-disabled') === 'true');

  return {{
    found: true,
    x: rect.cx,
    y: rect.cy,
    width: Math.round(rect.width),
    height: Math.round(rect.height),
    inViewport: inVp,
    tag,
    role: chosen.getAttribute('role') || tag,
    text: (chosen.innerText || chosen.value || chosen.getAttribute('aria-label') || '').trim().slice(0, 80),
    checked,
    disabled,
    isContentEditable: Boolean(chosen.isContentEditable)
  }};
}})()
"""


# ==============================================================================
# CORE GENERALIZED OPERATION PRIMITIVES (Shared by CLI & run-goal)
# ==============================================================================

def dispatch_cdp_key(profile: str, tab_id: int, combo: str) -> None:
    """Dispatches a key or modifier chord via trusted CDP Input.dispatchKeyEvent."""
    key, code, vk, modifiers = parse_key_combo(combo)
    down_params: Dict[str, Any] = {
        "type": "rawKeyDown",
        "key": key,
        "modifiers": modifiers,
    }
    if code:
        down_params["code"] = code
    if vk:
        down_params["windowsVirtualKeyCode"] = vk
        down_params["nativeVirtualKeyCode"] = vk

    up_params = dict(down_params)
    up_params["type"] = "keyUp"

    cdp_send("Input.dispatchKeyEvent", down_params, profile=profile, tab_id=tab_id)
    if modifiers == 0 and len(key) == 1:
        cdp_send("Input.dispatchKeyEvent", {"type": "char", "text": key}, profile=profile, tab_id=tab_id)
    time.sleep(0.03)
    cdp_send("Input.dispatchKeyEvent", up_params, profile=profile, tab_id=tab_id)


def dispatch_cdp_click(
    profile: str,
    tab_id: int,
    x: int,
    y: int,
    button: str = "left",
    click_count: int = 1,
    stealth: bool = False,
) -> Tuple[int, int]:
    """Dispatches trusted CDP mouse click (or stealth Bezier trajectory when enabled)."""
    if stealth and stealth_input is not None and button == "left" and click_count == 1:
        caller = make_bridge_caller(profile)
        return stealth_input.dispatch_stealth_click(caller, tab_id, x, y)

    buttons_mask = {"left": 1, "right": 2, "middle": 4}.get(button, 1)
    cdp_send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y, "button": "none", "buttons": 0}, profile=profile, tab_id=tab_id)
    time.sleep(0.03)
    for click_idx in range(1, click_count + 1):
        cdp_send(
            "Input.dispatchMouseEvent",
            {"type": "mousePressed", "x": x, "y": y, "button": button, "buttons": buttons_mask, "clickCount": click_idx},
            profile=profile,
            tab_id=tab_id,
        )
        time.sleep(0.05)
        cdp_send(
            "Input.dispatchMouseEvent",
            {"type": "mouseReleased", "x": x, "y": y, "button": button, "buttons": 0, "clickCount": click_idx},
            profile=profile,
            tab_id=tab_id,
        )
        if click_idx < click_count:
            time.sleep(0.04)
    return x, y


def perform_click(
    profile: str,
    tab_id: int,
    target: Optional[str] = None,
    role: Optional[str] = None,
    name: Optional[str] = None,
    button: str = "left",
    double: bool = False,
    stealth: bool = False,
    js_fallback: bool = False,
) -> Dict[str, Any]:
    """Resolves element with viewport clamping and dispatches a single trusted CDP click."""
    res = eval_tab_js(build_resolve_element_js(target, role=role, name=name), profile=profile, tab_id=tab_id)
    if not isinstance(res, dict) or not res.get("found"):
        return {"ok": False, "error": f"Element '{target or name}' not found"}

    if not res.get("inViewport"):
        if js_fallback:
            eval_tab_js(
                f"(() => {{ {SHARED_DOM_HELPERS_JS} const el = document.querySelector('[data-agy-id=\"{target}\"]') || document.querySelector({json.dumps(str(target or ''))}); if (el) el.click(); }})()",
                profile=profile,
                tab_id=tab_id,
            )
            return {"ok": True, "text": res.get("text"), "x": res.get("x"), "y": res.get("y"), "method": "js-fallback"}
        return {"ok": False, "error": f"Element '{res.get('text')}' is outside viewport ({res.get('x')}, {res.get('y')})"}

    fx, fy = dispatch_cdp_click(
        profile,
        tab_id,
        int(res["x"]),
        int(res["y"]),
        button=button,
        click_count=2 if double else 1,
        stealth=stealth,
    )
    return {"ok": True, "text": res.get("text"), "x": fx, "y": fy, "button": button, "double": double}


def perform_hover(
    profile: str,
    tab_id: int,
    target: Optional[str] = None,
    role: Optional[str] = None,
    name: Optional[str] = None,
) -> Dict[str, Any]:
    """Moves pointer over element without clicking."""
    res = eval_tab_js(build_resolve_element_js(target, role=role, name=name), profile=profile, tab_id=tab_id)
    if not isinstance(res, dict) or not res.get("found"):
        return {"ok": False, "error": f"Element '{target or name}' not found"}
    if not res.get("inViewport"):
        return {"ok": False, "error": f"Element '{res.get('text')}' outside viewport"}
    cdp_send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": int(res["x"]), "y": int(res["y"]), "button": "none", "buttons": 0}, profile=profile, tab_id=tab_id)
    return {"ok": True, "text": res.get("text"), "x": res.get("x"), "y": res.get("y")}


def perform_type(
    profile: str,
    tab_id: int,
    target: str,
    text: str,
    clear: bool = True,
    enter: bool = False,
    stealth: bool = False,
) -> Dict[str, Any]:
    """React/Angular-safe focus, optional clear via native value setter, and text input."""
    res = eval_tab_js(build_resolve_element_js(target, inputs_only=True), profile=profile, tab_id=tab_id)
    if not isinstance(res, dict) or not res.get("found"):
        res = eval_tab_js(build_resolve_element_js(target, inputs_only=False), profile=profile, tab_id=tab_id)
    if not isinstance(res, dict) or not res.get("found"):
        return {"ok": False, "error": f"Input element '{target}' not found"}

    # Focus element via trusted click if in viewport
    if res.get("inViewport"):
        dispatch_cdp_click(profile, tab_id, int(res["x"]), int(res["y"]), stealth=stealth)

    # React/Angular-safe focus & clear
    target_str = str(target)
    clear_js = f"""
    (() => {{
{SHARED_DOM_HELPERS_JS}
      let el = null;
      if ({json.dumps(target_str.isdigit())} && window.__agyElements && window.__agyElements[{json.dumps(int(target_str) if target_str.isdigit() else 0)}]) {{
        el = window.__agyElements[{json.dumps(int(target_str) if target_str.isdigit() else 0)}].el;
      }}
      if (!el) {{
        for (const ctx of collectRoots(document)) {{
          if ({json.dumps(target_str.isdigit())}) {{
            el = ctx.root.querySelector('[data-agy-id="{target_str}"]');
          }} else {{
            try {{ el = ctx.root.querySelector({json.dumps(target_str)}); }} catch(e) {{}}
          }}
          if (el) break;
        }}
      }}
      if (!el) return {{ ok: false }};
      el.focus();
      if ({json.dumps(clear)}) {{
        if (el.isContentEditable) {{
          el.innerText = '';
          el.dispatchEvent(new InputEvent('input', {{ bubbles: true, inputType: 'deleteContentBackward' }}));
        }} else {{
          const proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
          const desc = Object.getOwnPropertyDescriptor(proto, 'value');
          if (desc && desc.set) desc.set.call(el, '');
          else el.value = '';
          el.dispatchEvent(new Event('input', {{ bubbles: true }}));
          el.dispatchEvent(new Event('change', {{ bubbles: true }}));
        }}
      }}
      return {{ ok: true }};
    }})()
    """
    eval_tab_js(clear_js, profile=profile, tab_id=tab_id)

    if clear:
        # Also Ctrl+A -> Backspace via CDP in case framework ignored synthetic clear
        dispatch_cdp_key(profile, tab_id, "Control+a")
        dispatch_cdp_key(profile, tab_id, "Backspace")

    if stealth and stealth_input is not None:
        stealth_input.dispatch_stealth_type(make_bridge_caller(profile), tab_id, text, fast_mode=(len(text) > 120))
    else:
        cdp_send("Input.insertText", {"text": text}, profile=profile, tab_id=tab_id)

    if enter:
        time.sleep(0.08)
        dispatch_cdp_key(profile, tab_id, "Enter")

    return {"ok": True, "target": target, "length": len(text), "enter": enter}


def perform_select(profile: str, tab_id: int, target: str, value: str) -> Dict[str, Any]:
    """Selects an option in a native <select> OR custom ARIA/Angular combobox."""
    target_str = str(target)
    select_js = f"""
    (() => {{
{SHARED_DOM_HELPERS_JS}
      let el = null;
      if ({json.dumps(target_str.isdigit())} && window.__agyElements && window.__agyElements[{json.dumps(int(target_str) if target_str.isdigit() else 0)}]) {{
        el = window.__agyElements[{json.dumps(int(target_str) if target_str.isdigit() else 0)}].el;
      }}
      if (!el) {{
        for (const ctx of collectRoots(document)) {{
          if ({json.dumps(target_str.isdigit())}) el = ctx.root.querySelector('[data-agy-id="{target_str}"]');
          else {{ try {{ el = ctx.root.querySelector({json.dumps(target_str)}); }} catch(e) {{}} }}
          if (el) break;
        }}
      }}
      if (!el) return {{ found: false }};
      const tag = el.tagName.toLowerCase();
      if (tag !== 'select') return {{ found: true, nativeSelect: false }};
      const want = {json.dumps(value)}.toLowerCase();
      const opts = Array.from(el.options);
      const match = opts.find(o => o.value.toLowerCase() === want || (o.text || '').trim().toLowerCase() === want || (o.text || '').trim().toLowerCase().includes(want));
      if (!match) return {{ found: true, nativeSelect: true, matched: false, available: opts.map(o => o.text.trim()).slice(0, 20) }};
      const desc = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value');
      if (desc && desc.set) desc.set.call(el, match.value);
      else el.value = match.value;
      el.dispatchEvent(new Event('input', {{ bubbles: true }}));
      el.dispatchEvent(new Event('change', {{ bubbles: true }}));
      return {{ found: true, nativeSelect: true, matched: true, value: match.value, label: match.text.trim() }};
    }})()
    """
    res = eval_tab_js(select_js, profile=profile, tab_id=tab_id)
    if not isinstance(res, dict) or not res.get("found"):
        return {"ok": False, "error": f"Select element '{target}' not found"}
    if res.get("nativeSelect"):
        if res.get("matched"):
            return {"ok": True, "value": res.get("value"), "label": res.get("label")}
        return {"ok": False, "error": f"Option '{value}' not found. Available: {res.get('available')}"}

    # Custom ARIA combobox / mat-select: click trigger, wait for [role="option"], click matching text
    clk = perform_click(profile, tab_id, target=target)
    if not clk.get("ok"):
        return clk
    time.sleep(0.35)
    opt_res = perform_click(profile, tab_id, role="option", name=value)
    if not opt_res.get("ok"):
        opt_res = perform_click(profile, tab_id, target=value)
    return opt_res


def perform_check(profile: str, tab_id: int, target: str, desired_state: Optional[bool] = True) -> Dict[str, Any]:
    """Deterministically sets checkbox, radio, or ARIA switch state."""
    res = eval_tab_js(build_resolve_element_js(target), profile=profile, tab_id=tab_id)
    if not isinstance(res, dict) or not res.get("found"):
        return {"ok": False, "error": f"Checkbox/switch '{target}' not found"}
    current = res.get("checked")
    if desired_state is not None and current is not None and bool(current) == bool(desired_state):
        return {"ok": True, "changed": False, "checked": bool(current), "text": res.get("text")}
    clk = perform_click(profile, tab_id, target=target)
    if not clk.get("ok"):
        return clk
    return {"ok": True, "changed": True, "checked": not bool(current) if current is not None else desired_state, "text": res.get("text")}


def perform_wait(
    profile: str,
    tab_id: int,
    selector: Optional[str] = None,
    text: Optional[str] = None,
    url: Optional[str] = None,
    gone: Optional[str] = None,
    idle: bool = False,
    network_idle: bool = False,
    timeout: float = 10.0,
) -> Dict[str, Any]:
    """Waits for selector, text, URL substring, element disappearance, or DOM/network settle."""
    start = time.time()
    if idle or network_idle:
        settle_js = f"""
        (() => new Promise(resolve => {{
          let timer = null;
          let maxTimer = null;
          let obs = null;
          const finish = (status) => {{
            if (obs) obs.disconnect();
            if (timer) clearTimeout(timer);
            if (maxTimer) clearTimeout(maxTimer);
            resolve({{ ok: true, status }});
          }};
          const hasSpinner = () => Array.from(document.querySelectorAll('.spinner, [role="progressbar"], mat-progress-bar, .loading')).some(s => s.offsetWidth > 0 && s.offsetHeight > 0);
          const check = () => {{
            if (document.readyState === 'complete' && !hasSpinner()) {{
              timer = setTimeout(() => finish('settled'), 350);
            }} else {{
              timer = setTimeout(check, 250);
            }}
          }};
          obs = new MutationObserver(() => {{
            if (timer) clearTimeout(timer);
            timer = setTimeout(check, 300);
          }});
          obs.observe(document.documentElement, {{ childList: true, subtree: true, attributes: true }});
          timer = setTimeout(check, 300);
          maxTimer = setTimeout(() => finish('timeout'), {int(timeout * 1000)});
        }}))()
        """
        res = eval_tab_js(settle_js, profile=profile, tab_id=tab_id, timeout=timeout + 5.0)
        elapsed = round(time.time() - start, 2)
        if isinstance(res, dict) and res.get("status") == "settled":
            return {"ok": True, "elapsed": elapsed, "status": "settled"}
        return {"ok": False, "error": f"Timeout ({timeout}s) waiting for DOM settle"}

    while time.time() - start < timeout:
        check_js = f"""
        (() => {{
{SHARED_DOM_HELPERS_JS}
          const sel = {json.dumps(selector or '')};
          const txt = {json.dumps((text or '').lower())};
          const urlSub = {json.dumps((url or '').lower())};
          const goneTarget = {json.dumps(gone or '')};
          const roots = collectRoots(document);

          if (urlSub) {{
            if (window.location.href.toLowerCase().includes(urlSub)) {{
              return {{ matched: true, detail: window.location.href }};
            }}
            return {{ matched: false }};
          }}

          if (goneTarget) {{
            let stillPresent = false;
            for (const ctx of roots) {{
              let el = null;
              if (goneTarget.startsWith('#') || goneTarget.startsWith('.') || goneTarget.startsWith('[')) {{
                try {{ el = ctx.root.querySelector(goneTarget); }} catch(e) {{}}
              }} else {{
                const gLow = goneTarget.toLowerCase();
                const all = Array.from(ctx.root.querySelectorAll('div, span, p, button, [role="progressbar"], [role="dialog"]'));
                el = all.find(c => isElementVisible(c, ctx.offsetX, ctx.offsetY) && (c.innerText || '').toLowerCase().includes(gLow));
              }}
              if (el && isElementVisible(el, ctx.offsetX, ctx.offsetY)) {{ stillPresent = true; break; }}
            }}
            return {{ matched: !stillPresent, detail: stillPresent ? 'still visible' : 'gone' }};
          }}

          for (const ctx of roots) {{
            let el = null;
            if (sel) {{
              try {{ el = ctx.root.querySelector(sel); }} catch(e) {{}}
              if (el && isElementVisible(el, ctx.offsetX, ctx.offsetY)) {{
                if (!txt || (el.innerText || '').toLowerCase().includes(txt)) {{
                  return {{ matched: true, detail: (el.innerText || el.value || sel).trim().slice(0, 80) }};
                }}
              }}
            }} else if (txt) {{
              const all = Array.from(ctx.root.querySelectorAll('button, a, [role="button"], span, div, h1, h2, h3, tr, td, p, li'));
              el = all.find(c => isElementVisible(c, ctx.offsetX, ctx.offsetY) && (c.innerText || '').toLowerCase().includes(txt));
              if (el) return {{ matched: true, detail: (el.innerText || '').trim().slice(0, 80) }};
            }}
          }}
          return {{ matched: false }};
        }})()
        """
        res = eval_tab_js(check_js, profile=profile, tab_id=tab_id)
        if isinstance(res, dict) and res.get("matched"):
            return {"ok": True, "elapsed": round(time.time() - start, 2), "detail": res.get("detail", "")}
        time.sleep(0.25)

    return {"ok": False, "error": f"Timeout ({timeout}s) waiting for condition"}


def perform_scroll(
    profile: str,
    tab_id: int,
    direction: str = "down",
    amount: int = 600,
    container: Optional[str] = None,
    into_view: Optional[str] = None,
) -> Dict[str, Any]:
    """Scrolls window, specific scrollable container, or brings a target element into view."""
    if into_view:
        res = eval_tab_js(build_resolve_element_js(into_view, scroll_into_view=True), profile=profile, tab_id=tab_id)
        if isinstance(res, dict) and res.get("found"):
            return {"ok": True, "into_view": res.get("text"), "x": res.get("x"), "y": res.get("y")}
        return {"ok": False, "error": f"Target '{into_view}' not found to scroll into view"}

    scroll_js = f"""
    (() => {{
      const dir = {json.dumps(direction)};
      const amt = {int(amount)};
      const sel = {json.dumps(container or "")};
      const target = sel ? document.querySelector(sel) : null;
      if (sel && !target) return {{ ok: false, error: 'Container not found: ' + sel }};
      if (target) {{
        if (dir === 'down') target.scrollTop += amt;
        else if (dir === 'up') target.scrollTop -= amt;
        else if (dir === 'top') target.scrollTop = 0;
        else if (dir === 'bottom') target.scrollTop = target.scrollHeight;
        else if (dir === 'right') target.scrollLeft += amt;
        else if (dir === 'left') target.scrollLeft -= amt;
        return {{ ok: true, container: sel, scrollTop: target.scrollTop, scrollLeft: target.scrollLeft }};
      }}
      if (dir === 'down') window.scrollBy({{ top: amt, behavior: 'instant' }});
      else if (dir === 'up') window.scrollBy({{ top: -amt, behavior: 'instant' }});
      else if (dir === 'top') window.scrollTo({{ top: 0, behavior: 'instant' }});
      else if (dir === 'bottom') window.scrollTo({{ top: document.body.scrollHeight, behavior: 'instant' }});
      else if (dir === 'right') window.scrollBy({{ left: amt, behavior: 'instant' }});
      else if (dir === 'left') window.scrollBy({{ left: -amt, behavior: 'instant' }});
      return {{ ok: true, scrollX: window.scrollX, scrollY: window.scrollY }};
    }})()
    """
    res = eval_tab_js(scroll_js, profile=profile, tab_id=tab_id)
    if isinstance(res, dict) and res.get("ok"):
        return res
    return {"ok": False, "error": res.get("error") if isinstance(res, dict) else "Scroll failed"}


def perform_scroll_find(
    profile: str,
    tab_id: int,
    container: str,
    text: Optional[str] = None,
    selector: Optional[str] = None,
    step: int = 600,
    max_steps: int = 25,
    settle_ms: int = 350,
) -> Dict[str, Any]:
    """Incrementally steps scrollTop on a virtualized container until target mounts, then centers it."""
    eval_tab_js(
        f"(() => {{ const c = document.querySelector({json.dumps(container)}); if (c) c.scrollTop = 0; }})()",
        profile=profile,
        tab_id=tab_id,
    )
    time.sleep(settle_ms / 1000.0)

    for i in range(max_steps):
        probe_js = f"""
        (() => {{
          const c = document.querySelector({json.dumps(container)});
          if (!c) return {{ containerMissing: true }};
          const sel = {json.dumps(selector or '')};
          const txt = {json.dumps((text or '').lower())};
          let found = null;
          if (sel) found = c.querySelector(sel);
          if (!found && txt) {{
            const nodes = Array.from(c.querySelectorAll('div, tr, li, a, button, span, [role="row"], [role="listitem"]'));
            found = nodes.find(n => n.offsetWidth > 0 && (n.innerText || '').toLowerCase().includes(txt));
          }}
          if (found) {{
            found.scrollIntoView({{ block: 'center', inline: 'nearest', behavior: 'instant' }});
            const r = found.getBoundingClientRect();
            return {{ found: true, step: {i}, x: Math.round(r.left + r.width/2), y: Math.round(r.top + r.height/2), text: (found.innerText || '').trim().slice(0, 80) }};
          }}
          const atBottom = (c.scrollTop + c.clientHeight) >= (c.scrollHeight - 4);
          if (!atBottom) c.scrollTop += {int(step)};
          return {{ found: false, atBottom, scrollTop: c.scrollTop }};
        }})()
        """
        res = eval_tab_js(probe_js, profile=profile, tab_id=tab_id)
        if not isinstance(res, dict):
            return {"ok": False, "error": "Failed probing virtualized container"}
        if res.get("containerMissing"):
            return {"ok": False, "error": f"Virtualized container '{container}' not found"}
        if res.get("found"):
            return {"ok": True, **res}
        if res.get("atBottom"):
            return {"ok": False, "error": f"Reached bottom of '{container}' without finding '{text or selector}'"}
        time.sleep(settle_ms / 1000.0)

    return {"ok": False, "error": f"Exceeded max_steps ({max_steps}) scanning '{container}'"}


def _cdp_set_file_input_files(
    profile: str,
    tab_id: int,
    abs_files: List[str],
    selector: Optional[str] = None,
) -> Dict[str, Any]:
    """Attaches files directly to <input type='file'> via CDP DOM.setFileInputFiles."""
    cdp_send("DOM.enable", {}, profile=profile, tab_id=tab_id)
    doc_res = cdp_send("DOM.getDocument", {"depth": -1, "pierce": True}, profile=profile, tab_id=tab_id)
    root_node_id = doc_res.get("result", {}).get("root", {}).get("nodeId")
    if not root_node_id:
        return {"ok": False, "error": "Failed to inspect DOM document root via CDP"}

    selectors = [selector] if selector else [
        '.ant-modal input[type="file"]',
        '[role="dialog"] input[type="file"]',
        'input[type="file"]',
    ]
    node_id = 0
    matched_selector = None
    for css_sel in selectors:
        if not css_sel:
            continue
        q_res = cdp_send("DOM.querySelector", {"nodeId": root_node_id, "selector": css_sel}, profile=profile, tab_id=tab_id)
        node_id = q_res.get("result", {}).get("nodeId", 0)
        if node_id:
            matched_selector = css_sel
            break

    if not node_id:
        return {"ok": False, "error": f"No matching <input type='file'> node found (tried: {selectors})"}

    set_res = cdp_send("DOM.setFileInputFiles", {"nodeId": node_id, "files": abs_files}, profile=profile, tab_id=tab_id)
    if set_res.get("ok"):
        return {"ok": True, "tier": "direct-cdp", "selector": matched_selector, "files": abs_files}
    return {"ok": False, "error": set_res.get("error") or "DOM.setFileInputFiles returned failure"}


def perform_upload(
    profile: str,
    tab_id: int,
    files: List[str],
    selector: Optional[str] = None,
    intercept: bool = False,
    direct_cdp: bool = False,
    trigger: Optional[str] = None,
    accelerator: Optional[str] = None,
) -> Dict[str, Any]:
    """3-tier file upload: Direct CDP DOM.setFileInputFiles OR file-chooser intercept + fallback."""
    abs_files = [str(Path(f).resolve()) for f in files]
    missing = [f for f in abs_files if not Path(f).exists()]
    if missing:
        return {"ok": False, "error": f"Files not found: {missing}"}

    if direct_cdp or not intercept:
        direct_res = _cdp_set_file_input_files(profile, tab_id, abs_files, selector=selector)
        if direct_res.get("ok"):
            return direct_res
        if direct_cdp:
            return direct_res

    # Tier 2 / 3: Stub window.showOpenFilePicker & use extension UPLOAD_FILES file-chooser interception
    eval_tab_js("try { window.showOpenFilePicker = undefined; } catch(e) {}", profile=profile, tab_id=tab_id)
    trigger_js = None
    if trigger:
        trigger_js = f"""
        (() => {{
          const sel = {json.dumps(trigger)};
          let el = (sel.startsWith('#') || sel.startsWith('.') || sel.startsWith('[')) ? document.querySelector(sel) : null;
          if (!el) {{
            const low = sel.toLowerCase();
            el = Array.from(document.querySelectorAll('button, a, [role="button"], [role="menuitem"], label')).find(c => c.offsetWidth > 0 && ((c.innerText || '').toLowerCase().includes(low) || (c.getAttribute('aria-label') || '').toLowerCase().includes(low)));
          }}
          if (el) {{ el.click(); return {{ clicked: true }}; }}
          return {{ clicked: false }};
        }})()
        """
    if accelerator:
        import threading
        trigger_js = "({ clicked: true })"

        def _fire_acc():
            time.sleep(0.4)
            try:
                dispatch_cdp_key(profile, tab_id, accelerator)
            except Exception:
                pass

        threading.Thread(target=_fire_acc, daemon=True).start()
    res = execute_browser_command(
        "UPLOAD_FILES",
        {"tabId": tab_id, "files": abs_files, **({"triggerJs": trigger_js} if trigger_js else {})},
        profile=profile,
        timeout=20.0,
    )
    if res.get("ok"):
        return res

    # Fallback: if file-chooser interception timed out (e.g. missing userGesture) but DOM input appeared, attach via CDP
    fallback_res = _cdp_set_file_input_files(profile, tab_id, abs_files, selector=selector)
    if fallback_res.get("ok"):
        fallback_res["tier"] = "direct-cdp-fallback"
        fallback_res["prior_error"] = res.get("error")
        return fallback_res
    return res


def build_xhr_spy_install_js() -> str:
    """Builds the idempotent XMLHttpRequest & fetch live progress spy script."""
    return r"""
(() => {
  if (!window.__boXhrSpy) {
    window.__boXhrSpy = { installed: false, seq: 0, logs: [] };
  }
  window.__xhrLog = window.__boXhrSpy.logs;
  if (window.__boXhrSpy.installed) {
    return { status: 'already_installed', count: window.__boXhrSpy.logs.length };
  }
  window.__boXhrSpy.installed = true;

  const pushRec = (rec) => {
    const logs = window.__boXhrSpy.logs;
    logs.push(rec);
    if (logs.length > 200) logs.splice(0, logs.length - 200);
  };

  const origOpen = XMLHttpRequest.prototype.open;
  const origSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(method, url) {
    this.__boSpyRec = {
      id: ++window.__boXhrSpy.seq,
      kind: 'xhr',
      method: String(method || 'GET').toUpperCase(),
      url: String(url || ''),
      t0: Date.now(),
      elapsed_ms: 0,
      elapsed_s: 0.0,
      loaded: 0,
      total: 0,
      pct: 0.0,
      status: null,
      state: 'open',
      response_preview: '',
      events: []
    };
    return origOpen.apply(this, arguments);
  };

  XMLHttpRequest.prototype.send = function() {
    const rec = this.__boSpyRec;
    if (rec) {
      rec.t0 = Date.now();
      rec.state = 'sending';
      rec.events.push({ ev: 'send', dt: 0 });
      pushRec(rec);
      let lastProg = 0;

      if (this.upload && this.upload.addEventListener) {
        this.upload.addEventListener('progress', (e) => {
          const dt = Date.now() - rec.t0;
          rec.elapsed_ms = dt;
          rec.elapsed_s = Math.round(dt / 100) / 10;
          rec.loaded = e.loaded || 0;
          rec.total = e.total || 0;
          rec.pct = e.total > 0 ? Math.round((e.loaded / e.total) * 1000) / 10 : 0.0;
          if (dt - lastProg >= 400 || (e.total > 0 && e.loaded >= e.total)) {
            lastProg = dt;
            rec.events.push({ ev: 'upload.progress', dt, loaded: rec.loaded, total: rec.total, pct: rec.pct });
            if (rec.events.length > 80) rec.events.splice(1, rec.events.length - 80);
          }
        });
        this.upload.addEventListener('load', () => {
          const dt = Date.now() - rec.t0;
          rec.elapsed_ms = dt;
          rec.elapsed_s = Math.round(dt / 100) / 10;
          rec.state = 'upload_complete';
          rec.events.push({ ev: 'upload.load', dt, loaded: rec.loaded, total: rec.total, pct: 100.0 });
        });
        this.upload.addEventListener('error', () => {
          const dt = Date.now() - rec.t0;
          rec.elapsed_ms = dt;
          rec.state = 'upload_error';
          rec.events.push({ ev: 'upload.error', dt });
        });
        this.upload.addEventListener('abort', () => {
          const dt = Date.now() - rec.t0;
          rec.elapsed_ms = dt;
          rec.state = 'upload_abort';
          rec.events.push({ ev: 'upload.abort', dt });
        });
      }

      this.addEventListener('load', () => {
        const dt = Date.now() - rec.t0;
        rec.elapsed_ms = dt;
        rec.elapsed_s = Math.round(dt / 100) / 10;
        rec.status = this.status;
        rec.state = 'done';
        try {
          rec.response_preview = (this.responseType === '' || this.responseType === 'text')
            ? String(this.responseText || '').slice(0, 500)
            : ('[' + this.responseType + ']');
        } catch (err) {
          rec.response_preview = '[unreadable]';
        }
        rec.events.push({ ev: 'load', dt, status: this.status });
      });
      this.addEventListener('error', () => {
        const dt = Date.now() - rec.t0;
        rec.elapsed_ms = dt;
        rec.elapsed_s = Math.round(dt / 100) / 10;
        rec.status = this.status || -1;
        rec.state = 'error';
        rec.events.push({ ev: 'error', dt, status: rec.status });
      });
      this.addEventListener('abort', () => {
        const dt = Date.now() - rec.t0;
        rec.elapsed_ms = dt;
        rec.status = -2;
        rec.state = 'abort';
        rec.events.push({ ev: 'abort', dt });
      });
      this.addEventListener('timeout', () => {
        const dt = Date.now() - rec.t0;
        rec.elapsed_ms = dt;
        rec.status = -3;
        rec.state = 'timeout';
        rec.events.push({ ev: 'timeout', dt });
      });
    }
    return origSend.apply(this, arguments);
  };

  if (typeof window.fetch === 'function') {
    const origFetch = window.fetch.bind(window);
    window.fetch = function(input, init) {
      const url = typeof input === 'string' ? input : (input && input.url ? input.url : String(input || ''));
      const method = String((init && init.method) || (input && input.method) || 'GET').toUpperCase();
      const rec = {
        id: ++window.__boXhrSpy.seq,
        kind: 'fetch',
        method,
        url,
        t0: Date.now(),
        elapsed_ms: 0,
        elapsed_s: 0.0,
        loaded: 0,
        total: 0,
        pct: null,
        status: null,
        state: 'pending',
        response_preview: '',
        events: [{ ev: 'fetch.start', dt: 0 }]
      };
      pushRec(rec);
      return origFetch(input, init).then(
        (res) => {
          const dt = Date.now() - rec.t0;
          rec.elapsed_ms = dt;
          rec.elapsed_s = Math.round(dt / 100) / 10;
          rec.status = res.status;
          rec.state = 'done';
          rec.events.push({ ev: 'fetch.load', dt, status: res.status });
          try {
            res.clone().text().then((txt) => {
              rec.response_preview = String(txt || '').slice(0, 500);
            }).catch(() => {});
          } catch (e) {}
          return res;
        },
        (err) => {
          const dt = Date.now() - rec.t0;
          rec.elapsed_ms = dt;
          rec.elapsed_s = Math.round(dt / 100) / 10;
          rec.status = -1;
          rec.state = 'error';
          rec.response_preview = String(err || '');
          rec.events.push({ ev: 'fetch.error', dt });
          throw err;
        }
      );
    };
  }
  return { status: 'installed', count: window.__boXhrSpy.logs.length };
})();
"""


def perform_xhr_spy(
    profile: str,
    tab_id: int,
    install: bool = False,
    status: bool = False,
    clear: bool = False,
    url_filter: Optional[str] = None,
    refresh_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Installs, reads, or clears live XHR/fetch upload progress telemetry (plus optional session refresh)."""
    out: Dict[str, Any] = {"ok": True}

    if clear:
        c_res = eval_tab_js(
            "(() => { if (window.__boXhrSpy) { window.__boXhrSpy.logs.length = 0; } if (Array.isArray(window.__xhrLog)) { window.__xhrLog.length = 0; } return { cleared: true }; })()",
            profile=profile,
            tab_id=tab_id,
        )
        out["clear"] = c_res

    if install or (not status and not clear and not refresh_url):
        i_res = eval_tab_js(build_xhr_spy_install_js(), profile=profile, tab_id=tab_id)
        if not isinstance(i_res, dict) or "__eval_error__" in i_res:
            return {"ok": False, "error": f"Failed to install XHR spy: {i_res}"}
        out["spy"] = i_res

    if refresh_url:
        rf_js = f"""
        (async () => {{
          const cookies = document.cookie ? document.cookie.split('; ') : [];
          const csrfPair = cookies.find(c => /csrf|xsrf/i.test(c.split('=')[0] || ''));
          const csrfVal = csrfPair ? decodeURIComponent(csrfPair.split('=').slice(1).join('=') || '') : '';
          const headers = {{ 'Content-Type': 'application/json' }};
          if (csrfVal) headers['X-CSRF-Token'] = csrfVal;
          const res = await fetch({json.dumps(refresh_url)}, {{
            method: 'POST',
            credentials: 'include',
            headers,
            body: '{{}}'
          }});
          const text = await res.text().catch(() => '');
          return {{ ok: res.ok, status: res.status, body: text.slice(0, 500) }};
        }})()
        """
        out["refresh"] = eval_tab_js(rf_js, profile=profile, tab_id=tab_id, timeout=15.0)

    if status:
        s_js = f"""
        (() => {{
          const installed = !!(window.__boXhrSpy && window.__boXhrSpy.installed);
          const raw = (window.__boXhrSpy && Array.isArray(window.__boXhrSpy.logs))
            ? window.__boXhrSpy.logs
            : (Array.isArray(window.__xhrLog) ? window.__xhrLog : []);
          const needle = {json.dumps((url_filter or '').lower())};
          const filtered = needle ? raw.filter(r => String(r.url || '').toLowerCase().includes(needle)) : raw;
          const summary = filtered.map(r => {{
            const evs = Array.isArray(r.events) ? r.events : [];
            const lastEv = evs.length ? evs[evs.length - 1] : null;
            const liveElapsed = (r.state === 'sending' || r.state === 'pending' || r.state === 'upload_complete') && r.t0
              ? Math.round((Date.now() - r.t0) / 100) / 10
              : r.elapsed_s;
            return {{
              id: r.id,
              kind: r.kind,
              method: r.method,
              url: r.url,
              state: r.state,
              status: r.status,
              loaded: r.loaded,
              total: r.total,
              pct: r.pct,
              elapsed_s: liveElapsed,
              last_event: lastEv,
              response_preview: r.response_preview || ''
            }};
          }});
          return {{ installed, total_captured: raw.length, matched: summary.length, requests: summary }};
        }})()
        """
        s_res = eval_tab_js(s_js, profile=profile, tab_id=tab_id)
        if not isinstance(s_res, dict) or "__eval_error__" in s_res:
            return {"ok": False, "error": f"Failed reading XHR spy status: {s_res}"}
        out.update(s_res)

    return out


def generate_totp_code(secret: str) -> Tuple[str, int]:
    """Computes current 6-digit RFC 6238 TOTP code and remaining seconds in the 30s window."""
    cleaned = secret.strip().replace(" ", "").upper()
    pad = (-len(cleaned)) % 8
    key = base64.b32decode(cleaned + ("=" * pad))
    now = time.time()
    step = int(now // 30)
    msg = struct.pack(">Q", step)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[19] & 0x0F
    code_int = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    remaining = 30 - int(now % 30)
    return f"{code_int:06d}", remaining


def perform_type_otp(
    profile: str,
    tab_id: int,
    code: Optional[str] = None,
    totp_secret: Optional[str] = None,
    selector: Optional[str] = None,
    submit_text: Optional[str] = None,
    auto_verify: bool = True,
    delay_ms: int = 60,
    min_ttl: int = 4,
) -> Dict[str, Any]:
    """Types an OTP code char-by-char via CDP Input.dispatchKeyEvent with busy guard for multi-box React/AntD OTP inputs."""
    rem: Optional[int] = None
    if totp_secret:
        code, rem = generate_totp_code(totp_secret)
        if rem < min_ttl:
            time.sleep(rem + 1)
            code, rem = generate_totp_code(totp_secret)
    if not code:
        return {"ok": False, "error": "Provide an OTP code or --totp-secret"}
    code = str(code).strip()

    prep_js = f"""
    (() => {{
{SHARED_DOM_HELPERS_JS}
      const userSel = {json.dumps(selector)};
      const customSubmit = {json.dumps(submit_text)};
      const roots = collectRoots(document);

      const findVisibleContainer = () => {{
        const modals = [];
        for (const ctx of roots) {{
          for (const m of ctx.root.querySelectorAll('.ant-modal, [role="dialog"], .modal, [aria-modal="true"]')) {{
            const wrap = m.closest('.ant-modal-wrap');
            const st = window.getComputedStyle(m);
            const wst = wrap ? window.getComputedStyle(wrap) : null;
            if (m.offsetWidth > 0 && st.display !== 'none' && (!wst || wst.display !== 'none')) {{
              modals.push(m);
            }}
          }}
        }}
        if (modals.length) {{
          const otpModal = modals.find(m => /confirm it is still you|authenticator|one-time|otp|verification code|two-factor|verify your identity/i.test(m.innerText || ''));
          return otpModal || modals[modals.length - 1];
        }}
        return null;
      }};

      const scope = findVisibleContainer() || document;
      let inputs = [];

      if (userSel) {{
        for (const ctx of roots) {{
          const matched = Array.from(ctx.root.querySelectorAll(userSel)).filter(el => isElementVisible(el, ctx.offsetX, ctx.offsetY));
          for (const m of matched) {{
            if (m.tagName === 'INPUT') inputs.push(m);
            else {{
              const inner = Array.from(m.querySelectorAll('input')).filter(i => i.offsetWidth > 0);
              inputs.push(...inner);
            }}
          }}
          if (inputs.length) break;
        }}
      }} else {{
        const otpGroup = Array.from(scope.querySelectorAll('.ant-otp input, input[autocomplete="one-time-code"], #authCode, #code, input[name*="otp" i], input[name*="totp" i], input[placeholder*="code" i]'))
          .filter(i => i.offsetWidth > 0);
        if (otpGroup.length) {{
          inputs = otpGroup;
        }} else {{
          const candidates = Array.from(scope.querySelectorAll('input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]):not([type="file"])'))
            .filter(i => i.offsetWidth > 0);
          const singleChars = candidates.filter(i => i.maxLength === 1 || (i.className || '').includes('otp'));
          inputs = singleChars.length >= 4 ? singleChars : candidates;
        }}
      }}

      if (!inputs.length) {{
        return {{ ok: false, error: 'No visible OTP input fields found' }};
      }}

      const verifyLabels = customSubmit
        ? [customSubmit.toLowerCase()]
        : ['verify and submit', 'verify', 'confirm', 'submit', 'continue'];
      const buttons = Array.from(scope.querySelectorAll('button')).filter(b => b.offsetWidth > 0);
      const verifyBtn = buttons.find(b => verifyLabels.some(lbl => (b.innerText || '').trim().toLowerCase() === lbl))
        || buttons.find(b => verifyLabels.some(lbl => (b.innerText || '').trim().toLowerCase().includes(lbl)));

      const busy = inputs.some(i => i.disabled) || !!(verifyBtn && (verifyBtn.classList.contains('ant-btn-loading') || verifyBtn.getAttribute('aria-busy') === 'true'));
      if (busy) {{
        return {{ ok: true, busy: true, inputCount: inputs.length }};
      }}

      const proto = window.HTMLInputElement.prototype;
      const desc = Object.getOwnPropertyDescriptor(proto, 'value');
      for (const inp of inputs) {{
        if (inp.value) {{
          if (desc && desc.set) desc.set.call(inp, '');
          else inp.value = '';
          inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
        }}
      }}
      inputs[0].focus();
      return {{ ok: true, busy: false, inputCount: inputs.length }};
    }})()
    """

    prep = eval_tab_js(prep_js, profile=profile, tab_id=tab_id)
    if not isinstance(prep, dict) or not prep.get("ok"):
        return {"ok": False, "error": (prep.get("error") if isinstance(prep, dict) else None) or f"OTP preparation failed: {prep}"}
    if prep.get("busy"):
        return {"ok": True, "status": "busy_in_flight", "inputCount": prep.get("inputCount", 0), "totp_remaining_s": rem}

    for ch in code:
        cdp_send("Input.dispatchKeyEvent", {"type": "char", "text": ch}, profile=profile, tab_id=tab_id)
        time.sleep(max(0.01, delay_ms / 1000.0))

    time.sleep(0.3)
    if not auto_verify:
        return {"ok": True, "status": "typed", "code_length": len(code), "inputCount": prep.get("inputCount", 0), "totp_remaining_s": rem}

    verify_js = f"""
    (() => {{
{SHARED_DOM_HELPERS_JS}
      const customSubmit = {json.dumps(submit_text)};
      const roots = collectRoots(document);
      let scope = document;
      for (const ctx of roots) {{
        for (const m of ctx.root.querySelectorAll('.ant-modal, [role="dialog"], [aria-modal="true"]')) {{
          const wrap = m.closest('.ant-modal-wrap');
          const st = window.getComputedStyle(m);
          const wst = wrap ? window.getComputedStyle(wrap) : null;
          if (m.offsetWidth > 0 && st.display !== 'none' && (!wst || wst.display !== 'none')) {{
            scope = m;
          }}
        }}
      }}
      const verifyLabels = customSubmit
        ? [customSubmit.toLowerCase()]
        : ['verify and submit', 'verify', 'confirm', 'submit', 'continue'];
      const buttons = Array.from(scope.querySelectorAll('button')).filter(b => b.offsetWidth > 0);
      const btn = buttons.find(b => verifyLabels.some(lbl => (b.innerText || '').trim().toLowerCase() === lbl))
        || buttons.find(b => verifyLabels.some(lbl => (b.innerText || '').trim().toLowerCase().includes(lbl)));
      if (!btn) return {{ closed: scope === document, found: false, busy: false }};
      const busy = btn.classList.contains('ant-btn-loading') || btn.getAttribute('aria-busy') === 'true';
      const r = btn.getBoundingClientRect();
      const inVp = r.width > 0 && r.height > 0 && r.left + r.width / 2 >= 0 && r.left + r.width / 2 <= window.innerWidth && r.top + r.height / 2 >= 0 && r.top + r.height / 2 <= window.innerHeight;
      if (!busy && !btn.disabled && !inVp) btn.click();
      return {{
        found: true,
        busy,
        disabled: !!btn.disabled,
        inViewport: inVp,
        x: Math.round(r.left + r.width / 2),
        y: Math.round(r.top + r.height / 2),
        label: (btn.innerText || '').trim()
      }};
    }})()
    """
    ver = eval_tab_js(verify_js, profile=profile, tab_id=tab_id)
    clicked_verify = False
    if isinstance(ver, dict) and ver.get("found") and not ver.get("busy") and not ver.get("disabled"):
        if ver.get("inViewport"):
            dispatch_cdp_click(profile, tab_id, int(ver["x"]), int(ver["y"]))
        clicked_verify = True

    return {
        "ok": True,
        "status": "auto_submitted" if (isinstance(ver, dict) and ver.get("busy")) else ("submitted" if clicked_verify else "typed"),
        "code_length": len(code),
        "inputCount": prep.get("inputCount", 0),
        "clicked_verify": clicked_verify,
        "verify": ver,
        "totp_remaining_s": rem,
    }


def optimize_pdf_file(
    input_pdf: str,
    output_pdf: Optional[str] = None,
    max_height: int = 960,
    quality: int = 28,
    black_point: int = 65,
    white_point: int = 195,
) -> Dict[str, Any]:
    """Compresses embedded PDF scan images in-place while preserving embedded OCR text layers."""
    try:
        import pymupdf  # type: ignore
    except ImportError:
        try:
            import fitz as pymupdf  # type: ignore
        except ImportError:
            return {"ok": False, "error": "PyMuPDF (pymupdf) is not installed"}

    try:
        from PIL import Image  # type: ignore
    except ImportError:
        return {"ok": False, "error": "Pillow (PIL) is not installed"}

    src = Path(input_pdf).resolve()
    if not src.exists():
        return {"ok": False, "error": f"Input PDF not found: {src}"}
    dst = Path(output_pdf).resolve() if output_pdf else src.with_name(f"{src.stem}_compact{src.suffix}")
    dst.parent.mkdir(parents=True, exist_ok=True)

    span = max(1, white_point - black_point)
    scale = 255.0 / span
    lut = [max(0, min(255, int(round((px - black_point) * scale)))) for px in range(256)]

    doc = pymupdf.open(str(src))
    seen_xrefs = set()
    replaced = 0
    for page in doc:
        for img_info in page.get_images(full=True):
            xref = int(img_info[0])
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)
            base = doc.extract_image(xref)
            if not base or not base.get("image"):
                continue
            im = Image.open(io.BytesIO(base["image"])).convert("L")
            w, h = im.size
            if max_height > 0 and h > max_height:
                im = im.resize((max(1, int(w * max_height / h)), max_height), Image.Resampling.LANCZOS)
            im_clean = im.point(lut)
            buf = io.BytesIO()
            im_clean.save(buf, format="JPEG", quality=quality, optimize=True)
            page.replace_image(xref, stream=buf.getvalue())
            replaced += 1

    orig_bytes = src.stat().st_size
    doc.save(str(dst), garbage=4, deflate=True)
    doc.close()

    chk = pymupdf.open(str(dst))
    pages = len(chk)
    text_chars = sum(len(p.get_text().strip()) for p in chk)
    chk.close()
    out_bytes = dst.stat().st_size
    ratio = round(orig_bytes / out_bytes, 2) if out_bytes else 0.0

    return {
        "ok": True,
        "input": str(src),
        "output": str(dst),
        "pages": pages,
        "images_replaced": replaced,
        "original_bytes": orig_bytes,
        "output_bytes": out_bytes,
        "compression_ratio": ratio,
        "preserved_text_chars": text_chars,
    }


def check_auth_circuit_breaker(profile: str, tab_id: int) -> Dict[str, Any]:
    """Checks current page for 2FA, identity verification, or CAPTCHA challenges."""
    res = eval_tab_js(f"(() => {{ {SHARED_DOM_HELPERS_JS} return detectAuthChallenge(); }})()", profile=profile, tab_id=tab_id)
    if isinstance(res, dict):
        return res
    return {"triggered": False, "reasons": []}


# ==============================================================================
# SUBCOMMANDS
# ==============================================================================

def cmd_status(args: argparse.Namespace) -> int:
    """Shows bridge daemon status, connected profiles, and active leases."""
    if not ensure_daemon_running():
        print("[!] Bridge daemon offline.", file=sys.stderr)
        return 1
    status = send_http("/status")
    locks = send_http("/locks")
    payload = {
        "bridge_status": status.get("status"),
        "port": status.get("port"),
        "connected_extensions": status.get("connected_extensions", []),
        "ai_premium_count": status.get("ai_premium_count"),
        "locks": locks.get("profiles", {}),
    }
    print(json.dumps(payload, indent=2))
    return 0


def cmd_tabs(args: argparse.Namespace) -> int:
    """Lists open tabs for the target profile or all connected profiles."""
    if not ensure_daemon_running():
        return 1
    if getattr(args, "all", False):
        status = send_http("/status")
        out = {}
        for ext in status.get("connected_extensions", []):
            p_name = ext.get("dir_name")
            if p_name and p_name != "unknown":
                out[p_name] = get_tabs_list(p_name)
        print(json.dumps(out, indent=2))
        return 0

    profile = resolve_profile_connection(args.profile)
    if not profile:
        return 1
    tabs = get_tabs_list(profile)
    if getattr(args, "json", False):
        print(json.dumps(tabs, indent=2))
    else:
        print(f"=== TABS ON {profile} ({len(tabs)}) ===")
        for t in tabs:
            mark = "*" if t.get("active") else " "
            print(f" [{mark}] id={t.get('id')} | {t.get('title', '')[:50]} | {t.get('url', '')}")
    return 0


def cmd_new_tab(args: argparse.Namespace) -> int:
    """Opens a new tab with low-RAM single-tab guardrail awareness."""
    profile = resolve_profile_connection(args.profile)
    if not profile:
        return 1
    existing = get_tabs_list(profile)
    if getattr(args, "reuse", False) and existing:
        active_id = get_active_tab_id(profile)
        res = execute_browser_command("NAVIGATE_TAB", {"tabId": active_id, "url": args.url}, profile=profile)
        print(json.dumps(res, indent=2))
        return 0 if res.get("ok") else 1

    if len(existing) >= 1 and not getattr(args, "force", False):
        print(f"[BrowserOperator] Note: {profile} already has {len(existing)} open tab(s) (low-RAM single-tab advisory; pass --reuse to navigate existing tab).", file=sys.stderr)

    res = execute_browser_command(
        "OPEN_TAB",
        {"url": args.url, "active": not getattr(args, "background", False)},
        profile=profile,
        require_tab=False,
    )
    if res.get("ok"):
        print(f"Opened tab {res.get('tabId')} -> {args.url}")
        return 0
    print(f"[!] Failed to open tab: {res.get('error')}", file=sys.stderr)
    return 1


def cmd_switch_tab(args: argparse.Namespace) -> int:
    """Focuses an existing tab by ID, URL substring, or title substring."""
    profile = resolve_profile_connection(args.profile)
    if not profile:
        return 1
    params: Dict[str, Any] = {}
    if args.tab:
        params["tabId"] = args.tab
    elif args.url:
        params["urlContains"] = args.url
    elif args.title:
        params["titleContains"] = args.title
    else:
        print("[!] Specify --tab, --url, or --title", file=sys.stderr)
        return 1
    res = execute_browser_command("SWITCH_TAB", params, profile=profile, require_tab=False)
    if res.get("ok"):
        print(f"Switched to tab {res.get('tabId')} | {res.get('title')} | {res.get('url')}")
        return 0
    print(f"[!] Switch tab failed: {res.get('error')}", file=sys.stderr)
    return 1


def cmd_close_tab(args: argparse.Namespace) -> int:
    """Closes a tab by ID, URL substring, or title substring (or current active tab)."""
    profile = resolve_profile_connection(args.profile)
    if not profile:
        return 1
    tab_id = resolve_tab_id(profile, tab_arg=args.tab, url_match=args.url, title_match=args.title)
    if not tab_id:
        print("[!] No matching tab found to close.", file=sys.stderr)
        return 1
    res = execute_browser_command("CLOSE_TAB", {"tabId": tab_id}, profile=profile, require_tab=False)
    if res.get("ok"):
        print(f"Closed tab {tab_id}")
        return 0
    print(f"[!] Close tab failed: {res.get('error')}", file=sys.stderr)
    return 1


def cmd_history_nav(args: argparse.Namespace) -> int:
    """Handles back, forward, and reload tab navigation."""
    profile = resolve_profile_connection(args.profile)
    if not profile:
        return 1
    tab_id = resolve_tab_id(profile, tab_arg=args.tab)
    if not tab_id:
        print("[!] No active tab found.", file=sys.stderr)
        return 1

    action_map = {"back": "GO_BACK", "forward": "GO_FORWARD", "reload": "RELOAD_TAB"}
    params: Dict[str, Any] = {"tabId": tab_id}
    if args.subcommand == "reload" and getattr(args, "bypass_cache", False):
        params["bypassCache"] = True
    res = execute_browser_command(action_map[args.subcommand], params, profile=profile)
    if res.get("ok"):
        print(f"Executed {args.subcommand} on tab {tab_id}")
        return 0
    print(f"[!] {args.subcommand} failed: {res.get('error')}", file=sys.stderr)
    return 1


def cmd_goto(args: argparse.Namespace) -> int:
    """Navigates target profile to URL via NAVIGATE_TAB and waits for readiness."""
    profile = resolve_profile_connection(args.profile, launch_url=args.url)
    if not profile:
        return 1

    if getattr(args, "new_tab", False):
        open_res = execute_browser_command("OPEN_TAB", {"url": args.url, "active": True}, profile=profile, require_tab=False)
        if not open_res.get("ok"):
            print(f"[!] Failed opening new tab: {open_res.get('error')}", file=sys.stderr)
            return 1
        tab_id = open_res.get("tabId")
    else:
        tab_id = resolve_tab_id(profile, tab_arg=args.tab)
        if not tab_id:
            print("[!] No active tab found to navigate.", file=sys.stderr)
            return 1
        print(f"[BrowserOperator] Navigating Tab {tab_id} on '{profile}' -> {args.url}...")
        nav_res = execute_browser_command("NAVIGATE_TAB", {"tabId": tab_id, "url": args.url}, profile=profile, timeout=max(args.timeout, 15.0))
        if not nav_res.get("ok"):
            # Fallback to JS redirect if NAVIGATE_TAB failed
            eval_tab_js(f"window.location.href = {json.dumps(args.url)}", profile=profile, tab_id=tab_id)

    wait_mode = getattr(args, "wait_until", "interactive")
    if wait_mode == "settle":
        perform_wait(profile, tab_id, idle=True, timeout=args.timeout)
    else:
        target_states = ("complete",) if wait_mode == "load" else ("interactive", "complete")
        start = time.time()
        while time.time() - start < args.timeout:
            st = eval_tab_js("({ url: window.location.href, readyState: document.readyState, title: document.title })", profile=profile, tab_id=tab_id)
            if isinstance(st, dict) and st.get("readyState") in target_states:
                print(f"Navigated to: {st.get('url')} | Title: '{st.get('title')}'")
                return 0
            time.sleep(0.35)

    st = eval_tab_js("({ url: window.location.href, title: document.title })", profile=profile, tab_id=tab_id)
    if isinstance(st, dict):
        print(f"Navigated to: {st.get('url')} | Title: '{st.get('title')}'")
    else:
        print(f"Dispatched navigation to {args.url}")
    return 0


def cmd_meta(args: argparse.Namespace) -> int:
    """Outputs quick page metadata, hydration state, and 2FA/CAPTCHA circuit-breaker check."""
    profile = resolve_profile_connection(args.profile)
    if not profile:
        return 1
    tab_id = resolve_tab_id(profile, tab_arg=args.tab)
    js = f"""
    (() => {{
{SHARED_DOM_HELPERS_JS}
      const spinners = Array.from(document.querySelectorAll('.spinner, [role="progressbar"], mat-progress-bar, .loading'));
      return {{
        tabId: {json.dumps(tab_id)},
        title: document.title || '',
        url: window.location.href,
        readyState: document.readyState,
        viewport: {{ width: window.innerWidth, height: window.innerHeight, scrollX: Math.round(window.scrollX), scrollY: Math.round(window.scrollY), scrollHeight: document.body ? document.body.scrollHeight : 0 }},
        hasSpinners: spinners.some(s => s.offsetWidth > 0 && s.offsetHeight > 0),
        activeOverlays: document.querySelectorAll('.cdk-overlay-backdrop, .modal.show, [role="dialog"]').length,
        auth_challenge: detectAuthChallenge()
      }};
    }})()
    """
    data = eval_tab_js(js, profile=profile, tab_id=tab_id, timeout=args.timeout)
    print(json.dumps(data, indent=2))
    return 0


def cmd_read(args: argparse.Namespace) -> int:
    """Extracts high-density structured content from the page."""
    profile = resolve_profile_connection(args.profile)
    if not profile:
        return 1
    tab_id = resolve_tab_id(profile, tab_arg=args.tab)

    data = eval_tab_js(build_extraction_js(root_selector=getattr(args, "selector", None)), profile=profile, tab_id=tab_id, timeout=args.timeout)
    if not isinstance(data, dict) or "__eval_error__" in data:
        print(f"[!] Extraction error: {data}", file=sys.stderr)
        return 1

    fmt = args.format.lower()
    output_str = ""

    if fmt in ("md", "markdown"):
        output_str = f"# {data.get('title')}\nURL: {data.get('url')}\n\n"
        if data.get("kpi_cards"):
            output_str += "### Key Metrics / KPIs\n"
            for k in data["kpi_cards"]:
                output_str += f"- **{k.get('label')}**: `{k.get('value')}`" + (f" ({k.get('delta')})" if k.get("delta") else "") + "\n"
            output_str += "\n"
        output_str += "### Content Summary\n" + data.get("markdown_content", "")
    elif fmt == "tables":
        tables = data.get("tables", [])
        if not tables:
            output_str = "No structured tables found on active page."
        else:
            for tbl in tables:
                output_str += f"\n### {tbl.get('caption', 'Table')}\n"
                headers = tbl.get("headers", [])
                rows = tbl.get("rows", [])
                if headers:
                    output_str += "| " + " | ".join(headers) + " |\n"
                    output_str += "| " + " | ".join(["---"] * len(headers)) + " |\n"
                for row in rows:
                    output_str += "| " + " | ".join(str(c) for c in row) + " |\n"
    elif fmt == "kpis":
        output_str = json.dumps(data.get("kpi_cards", []), indent=2)
    elif fmt == "links":
        output_str = json.dumps(data.get("links", []), indent=2)
    elif fmt == "forms":
        output_str = json.dumps(data.get("forms", []), indent=2)
    elif fmt == "meta":
        output_str = json.dumps({
            "title": data.get("title"),
            "url": data.get("url"),
            "readyState": data.get("readyState"),
            "viewport": data.get("viewport"),
            "hydration": data.get("hydration"),
            "auth_challenge": data.get("auth_challenge"),
        }, indent=2)
    else:  # all / json
        output_str = json.dumps(data, indent=2)

    if args.output:
        out_p = Path(args.output)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(output_str, encoding="utf-8")
        print(f"Extracted page data saved -> {args.output}")
    else:
        print(output_str)
    return 0


def _capture_screenshot_file(
    profile: str,
    tab_id: int,
    output_path: str,
    badges: bool = False,
    full_page: bool = False,
    fmt: str = "png",
    quality: int = 85,
) -> bool:
    """Captures screenshot with optional [id] visual badge overlay."""
    if badges:
        badge_js = """
        (() => {
          document.getElementById('__agy_badge_overlay')?.remove();
          const ov = document.createElement('div');
          ov.id = '__agy_badge_overlay';
          ov.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:2147483647;';
          document.body.appendChild(ov);
          const map = window.__agyElements || {};
          for (const [id, entry] of Object.entries(map)) {
            const el = entry.el;
            if (!el || !el.isConnected) continue;
            const r = el.getBoundingClientRect();
            const x = r.left + (entry.offsetX || 0);
            const y = r.top + (entry.offsetY || 0);
            if (r.width <= 0 || r.height <= 0 || x < 0 || y < 0 || x > window.innerWidth || y > window.innerHeight) continue;
            const b = document.createElement('div');
            b.innerText = id;
            b.style.cssText = `position:absolute;left:${Math.round(x)}px;top:${Math.round(y)}px;background:#facc15;color:#000;font:bold 10px/1 monospace;padding:1px 3px;border:1px solid #000;border-radius:3px;`;
            ov.appendChild(b);
          }
        })()
        """
        eval_tab_js(badge_js, profile=profile, tab_id=tab_id)

    try:
        res = execute_browser_command(
            "TAKE_SCREENSHOT",
            params={"tabId": tab_id, "format": fmt, "quality": quality, "fullPage": full_page},
            profile=profile,
        )
        data = res.get("data") if res.get("ok") else None
        if not data:
            cdp_params: Dict[str, Any] = {"format": fmt}
            if fmt != "png":
                cdp_params["quality"] = quality
            if full_page:
                cdp_params["captureBeyondViewport"] = True
            cdp_res = cdp_send("Page.captureScreenshot", cdp_params, profile=profile, tab_id=tab_id)
            data = cdp_res.get("result", {}).get("data")
        if not data:
            return False
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_bytes(base64.b64decode(data))
        return True
    finally:
        if badges:
            eval_tab_js("document.getElementById('__agy_badge_overlay')?.remove()", profile=profile, tab_id=tab_id)


def cmd_observe(args: argparse.Namespace) -> int:
    """Outputs numbered interactive element action space [id] across DOM, Shadow DOM, and iframes."""
    profile = resolve_profile_connection(args.profile)
    if not profile:
        return 1
    tab_id = resolve_tab_id(profile, tab_arg=args.tab)

    data = eval_tab_js(build_extraction_js(), profile=profile, tab_id=tab_id, timeout=args.timeout)
    if not isinstance(data, dict) or "__eval_error__" in data:
        print(f"[!] Observe failed: {data}", file=sys.stderr)
        return 1

    items = data.get("interactive_index", [])
    if getattr(args, "viewport_only", False):
        items = [it for it in items if it.get("inViewport")]
    if getattr(args, "filter", None):
        flt = args.filter.lower()
        items = [it for it in items if flt in (it.get("display") or "").lower()]

    if getattr(args, "screenshot", None):
        _capture_screenshot_file(profile, tab_id, args.screenshot, badges=getattr(args, "badges", False))

    if getattr(args, "json", False):
        print(json.dumps({"title": data.get("title"), "url": data.get("url"), "elements": items}, indent=2))
        return 0

    print(f"\n=== INTERACTIVE ACTION SPACE ({len(items)} elements) [Page: {data.get('title')}] ===")
    for item in items:
        print(item.get("display") or f"[{item.get('id')}] <{item.get('tag')}> {item.get('text')}")
    return 0


def cmd_click(args: argparse.Namespace) -> int:
    """Dispatches single trusted CDP click to element by ID, CSS selector, ARIA role/name, or visible text."""
    if not args.target and not getattr(args, "name", None) and not getattr(args, "role", None):
        print("[!] Provide target element ID/selector/text or --role/--name.", file=sys.stderr)
        return 1
    profile = resolve_profile_connection(args.profile)
    if not profile:
        return 1
    tab_id = resolve_tab_id(profile, tab_arg=args.tab)
    res = perform_click(
        profile,
        tab_id,
        target=args.target,
        role=getattr(args, "role", None),
        name=getattr(args, "name", None),
        button=getattr(args, "button", "left"),
        double=getattr(args, "double", False),
        stealth=getattr(args, "stealth", False),
        js_fallback=getattr(args, "js_fallback", False),
    )
    if res.get("ok"):
        print(f"Clicked '{res.get('text')}' at ({res.get('x')}, {res.get('y')}) [Trusted CDP]")
        return 0
    print(f"[!] {res.get('error')}", file=sys.stderr)
    return 1


def cmd_hover(args: argparse.Namespace) -> int:
    """Moves pointer over target element via CDP mouseMoved."""
    if not args.target and not getattr(args, "name", None) and not getattr(args, "role", None):
        print("[!] Provide target element ID/selector/text or --role/--name.", file=sys.stderr)
        return 1
    profile = resolve_profile_connection(args.profile)
    if not profile:
        return 1
    tab_id = resolve_tab_id(profile, tab_arg=args.tab)
    res = perform_hover(profile, tab_id, target=args.target, role=getattr(args, "role", None), name=getattr(args, "name", None))
    if res.get("ok"):
        print(f"Hovered '{res.get('text')}' at ({res.get('x')}, {res.get('y')})")
        return 0
    print(f"[!] {res.get('error')}", file=sys.stderr)
    return 1


def cmd_type(args: argparse.Namespace) -> int:
    """Types text into element with React/Angular-safe setter, optional stealth cadence, and Enter."""
    profile = resolve_profile_connection(args.profile)
    if not profile:
        return 1
    tab_id = resolve_tab_id(profile, tab_arg=args.tab)
    res = perform_type(
        profile,
        tab_id,
        target=args.target,
        text=args.text,
        clear=not args.no_clear,
        enter=args.enter,
        stealth=getattr(args, "stealth", False),
    )
    if res.get("ok"):
        print(f"Typed {res.get('length')} chars into '{args.target}'" + (" [Enter]" if args.enter else ""))
        return 0
    print(f"[!] {res.get('error')}", file=sys.stderr)
    return 1


def cmd_select(args: argparse.Namespace) -> int:
    """Selects an option in a native <select> or custom ARIA/mat-select dropdown."""
    profile = resolve_profile_connection(args.profile)
    if not profile:
        return 1
    tab_id = resolve_tab_id(profile, tab_arg=args.tab)
    res = perform_select(profile, tab_id, target=args.target, value=args.value)
    if res.get("ok"):
        print(f"Selected '{args.value}' on '{args.target}'")
        return 0
    print(f"[!] {res.get('error')}", file=sys.stderr)
    return 1


def cmd_check(args: argparse.Namespace) -> int:
    """Sets checkbox, radio, or ARIA switch to checked/unchecked."""
    profile = resolve_profile_connection(args.profile)
    if not profile:
        return 1
    tab_id = resolve_tab_id(profile, tab_arg=args.tab)
    desired = True if args.subcommand == "check" else False
    res = perform_check(profile, tab_id, target=args.target, desired_state=desired)
    if res.get("ok"):
        print(f"Set '{res.get('text')}' -> checked={res.get('checked')} (changed={res.get('changed')})")
        return 0
    print(f"[!] {res.get('error')}", file=sys.stderr)
    return 1


def cmd_wait(args: argparse.Namespace) -> int:
    """Waits for selector, text, URL match, element disappearance, or DOM/network settle."""
    profile = resolve_profile_connection(args.profile)
    if not profile:
        return 1
    tab_id = resolve_tab_id(profile, tab_arg=args.tab)
    res = perform_wait(
        profile,
        tab_id,
        selector=args.selector,
        text=args.text,
        url=getattr(args, "url", None),
        gone=getattr(args, "gone", None),
        idle=getattr(args, "idle", False),
        network_idle=getattr(args, "network_idle", False),
        timeout=args.timeout,
    )
    if res.get("ok"):
        print(f"Wait satisfied in {res.get('elapsed')}s: {res.get('detail', res.get('status', 'ok'))}")
        return 0
    print(f"[!] {res.get('error')}", file=sys.stderr)
    return 1


def cmd_scroll(args: argparse.Namespace) -> int:
    """Scrolls page, scrollable container, or brings an element into view."""
    profile = resolve_profile_connection(args.profile)
    if not profile:
        return 1
    tab_id = resolve_tab_id(profile, tab_arg=args.tab)
    res = perform_scroll(
        profile,
        tab_id,
        direction=args.direction,
        amount=args.amount,
        container=getattr(args, "container", None),
        into_view=getattr(args, "into_view", None),
    )
    if res.get("ok"):
        print(f"Scrolled: {json.dumps(res)}")
        return 0
    print(f"[!] {res.get('error')}", file=sys.stderr)
    return 1


def cmd_scroll_find(args: argparse.Namespace) -> int:
    """Scans a virtualized scrollable container until matching text/selector mounts."""
    profile = resolve_profile_connection(args.profile)
    if not profile:
        return 1
    tab_id = resolve_tab_id(profile, tab_arg=args.tab)
    res = perform_scroll_find(
        profile,
        tab_id,
        container=args.container,
        text=args.text,
        selector=args.selector,
        step=args.step,
        max_steps=args.max_steps,
        settle_ms=args.settle_ms,
    )
    if res.get("ok"):
        print(json.dumps(res, indent=2))
        return 0
    print(f"[!] {res.get('error')}", file=sys.stderr)
    return 1


def cmd_press(args: argparse.Namespace) -> int:
    """Dispatches arbitrary key or chord (e.g. 'Enter', 'Control+Shift+R', 'Alt+C')."""
    profile = resolve_profile_connection(args.profile)
    if not profile:
        return 1
    tab_id = resolve_tab_id(profile, tab_arg=args.tab)
    try:
        dispatch_cdp_key(profile, tab_id, args.keys)
        print(f"Dispatched key combo: {args.keys}")
        return 0
    except ValueError as e:
        print(f"[!] {e}", file=sys.stderr)
        return 1


def cmd_accelerator(args: argparse.Namespace) -> int:
    """Dispatches named application shortcuts or arbitrary key chords via trusted CDP events."""
    profile = resolve_profile_connection(args.profile)
    if not profile:
        return 1
    tab_id = resolve_tab_id(profile, tab_arg=args.tab)
    shortcut = args.name.lower().strip()

    if shortcut in ("drive-upload", "alt+c+u"):
        dispatch_cdp_key(profile, tab_id, "Alt+c")
        time.sleep(0.5)
        dispatch_cdp_key(profile, tab_id, "u")
        print("Dispatched Drive Upload Accelerator (Alt+C then U)")
        return 0
    if shortcut in ("share", "ctrl+alt+a"):
        dispatch_cdp_key(profile, tab_id, "Control+Alt+a")
        print("Dispatched Share Accelerator (Ctrl+Alt+A)")
        return 0
    if shortcut in ("esc", "escape"):
        dispatch_cdp_key(profile, tab_id, "Escape")
        print("Dispatched Escape Key")
        return 0
    if shortcut in ("period", "."):
        dispatch_cdp_key(profile, tab_id, ".")
        print("Dispatched Period (.) Action Key")
        return 0

    try:
        dispatch_cdp_key(profile, tab_id, args.name)
        print(f"Dispatched key combo: {args.name}")
        return 0
    except ValueError as e:
        print(f"[!] Unsupported accelerator: {e}", file=sys.stderr)
        return 1


def cmd_upload(args: argparse.Namespace) -> int:
    """Uploads local files via direct CDP input injection or file-chooser interception."""
    profile = resolve_profile_connection(args.profile)
    if not profile:
        return 1
    tab_id = resolve_tab_id(profile, tab_arg=args.tab)
    res = perform_upload(
        profile,
        tab_id,
        files=args.files,
        selector=args.selector,
        intercept=args.intercept,
        direct_cdp=getattr(args, "direct_cdp", False),
        trigger=args.trigger,
        accelerator=getattr(args, "accelerator", None),
    )
    if res.get("ok"):
        print(json.dumps(res, indent=2))
        return 0
    print(f"[!] Upload failed: {res.get('error')}", file=sys.stderr)
    return 1


def cmd_xhr_spy(args: argparse.Namespace) -> int:
    """Installs, reads, or clears live XHR/fetch upload & API telemetry (plus optional session refresh)."""
    profile = resolve_profile_connection(args.profile)
    if not profile:
        return 1
    tab_id = resolve_tab_id(profile, tab_arg=args.tab)
    res = perform_xhr_spy(
        profile,
        tab_id,
        install=getattr(args, "install", False),
        status=getattr(args, "status", False),
        clear=getattr(args, "clear", False),
        url_filter=getattr(args, "filter", None),
        refresh_url=getattr(args, "refresh_url", None),
    )
    if res.get("ok"):
        print(json.dumps(res, indent=2))
        return 0
    print(f"[!] XHR spy failed: {res.get('error')}", file=sys.stderr)
    return 1


def cmd_type_otp(args: argparse.Namespace) -> int:
    """Types an explicit OTP code or TOTP secret char-by-char via CDP Input.dispatchKeyEvent."""
    profile = resolve_profile_connection(args.profile)
    if not profile:
        return 1
    tab_id = resolve_tab_id(profile, tab_arg=args.tab)
    res = perform_type_otp(
        profile,
        tab_id,
        code=getattr(args, "code", None),
        totp_secret=getattr(args, "totp_secret", None),
        selector=getattr(args, "selector", None),
        submit_text=getattr(args, "submit_text", None),
        auto_verify=getattr(args, "auto_verify", True),
        delay_ms=getattr(args, "delay_ms", 60),
    )
    if res.get("ok"):
        print(json.dumps(res, indent=2))
        return 0
    print(f"[!] OTP input failed: {res.get('error')}", file=sys.stderr)
    return 1


def cmd_optimize_pdf(args: argparse.Namespace) -> int:
    """Compresses embedded scanned PDF images in-place while preserving OCR text layers."""
    res = optimize_pdf_file(
        input_pdf=args.input_pdf,
        output_pdf=getattr(args, "output", None),
        max_height=getattr(args, "max_height", 960),
        quality=getattr(args, "quality", 28),
        black_point=getattr(args, "black_point", 65),
        white_point=getattr(args, "white_point", 195),
    )
    if res.get("ok"):
        print(json.dumps(res, indent=2))
        return 0
    print(f"[!] PDF optimization failed: {res.get('error')}", file=sys.stderr)
    return 1


def cmd_dialog(args: argparse.Namespace) -> int:
    """Accepts or dismisses active JavaScript alert/confirm/prompt dialogs."""
    profile = resolve_profile_connection(args.profile)
    if not profile:
        return 1
    tab_id = resolve_tab_id(profile, tab_arg=args.tab)
    accept = not getattr(args, "dismiss", False)
    res = execute_browser_command(
        "HANDLE_DIALOG",
        {"tabId": tab_id, "accept": accept, "promptText": getattr(args, "prompt_text", None)},
        profile=profile,
    )
    if res.get("ok"):
        print(f"Dialog {'accepted' if accept else 'dismissed'}")
        return 0
    print(f"[!] Dialog handling failed: {res.get('error')}", file=sys.stderr)
    return 1


def cmd_logs(args: argparse.Namespace) -> int:
    """Enables, fetches, or clears console & network error telemetry on target tab."""
    profile = resolve_profile_connection(args.profile)
    if not profile:
        return 1
    tab_id = resolve_tab_id(profile, tab_arg=args.tab)

    if getattr(args, "enable", False):
        res = execute_browser_command("ENABLE_TELEMETRY", {"tabId": tab_id, "enabled": True}, profile=profile)
        print(json.dumps(res, indent=2))
        return 0 if res.get("ok") else 1
    if getattr(args, "disable", False):
        res = execute_browser_command("ENABLE_TELEMETRY", {"tabId": tab_id, "enabled": False}, profile=profile)
        print(json.dumps(res, indent=2))
        return 0 if res.get("ok") else 1
    if getattr(args, "clear", False) and not getattr(args, "fetch", False):
        res = execute_browser_command("CLEAR_LOGS", {"tabId": tab_id}, profile=profile)
        print(json.dumps(res, indent=2))
        return 0 if res.get("ok") else 1

    res = execute_browser_command("GET_LOGS", {"tabId": tab_id, "clear": getattr(args, "clear", False)}, profile=profile)
    if not res.get("ok"):
        print(f"[!] Failed getting logs: {res.get('error')}", file=sys.stderr)
        return 1

    console_logs = res.get("console", [])
    net_errors = res.get("networkErrors", [])
    if getattr(args, "level", "all") == "error":
        console_logs = [c for c in console_logs if c.get("level") in ("error", "warning")]
    log_type = getattr(args, "type", "all")
    out_data: Dict[str, Any] = {"enabled": res.get("enabled")}
    if log_type in ("all", "console"):
        out_data["console"] = console_logs
    if log_type in ("all", "network"):
        out_data["networkErrors"] = net_errors

    out_str = json.dumps(out_data, indent=2)
    if getattr(args, "output", None):
        p = Path(args.output)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(out_str, encoding="utf-8")
        print(f"Logs saved -> {args.output}")
    else:
        print(out_str)
    return 0


def cmd_storage(args: argparse.Namespace) -> int:
    """Inspects cookies (via CDP) and localStorage/sessionStorage keys safely."""
    profile = resolve_profile_connection(args.profile)
    if not profile:
        return 1
    tab_id = resolve_tab_id(profile, tab_arg=args.tab)
    st_type = args.type
    raw = getattr(args, "raw", False)
    out: Dict[str, Any] = {}

    if st_type in ("cookies", "all"):
        c_res = cdp_send("Network.getCookies", {}, profile=profile, tab_id=tab_id)
        cookies = c_res.get("result", {}).get("cookies", []) if c_res.get("ok") else []
        if raw:
            out["cookies"] = cookies
        else:
            out["cookies"] = [
                {
                    "name": c.get("name"),
                    "domain": c.get("domain"),
                    "path": c.get("path"),
                    "httpOnly": c.get("httpOnly"),
                    "secure": c.get("secure"),
                    "valuePreview": (c.get("value", "")[:4] + "***") if c.get("value") else "",
                }
                for c in cookies
            ]

    if st_type in ("local", "session", "all"):
        s_js = f"""
        (() => {{
          const dump = (store) => {{
            const obj = {{}};
            for (let i = 0; i < store.length; i++) {{
              const k = store.key(i);
              const v = store.getItem(k) || '';
              obj[k] = {json.dumps(raw)} ? v : ('[' + v.length + ' chars]');
            }}
            return obj;
          }};
          return {{
            localStorage: {json.dumps(st_type in ('local', 'all'))} ? dump(window.localStorage) : undefined,
            sessionStorage: {json.dumps(st_type in ('session', 'all'))} ? dump(window.sessionStorage) : undefined
          }};
        }})()
        """
        s_res = eval_tab_js(s_js, profile=profile, tab_id=tab_id)
        if isinstance(s_res, dict):
            if "localStorage" in s_res and s_res["localStorage"] is not None:
                out["localStorage"] = s_res["localStorage"]
            if "sessionStorage" in s_res and s_res["sessionStorage"] is not None:
                out["sessionStorage"] = s_res["sessionStorage"]

    text_out = json.dumps(out, indent=2)
    if getattr(args, "output", None):
        p = Path(args.output)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text_out, encoding="utf-8")
        print(f"Storage state saved -> {args.output}")
    else:
        print(text_out)
    return 0


def cmd_check_auth(args: argparse.Namespace) -> int:
    """Runs the 2FA / CAPTCHA / identity verification circuit breaker on active page."""
    profile = resolve_profile_connection(args.profile)
    if not profile:
        return 1
    tab_id = resolve_tab_id(profile, tab_arg=args.tab)
    status = check_auth_circuit_breaker(profile, tab_id)
    print(json.dumps(status, indent=2))
    return 2 if status.get("triggered") else 0


def cmd_screenshot(args: argparse.Namespace) -> int:
    """Captures viewport or full-page screenshot (with optional [id] badges) and saves to file."""
    profile = resolve_profile_connection(args.profile)
    if not profile:
        return 1
    tab_id = resolve_tab_id(profile, tab_arg=args.tab)
    out_path = args.output or "temp_read/browser_live.png"
    ok = _capture_screenshot_file(
        profile,
        tab_id,
        out_path,
        badges=getattr(args, "badges", False),
        full_page=getattr(args, "full_page", False),
        fmt=getattr(args, "format", "png"),
        quality=getattr(args, "quality", 85),
    )
    if not ok:
        print("[!] Screenshot capture failed.", file=sys.stderr)
        return 1
    print(f"Screenshot captured -> {out_path}")
    return 0


def cmd_run_goal(args: argparse.Namespace) -> int:
    """Executes a multi-action batch pipeline in one process call with auth circuit breaking."""
    raw_actions = args.actions
    if getattr(args, "actions_file", None):
        raw_actions = Path(args.actions_file).read_text(encoding="utf-8")
    if not raw_actions:
        print("[!] Provide --actions or --actions-file", file=sys.stderr)
        return 1
    try:
        actions = json.loads(raw_actions)
    except Exception as e:
        print(f"[!] Invalid JSON in actions: {e}", file=sys.stderr)
        return 1

    profile = resolve_profile_connection(args.profile)
    if not profile:
        return 1
    tab_id = resolve_tab_id(profile, tab_arg=getattr(args, "tab", None))
    print(f"[BrowserOperator] Executing Goal: '{args.goal}' on '{profile}' ({len(actions)} steps)...")
    start = time.time()
    step_results: List[Dict[str, Any]] = []
    check_auth = not getattr(args, "no_auth_check", False)
    halt_on_error = not getattr(args, "continue_on_error", False)

    for idx, act in enumerate(actions, 1):
        step_type = str(act.get("action", "")).lower().strip()
        if check_auth and tab_id and step_type != "type-otp":
            auth = check_auth_circuit_breaker(profile, tab_id)
            if auth.get("triggered"):
                msg = f"2FA/CAPTCHA circuit breaker triggered before step {idx}: {auth.get('reasons')}"
                print(f"[!] {msg}", file=sys.stderr)
                step_results.append({"step": idx, "action": "auth_circuit_breaker", "ok": False, "reasons": auth.get("reasons")})
                if getattr(args, "output", None):
                    Path(args.output).write_text(json.dumps({"goal": args.goal, "halted": True, "steps": step_results}, indent=2), encoding="utf-8")
                return 2

        optional = bool(act.get("optional", False))
        print(f"  Step {idx}/{len(actions)}: [{step_type.upper()}] ...", end=" ", flush=True)
        res: Dict[str, Any] = {"ok": True}

        if step_type == "goto":
            url = act.get("url", "")
            execute_browser_command("NAVIGATE_TAB", {"tabId": tab_id, "url": url}, profile=profile, timeout=act.get("timeout", 20.0))
            if act.get("wait"):
                time.sleep(float(act["wait"]))
            res = {"ok": True, "url": url}
        elif step_type in ("back", "forward", "reload"):
            cmd_map = {"back": "GO_BACK", "forward": "GO_FORWARD", "reload": "RELOAD_TAB"}
            res = execute_browser_command(cmd_map[step_type], {"tabId": tab_id}, profile=profile)
        elif step_type == "new-tab":
            res = execute_browser_command("OPEN_TAB", {"url": act.get("url", "about:blank"), "active": act.get("active", True)}, profile=profile, require_tab=False)
            if res.get("ok") and res.get("tabId") and act.get("active", True):
                tab_id = res["tabId"]
        elif step_type == "switch-tab":
            res = execute_browser_command("SWITCH_TAB", {k: v for k, v in act.items() if k in ("tabId", "urlContains", "titleContains")}, profile=profile, require_tab=False)
            if res.get("ok") and res.get("tabId"):
                tab_id = res["tabId"]
        elif step_type == "close-tab":
            cid = act.get("tabId") or tab_id
            res = execute_browser_command("CLOSE_TAB", {"tabId": cid}, profile=profile, require_tab=False)
            tab_id = get_active_tab_id(profile)
        elif step_type == "wait":
            res = perform_wait(
                profile,
                tab_id,
                selector=act.get("selector"),
                text=act.get("text"),
                url=act.get("url"),
                gone=act.get("gone"),
                idle=bool(act.get("idle", False)),
                network_idle=bool(act.get("network_idle", False)),
                timeout=float(act.get("timeout", 10.0)),
            )
        elif step_type == "observe":
            obs = eval_tab_js(build_extraction_js(), profile=profile, tab_id=tab_id)
            res = {"ok": isinstance(obs, dict), "count": len(obs.get("interactive_index", [])) if isinstance(obs, dict) else 0}
        elif step_type == "click":
            target = act.get("id") or act.get("selector") or act.get("text")
            res = perform_click(
                profile,
                tab_id,
                target=str(target) if target is not None else None,
                role=act.get("role"),
                name=act.get("name"),
                button=act.get("button", "left"),
                double=bool(act.get("double", False)),
                stealth=bool(act.get("stealth", False)),
                js_fallback=bool(act.get("js_fallback", False)),
            )
        elif step_type == "hover":
            target = act.get("id") or act.get("selector") or act.get("text")
            res = perform_hover(profile, tab_id, target=str(target) if target is not None else None, role=act.get("role"), name=act.get("name"))
        elif step_type in ("type", "fill"):
            target = act.get("id") or act.get("selector") or act.get("target")
            res = perform_type(
                profile,
                tab_id,
                target=str(target),
                text=str(act.get("text", "")),
                clear=bool(act.get("clear", True)),
                enter=bool(act.get("enter", False)),
                stealth=bool(act.get("stealth", False)),
            )
        elif step_type == "select":
            target = act.get("id") or act.get("selector") or act.get("target")
            res = perform_select(profile, tab_id, target=str(target), value=str(act.get("value", "")))
        elif step_type in ("check", "uncheck"):
            target = act.get("id") or act.get("selector") or act.get("text")
            res = perform_check(profile, tab_id, target=str(target), desired_state=(step_type == "check"))
        elif step_type in ("press", "hotkey"):
            dispatch_cdp_key(profile, tab_id, str(act.get("keys") or act.get("key") or "Enter"))
            res = {"ok": True}
        elif step_type == "scroll":
            res = perform_scroll(
                profile,
                tab_id,
                direction=act.get("direction", "down"),
                amount=int(act.get("amount", 600)),
                container=act.get("container"),
                into_view=act.get("into_view"),
            )
        elif step_type == "scroll-find":
            res = perform_scroll_find(
                profile,
                tab_id,
                container=str(act.get("container", "[role='main']")),
                text=act.get("text"),
                selector=act.get("selector"),
                step=int(act.get("step", 600)),
                max_steps=int(act.get("max_steps", 25)),
                settle_ms=int(act.get("settle_ms", 350)),
            )
        elif step_type == "upload":
            res = perform_upload(
                profile,
                tab_id,
                files=list(act.get("files", [])),
                selector=act.get("selector"),
                intercept=bool(act.get("intercept", False)),
                direct_cdp=bool(act.get("direct_cdp", False)),
                trigger=act.get("trigger"),
                accelerator=act.get("accelerator"),
            )
        elif step_type == "xhr-spy":
            res = perform_xhr_spy(
                profile,
                tab_id,
                install=bool(act.get("install", False)),
                status=bool(act.get("status", False)),
                clear=bool(act.get("clear", False)),
                url_filter=act.get("filter"),
                refresh_url=act.get("refresh_url"),
            )
        elif step_type == "type-otp":
            res = perform_type_otp(
                profile,
                tab_id,
                code=act.get("code"),
                totp_secret=act.get("totp_secret"),
                selector=act.get("selector"),
                submit_text=act.get("submit_text"),
                auto_verify=bool(act.get("auto_verify", True)),
                delay_ms=int(act.get("delay_ms", 60)),
            )
        elif step_type == "dialog":
            res = execute_browser_command("HANDLE_DIALOG", {"tabId": tab_id, "accept": bool(act.get("accept", True)), "promptText": act.get("prompt_text")}, profile=profile)
        elif step_type == "screenshot":
            out_s = act.get("output", f"temp_read/goal_step_{idx}.png")
            ok_s = _capture_screenshot_file(profile, tab_id, out_s, badges=bool(act.get("badges", False)), full_page=bool(act.get("full_page", False)))
            res = {"ok": ok_s, "output": out_s}
        elif step_type == "read":
            fmt = act.get("format", "all")
            out_p = act.get("output")
            data = eval_tab_js(build_extraction_js(root_selector=act.get("selector")), profile=profile, tab_id=tab_id)
            if isinstance(data, dict) and "__eval_error__" not in data:
                if out_p:
                    p = Path(out_p)
                    p.parent.mkdir(parents=True, exist_ok=True)
                    if fmt == "tables":
                        p.write_text(json.dumps(data.get("tables", []), indent=2), encoding="utf-8")
                    elif fmt == "kpis":
                        p.write_text(json.dumps(data.get("kpi_cards", []), indent=2), encoding="utf-8")
                    elif fmt == "links":
                        p.write_text(json.dumps(data.get("links", []), indent=2), encoding="utf-8")
                    elif fmt == "forms":
                        p.write_text(json.dumps(data.get("forms", []), indent=2), encoding="utf-8")
                    elif fmt in ("md", "markdown"):
                        p.write_text(data.get("markdown_content", ""), encoding="utf-8")
                    else:
                        p.write_text(json.dumps(data, indent=2), encoding="utf-8")
                res = {"ok": True, "output": out_p}
            else:
                res = {"ok": False, "error": "Read failed"}
        elif step_type == "assert":
            chk = perform_wait(profile, tab_id, selector=act.get("selector"), text=act.get("text"), url=act.get("url"), timeout=float(act.get("timeout", 2.0)))
            res = chk if chk.get("ok") else {"ok": False, "error": f"Assertion failed: {act}"}
        elif step_type == "eval":
            ev = eval_tab_js(str(act.get("code", "null")), profile=profile, tab_id=tab_id)
            res = {"ok": not (isinstance(ev, dict) and "__eval_error__" in ev), "result": ev}
        elif step_type == "sleep":
            time.sleep(float(act.get("seconds", 1.0)))
            res = {"ok": True}
        else:
            res = {"ok": False, "error": f"Unknown goal action '{step_type}'"}

        ok = bool(res.get("ok", True))
        print("Done" if ok else f"FAILED ({res.get('error')})")
        step_results.append({"step": idx, "action": step_type, **res})
        if not ok and halt_on_error and not optional:
            if getattr(args, "output", None):
                Path(args.output).write_text(json.dumps({"goal": args.goal, "ok": False, "steps": step_results}, indent=2), encoding="utf-8")
            return 1
        time.sleep(float(act.get("pause", 0.25)))

    elapsed = round(time.time() - start, 2)
    if getattr(args, "output", None):
        out_p = Path(args.output)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps({"goal": args.goal, "ok": True, "elapsed": elapsed, "steps": step_results}, indent=2), encoding="utf-8")
    print(f"Goal '{args.goal}' completed in {elapsed}s!")
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    """Evaluates raw JavaScript expression in the active tab context."""
    profile = resolve_profile_connection(args.profile)
    if not profile:
        return 1
    tab_id = resolve_tab_id(profile, tab_arg=args.tab)
    res = execute_browser_command("EVAL_DOM", {"code": args.code, "tabId": tab_id}, profile=profile, timeout=args.timeout)
    if not res.get("ok"):
        print(f"[!] Error: {res.get('error')}", file=sys.stderr)
        return 1
    val = res.get("result")
    print(json.dumps(val, indent=2) if isinstance(val, (dict, list)) else val)
    return 0


# ==============================================================================
# MAIN CLI ROUTER
# ==============================================================================

def _add_common_target_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--profile", help="Target Chrome profile name, number, or email")
    p.add_argument("--tab", type=int, help="Target tab ID")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generalized Universal Chrome Profile Browser Operator")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # status
    p_status = subparsers.add_parser("status", help="Inspect bridge daemon, connected profiles, and active leases")
    p_status.set_defaults(func=cmd_status)

    # tabs
    p_tabs = subparsers.add_parser("tabs", help="List open tabs on target profile (or all connected profiles)")
    p_tabs.add_argument("--profile", help="Target Chrome profile")
    p_tabs.add_argument("--all", action="store_true", help="List tabs across all connected profiles")
    p_tabs.add_argument("--json", action="store_true", help="Output JSON")
    p_tabs.set_defaults(func=cmd_tabs)

    # new-tab
    p_nt = subparsers.add_parser("new-tab", help="Open a new tab (respecting low-RAM single-tab advisory)")
    p_nt.add_argument("url", nargs="?", default="about:blank", help="URL to open")
    p_nt.add_argument("--profile", help="Target Chrome profile")
    p_nt.add_argument("--background", action="store_true", help="Open tab in background")
    p_nt.add_argument("--reuse", action="store_true", help="Reuse active tab instead of opening a new one")
    p_nt.add_argument("--force", action="store_true", help="Suppress single-tab advisory")
    p_nt.set_defaults(func=cmd_new_tab)

    # switch-tab
    p_st = subparsers.add_parser("switch-tab", help="Focus/switch to an existing tab by ID, URL, or title")
    p_st.add_argument("--profile", help="Target Chrome profile")
    p_st.add_argument("--tab", type=int, help="Target tab ID")
    p_st.add_argument("--url", help="URL substring to match")
    p_st.add_argument("--title", help="Title substring to match")
    p_st.set_defaults(func=cmd_switch_tab)

    # close-tab
    p_ct = subparsers.add_parser("close-tab", help="Close a tab by ID, URL, or title")
    p_ct.add_argument("--profile", help="Target Chrome profile")
    p_ct.add_argument("--tab", type=int, help="Target tab ID")
    p_ct.add_argument("--url", help="URL substring to match")
    p_ct.add_argument("--title", help="Title substring to match")
    p_ct.set_defaults(func=cmd_close_tab)

    # back / forward / reload
    for nav_cmd in ("back", "forward", "reload"):
        p_nav = subparsers.add_parser(nav_cmd, help=f"Navigate browser {nav_cmd}")
        _add_common_target_flags(p_nav)
        if nav_cmd == "reload":
            p_nav.add_argument("--bypass-cache", action="store_true", help="Hard reload bypassing cache")
        p_nav.set_defaults(func=cmd_history_nav)

    # eval
    p_eval = subparsers.add_parser("eval", help="Evaluate JavaScript expression in tab")
    p_eval.add_argument("code", help="JavaScript expression or IIFE to evaluate")
    _add_common_target_flags(p_eval)
    p_eval.add_argument("--timeout", type=float, default=20.0)
    p_eval.set_defaults(func=cmd_eval)

    # goto
    p_goto = subparsers.add_parser("goto", help="Navigate to URL")
    p_goto.add_argument("url", help="Target URL")
    _add_common_target_flags(p_goto)
    p_goto.add_argument("--new-tab", action="store_true", help="Open URL in a new tab")
    p_goto.add_argument("--wait-until", choices=["interactive", "load", "settle"], default="interactive")
    p_goto.add_argument("--timeout", type=float, default=20.0, help="Navigation timeout")
    p_goto.set_defaults(func=cmd_goto)

    # meta
    p_meta = subparsers.add_parser("meta", help="Get page metadata, viewport, hydration, and auth circuit-breaker status")
    _add_common_target_flags(p_meta)
    p_meta.add_argument("--timeout", type=float, default=15.0)
    p_meta.set_defaults(func=cmd_meta)

    # read
    p_read = subparsers.add_parser("read", help="Extract structured page data (markdown, tables, KPIs, links, forms, meta)")
    p_read.add_argument("--format", choices=["all", "md", "markdown", "tables", "kpis", "links", "forms", "meta"], default="all")
    p_read.add_argument("--selector", help="Optional CSS selector to scope extraction")
    p_read.add_argument("-o", "--output", help="Save extracted content to output file")
    _add_common_target_flags(p_read)
    p_read.add_argument("--timeout", type=float, default=20.0)
    p_read.set_defaults(func=cmd_read)

    # observe
    p_obs = subparsers.add_parser("observe", help="List numbered interactive action space [id] across DOM, Shadow DOM, and iframes")
    _add_common_target_flags(p_obs)
    p_obs.add_argument("--viewport-only", action="store_true", help="Only list elements inside current viewport")
    p_obs.add_argument("--filter", help="Filter elements by substring")
    p_obs.add_argument("--json", action="store_true", help="Output JSON")
    p_obs.add_argument("--screenshot", help="Save annotated screenshot path")
    p_obs.add_argument("--badges", action="store_true", help="Draw [id] badges on screenshot")
    p_obs.add_argument("--timeout", type=float, default=20.0)
    p_obs.set_defaults(func=cmd_observe)

    # click
    p_click = subparsers.add_parser("click", help="Click element by ID, selector, ARIA role/name, or visible text")
    p_click.add_argument("target", nargs="?", help="Element numeric ID, CSS selector, or visible text")
    p_click.add_argument("--role", help="ARIA role filter (e.g. button, tab, option)")
    p_click.add_argument("--name", help="Accessible name / text filter")
    p_click.add_argument("--button", choices=["left", "right", "middle"], default="left")
    p_click.add_argument("--double", action="store_true", help="Double click")
    p_click.add_argument("--stealth", action="store_true", help="Use cubic Bezier stealth mouse motion")
    p_click.add_argument("--js-fallback", action="store_true", help="Fallback to el.click() if offscreen")
    _add_common_target_flags(p_click)
    p_click.add_argument("--timeout", type=float, default=15.0)
    p_click.set_defaults(func=cmd_click)

    # hover
    p_hover = subparsers.add_parser("hover", help="Hover pointer over element by ID, selector, ARIA role/name, or text")
    p_hover.add_argument("target", nargs="?", help="Element numeric ID, CSS selector, or visible text")
    p_hover.add_argument("--role", help="ARIA role filter")
    p_hover.add_argument("--name", help="Accessible name / text filter")
    _add_common_target_flags(p_hover)
    p_hover.set_defaults(func=cmd_hover)

    # type / fill
    for type_cmd in ("type", "fill"):
        p_type = subparsers.add_parser(type_cmd, help="Type/fill text into input (React/Angular safe)")
        p_type.add_argument("target", help="Element numeric ID, CSS selector, or label/placeholder text")
        p_type.add_argument("text", help="Text to type")
        p_type.add_argument("--enter", action="store_true", help="Press Enter after typing")
        p_type.add_argument("--no-clear", action="store_true", help="Do not clear existing input text")
        p_type.add_argument("--stealth", action="store_true", help="Use human-cadence typing")
        _add_common_target_flags(p_type)
        p_type.add_argument("--timeout", type=float, default=15.0)
        p_type.set_defaults(func=cmd_type)

    # select
    p_sel = subparsers.add_parser("select", help="Select option in <select> or ARIA combobox")
    p_sel.add_argument("target", help="Select element numeric ID, CSS selector, or label")
    p_sel.add_argument("value", help="Option value or visible text")
    _add_common_target_flags(p_sel)
    p_sel.set_defaults(func=cmd_select)

    # check / uncheck
    for chk_cmd in ("check", "uncheck"):
        p_chk = subparsers.add_parser(chk_cmd, help=f"Set checkbox/radio/switch to {chk_cmd}ed")
        p_chk.add_argument("target", help="Element numeric ID, CSS selector, or visible text")
        _add_common_target_flags(p_chk)
        p_chk.set_defaults(func=cmd_check)

    # wait
    p_wait = subparsers.add_parser("wait", help="Wait for element, text, URL, disappearance, or DOM/network settle")
    p_wait.add_argument("--selector", help="CSS selector to wait for")
    p_wait.add_argument("--text", help="Text substring to wait for")
    p_wait.add_argument("--url", help="URL substring to wait for")
    p_wait.add_argument("--gone", help="CSS selector or text to wait to disappear")
    p_wait.add_argument("--idle", action="store_true", help="Wait for DOM mutations and spinners to settle")
    p_wait.add_argument("--network-idle", action="store_true", help="Wait for network/DOM settle")
    p_wait.add_argument("--timeout", type=float, default=10.0, help="Wait timeout in seconds")
    _add_common_target_flags(p_wait)
    p_wait.set_defaults(func=cmd_wait)

    # scroll
    p_scroll = subparsers.add_parser("scroll", help="Scroll page, scrollable container, or bring element into view")
    p_scroll.add_argument("direction", choices=["down", "up", "top", "bottom", "left", "right"], default="down", nargs="?")
    p_scroll.add_argument("--amount", type=int, default=600, help="Scroll pixel delta")
    p_scroll.add_argument("--container", help="CSS selector of target scrollable container (e.g. .a-Cd-oa)")
    p_scroll.add_argument("--into-view", help="Scroll target [id], CSS selector, or text into center view")
    _add_common_target_flags(p_scroll)
    p_scroll.set_defaults(func=cmd_scroll)

    # scroll-find
    p_sf = subparsers.add_parser("scroll-find", help="Step through a virtualized scrollable container until target mounts")
    p_sf.add_argument("--container", required=True, help="CSS selector of scrollable container (e.g. .a-Cd-oa)")
    p_sf.add_argument("--text", help="Text substring to locate")
    p_sf.add_argument("--selector", help="CSS selector to locate")
    p_sf.add_argument("--step", type=int, default=600)
    p_sf.add_argument("--max-steps", type=int, default=25)
    p_sf.add_argument("--settle-ms", type=int, default=350)
    _add_common_target_flags(p_sf)
    p_sf.set_defaults(func=cmd_scroll_find)

    # press / hotkey
    for key_cmd in ("press", "hotkey"):
        p_press = subparsers.add_parser(key_cmd, help="Dispatch arbitrary key or chord (e.g. Enter, Control+Shift+R)")
        p_press.add_argument("keys", help="Key or modifier chord")
        _add_common_target_flags(p_press)
        p_press.set_defaults(func=cmd_press)

    # accelerator (backward-compatible)
    p_acc = subparsers.add_parser("accelerator", help="Dispatch named application shortcut or key chord via trusted CDP")
    p_acc.add_argument("name", help="Shortcut name (drive-upload, share, esc, period) or key chord")
    _add_common_target_flags(p_acc)
    p_acc.set_defaults(func=cmd_accelerator)

    # upload
    p_up = subparsers.add_parser("upload", help="Upload files via direct CDP input injection or file-chooser intercept")
    p_up.add_argument("files", nargs="+", help="Local file path(s) to upload")
    p_up.add_argument("--selector", help="CSS selector for <input type='file'>")
    p_up.add_argument("--intercept", action="store_true", help="Use file chooser interception + showOpenFilePicker stub")
    p_up.add_argument("--direct-cdp", action="store_true", help="Force direct CDP DOM.setFileInputFiles (bypass userGesture dialog restrictions)")
    p_up.add_argument("--trigger", help="Button selector or text to click when using --intercept")
    p_up.add_argument("--accelerator", help="Keyboard shortcut to trigger file chooser when using --intercept (e.g. Alt+c)")
    _add_common_target_flags(p_up)
    p_up.set_defaults(func=cmd_upload)

    # xhr-spy
    p_xhr = subparsers.add_parser("xhr-spy", help="Install, poll, or clear live XHR/fetch upload & API progress telemetry")
    p_xhr.add_argument("--install", action="store_true", help="Install idempotent XHR & fetch spy hook on tab")
    p_xhr.add_argument("--status", action="store_true", help="Read captured XHR/fetch progress and status summary")
    p_xhr.add_argument("--clear", action="store_true", help="Clear captured XHR/fetch spy buffer")
    p_xhr.add_argument("--filter", help="Filter captured requests by URL substring")
    p_xhr.add_argument("--refresh-url", help="Execute pre-upload session refresh POST before upload")
    _add_common_target_flags(p_xhr)
    p_xhr.set_defaults(func=cmd_xhr_spy)

    # type-otp
    p_otp = subparsers.add_parser("type-otp", help="Type OTP code char-by-char via CDP Input.dispatchKeyEvent (multi-box React/AntD safe)")
    p_otp.add_argument("code", nargs="?", help="Explicit OTP code (optional if --totp-secret is provided)")
    p_otp.add_argument("--totp-secret", help="Base32 RFC 6238 TOTP secret to generate live 6-digit code")
    p_otp.add_argument("--selector", help="CSS selector for OTP input or container (auto-detects visible modal OTP boxes by default)")
    p_otp.add_argument("--submit-text", help="Optional Verify button label to click if not auto-submitted")
    p_otp.add_argument("--auto-verify", dest="auto_verify", action="store_true", default=True, help="Click Verify if not auto-submitted (default: true)")
    p_otp.add_argument("--no-auto-verify", dest="auto_verify", action="store_false", help="Type OTP digits without clicking Verify")
    p_otp.add_argument("--delay-ms", type=int, default=60, help="Inter-digit delay in milliseconds (default: 60)")
    _add_common_target_flags(p_otp)
    p_otp.set_defaults(func=cmd_type_otp)

    # optimize-pdf
    p_pdf = subparsers.add_parser("optimize-pdf", help="Compress scanned PDF images in-place while preserving OCR text layer")
    p_pdf.add_argument("input_pdf", help="Source PDF path")
    p_pdf.add_argument("-o", "--output", help="Destination PDF path (default: <stem>_compact.pdf)")
    p_pdf.add_argument("--max-height", type=int, default=960, help="Maximum image pixel height (default: 960)")
    p_pdf.add_argument("--quality", type=int, default=28, help="JPEG quality 1-95 (default: 28)")
    p_pdf.add_argument("--black-point", type=int, default=65, help="Levels black point 0-254 (default: 65)")
    p_pdf.add_argument("--white-point", type=int, default=195, help="Levels white point 1-255 (default: 195)")
    p_pdf.set_defaults(func=cmd_optimize_pdf)

    # dialog
    p_dlg = subparsers.add_parser("dialog", help="Handle active JS alert/confirm/prompt dialog")
    p_dlg.add_argument("--accept", action="store_true", default=True, help="Accept dialog (default)")
    p_dlg.add_argument("--dismiss", action="store_true", help="Dismiss dialog")
    p_dlg.add_argument("--prompt-text", help="Text for JS prompt()")
    _add_common_target_flags(p_dlg)
    p_dlg.set_defaults(func=cmd_dialog)

    # logs
    p_logs = subparsers.add_parser("logs", help="Enable or read console & network error telemetry for a tab")
    p_logs.add_argument("--enable", action="store_true", help="Enable CDP console/network error capture on tab")
    p_logs.add_argument("--disable", action="store_true", help="Disable capture on tab")
    p_logs.add_argument("--clear", action="store_true", help="Clear captured logs")
    p_logs.add_argument("--fetch", action="store_true", help="Fetch logs before clearing")
    p_logs.add_argument("--type", choices=["all", "console", "network"], default="all")
    p_logs.add_argument("--level", choices=["all", "error"], default="all")
    p_logs.add_argument("-o", "--output", help="Save logs JSON to file")
    _add_common_target_flags(p_logs)
    p_logs.set_defaults(func=cmd_logs)

    # storage
    p_sto = subparsers.add_parser("storage", help="Inspect cookies, localStorage, and sessionStorage (masked by default)")
    p_sto.add_argument("--type", choices=["cookies", "local", "session", "all"], default="all")
    p_sto.add_argument("--raw", action="store_true", help="Include raw values (default masks sensitive values)")
    p_sto.add_argument("-o", "--output", help="Save JSON to file")
    _add_common_target_flags(p_sto)
    p_sto.set_defaults(func=cmd_storage)

    # check-auth
    p_auth = subparsers.add_parser("check-auth", help="Check active page for 2FA, identity verification, or CAPTCHA gates")
    _add_common_target_flags(p_auth)
    p_auth.set_defaults(func=cmd_check_auth)

    # screenshot
    p_snap = subparsers.add_parser("screenshot", help="Capture viewport or full-page screenshot")
    p_snap.add_argument("-o", "--output", default="temp_read/browser_live.png", help="Output image path")
    p_snap.add_argument("--badges", action="store_true", help="Overlay numeric [id] badges during capture")
    p_snap.add_argument("--full-page", action="store_true", help="Capture beyond viewport")
    p_snap.add_argument("--format", choices=["png", "webp", "jpeg"], default="png")
    p_snap.add_argument("--quality", type=int, default=85)
    _add_common_target_flags(p_snap)
    p_snap.set_defaults(func=cmd_screenshot)

    # run-goal
    p_goal = subparsers.add_parser("run-goal", help="Execute multi-action pipeline in one process call")
    p_goal.add_argument("goal", help="High level goal description")
    p_goal.add_argument("--actions", help="JSON array of action objects")
    p_goal.add_argument("--actions-file", help="Path to JSON file containing actions array")
    p_goal.add_argument("--no-auth-check", action="store_true", help="Disable automatic 2FA/CAPTCHA circuit breaker")
    p_goal.add_argument("--continue-on-error", action="store_true", help="Continue executing remaining steps on error")
    p_goal.add_argument("-o", "--output", help="Save step execution summary JSON")
    _add_common_target_flags(p_goal)
    p_goal.set_defaults(func=cmd_run_goal)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
