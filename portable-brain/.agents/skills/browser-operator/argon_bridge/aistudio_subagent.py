#!/usr/bin/env python3
"""aistudio_subagent.py - Google AI Studio Super-Subagent & 2M-Token Ingestion Driver.

Automates Google AI Studio (aistudio.google.com) to drive Gemini 4 Argon, Gemini 3.8 Flash,
Gemini 3.5 Flash Lite, and Gemini 3.1 Pro with up to 2,000,000 tokens of context at zero API credit cost
via the user's authentic logged-in Google One AI Premium Chrome profiles.

Features:
  - Multi-agent lease arbitration via profile_lock_manager (TTL, 25s heartbeats, auto-routing).
  - Single-Tab Invariant: Reuses existing aistudio.google.com tabs to preserve host RAM.
  - Automatic Onboarding & Modal Self-Healing (cookies, 18+ verification, Drive modal bypass).
  - Dynamic Model Selection (Gemini 4 Argon, Gemini 3.8 Flash, etc.).
  - Context Bundling: Ingests entire codebases, logs, and markdown specs up to 2M tokens (-f).
  - System Instructions Injection: Meta-role configuration.
  - Rich Artifact Harvesting: Formatted GFM, syntax-highlighted code blocks, tables, and token telemetry.
  - Screenshot Self-Healing: Diagnostic visual capture (--screenshot) via CDP.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BRIDGE_URL = "http://127.0.0.1:9229"

# Add current directory to path for profile_lock_manager
sys.path.insert(0, str(Path(__file__).parent))
try:
    import profile_lock_manager
except ImportError:
    profile_lock_manager = None

try:
    import popup_healer
except ImportError:
    popup_healer = None

GEMINI_SKILLS_DIR = Path(__file__).resolve().parents[2].parent / "gemini_skills"
ALLOWED_AISTUDIO_MODELS = {
    "argon": "gemini-4-argon",
    "gemini-4-argon": "gemini-4-argon",
    "4 argon": "gemini-4-argon",
    "neon": "gemini-4-neon",
    "gemini-4-neon": "gemini-4-neon",
    "4 neon": "gemini-4-neon",
}
BLOCKED_AISTUDIO_MODELS = ("hydrogen", "carbon")


def validate_aistudio_model(model_name: Optional[str]) -> str:
    """Enforces AI Studio model whitelist (gemini-4-argon / gemini-4-neon); hard-blocks Hydrogen & Carbon."""
    raw = (model_name or "gemini-4-argon").strip().lower()
    if any(b in raw for b in BLOCKED_AISTUDIO_MODELS):
        raise ValueError(
            f"Model '{model_name}' is blocked in browser bridges. "
            "Use 'gemini-4-argon' or 'gemini-4-neon' in AI Studio Playground."
        )
    if raw in ALLOWED_AISTUDIO_MODELS:
        return ALLOWED_AISTUDIO_MODELS[raw]
    if "argon" in raw:
        return "gemini-4-argon"
    if "neon" in raw:
        return "gemini-4-neon"
    raise ValueError(
        f"Unsupported AI Studio model '{model_name}'. Allowed Playground models: gemini-4-argon, gemini-4-neon."
    )


def resolve_system_skill(system_skill: Optional[str]) -> str:
    """Loads reusable AI Studio system instructions from brain/.agents/gemini_skills/<name>.md or explicit file path."""
    if not system_skill:
        return ""
    cand = Path(system_skill)
    if cand.is_file():
        return cand.read_text(encoding="utf-8", errors="replace").strip()
    slug = system_skill.strip().removesuffix(".md")
    skill_file = GEMINI_SKILLS_DIR / f"{slug}.md"
    if skill_file.is_file():
        return skill_file.read_text(encoding="utf-8", errors="replace").strip()
    raise FileNotFoundError(f"System skill not found: {system_skill} (checked {skill_file})")


def _scrub_for_cloud(text: str) -> str:
    """Best-effort 2-layer secret redaction before uploading text/bundles to AI Studio."""
    compiler_dir = Path(__file__).resolve().parents[2] / "full-sync" / "scripts"
    if str(compiler_dir) not in sys.path:
        sys.path.insert(0, str(compiler_dir))
    try:
        import offload_context_compiler
        scrubbed, _ = offload_context_compiler.redact_two_layer(text)
        return scrubbed
    except Exception:
        # Built-in fallback regex redaction before Wave 2 compiler exists
        text = re.sub(r"sk-[a-zA-Z0-9_\-]{20,}", "[REDACTED_API_KEY]", text)
        text = re.sub(r"AIza[0-9A-Za-z\-_]{35}", "[REDACTED_API_KEY]", text)
        text = re.sub(r"(?i)\bbearer\s+[a-zA-Z0-9_\-\.]{20,}", "Bearer [REDACTED_TOKEN]", text)
        text = re.sub(
            r'(?i)\b(password|passwd|secret|api[_-]?key|access[_-]?token)\s*[:=]\s*["\']?[^"\'\s\n]{6,}["\']?',
            r"\1: [REDACTED]",
            text,
        )
        return text


def call_bridge_api(
    endpoint: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """Helper to query local bridge daemon (preserves structured JSON on HTTP 4xx/5xx)."""
    url = f"{BRIDGE_URL}{endpoint}"
    data = json.dumps(payload).encode("utf-8") if payload else None
    headers = {"Content-Type": "application/json"} if payload else {}

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            parsed = json.loads(e.read().decode("utf-8"))
            if isinstance(parsed, dict):
                parsed.setdefault("http_status", e.code)
                return parsed
        except Exception:
            pass
        return {"ok": False, "http_status": e.code, "error": f"HTTP {e.code}: {e.reason}"}
    except urllib.error.URLError as e:
        raise ConnectionError(
            f"Cannot connect to Argon Bridge on {BRIDGE_URL}. Is server.py running? ({e})"
        )


def bundle_context_files(file_paths: List[str]) -> Tuple[str, int]:
    """Bundles multiple files into a clean, structured context payload with line numbers and token estimate."""
    blocks = []
    total_chars = 0
    for fp in file_paths:
        p = Path(fp)
        if not p.exists():
            print(f"[AIStudioSubagent] Warning: file not found: {fp}", file=sys.stderr)
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()
            numbered = "\n".join(f"{i+1:4d} | {line}" for i, line in enumerate(lines))
            total_chars += len(content)
            blocks.append(
                f"=== CONTEXT FILE: {p.name} ({p.as_posix()}) [{len(lines)} lines, {len(content)} bytes] ===\n{numbered}\n"
            )
        except Exception as e:
            blocks.append(f"=== CONTEXT FILE: {p.name} (Error reading: {e}) ===\n")

    combined = "\n".join(blocks)
    est_tokens = int(total_chars / 3.8)
    return combined, est_tokens


class HeartbeatThread(threading.Thread):
    """Background thread that automatically renews the surface-scoped profile lease every 25 seconds."""

    def __init__(self, profile_name: str, agent_id: str, surface: str = "aistudio", interval_sec: float = 25.0):
        super().__init__(daemon=True)
        self.profile_name = profile_name
        self.agent_id = agent_id
        self.surface = surface
        self.interval_sec = interval_sec
        self.stop_event = threading.Event()

    def run(self):
        while not self.stop_event.is_set():
            if self.stop_event.wait(self.interval_sec):
                break
            try:
                if profile_lock_manager:
                    profile_lock_manager.renew_profile_lease(
                        self.profile_name, agent_id=self.agent_id, extend_seconds=180.0, surface=self.surface
                    )
            except Exception:
                pass

    def stop(self):
        self.stop_event.set()


# -----------------------------------------------------------------------------
# AI Studio DOM Scripting Helpers
# -----------------------------------------------------------------------------

AI_STUDIO_HELPERS_JS = r"""
window.__agyStudio = {
    sleep: ms => new Promise(r => setTimeout(r, ms)),
    
    handleOnboardingAndModals: async function() {
        const logs = [];
        
        // 1. Accept Cookies
        const cookieBtn = Array.from(document.querySelectorAll('button')).find(b => 
            (b.innerText || '').trim().includes('OK, got it') || 
            (b.className || '').includes('glue-cookie-notification-bar__accept')
        );
        if (cookieBtn) {
            cookieBtn.click();
            logs.push("Dismissed cookie notification");
            await this.sleep(300);
        }
        
        // 2. Drive Modal -> Click 'Cancel and use Temporary chat'
        const tempChatBtn = Array.from(document.querySelectorAll('button')).find(b => 
            (b.innerText || '').toLowerCase().includes('cancel and use temporary chat') ||
            (b.innerText || '').toLowerCase().includes('temporary chat')
        );
        if (tempChatBtn) {
            tempChatBtn.click();
            logs.push("Dismissed Drive modal: selected Temporary chat");
            await this.sleep(300);
        }
        
        // 3. Onboarding Page flow (/onboarding)
        if (window.location.href.includes('/onboarding')) {
            // Check 18+ checkboxes
            const checkboxes = Array.from(document.querySelectorAll('input[type="checkbox"], mat-checkbox, [role="checkbox"]'));
            for (const cb of checkboxes) {
                if (!cb.checked) {
                    cb.click();
                    await this.sleep(150);
                }
            }
            // Intent tile
            const tile = document.querySelector('.intent-tile') || Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').includes('Chat with Gemini'));
            if (tile) {
                tile.click();
                await this.sleep(200);
            }
            // Continue buttons
            const continueButtons = Array.from(document.querySelectorAll('button')).filter(b => 
                (b.innerText || '').includes('Continue') || (b.innerText || '').includes('Continue to AI Studio')
            );
            for (const cb of continueButtons) {
                if (!cb.disabled) {
                    cb.click();
                    logs.push("Clicked onboarding continue: " + cb.innerText.trim());
                    await this.sleep(400);
                }
            }
        }
        
        // 4. Dismiss strictly safe promo / announcement dialogs (NEVER click consent/Drive/upgrade)
        const safeVerbs = new Set(['close', 'dismiss', 'got it', 'not now', 'no thanks', 'skip', 'ok', 'maybe later', '×', 'x']);
        const dialogButtons = Array.from(document.querySelectorAll(
            'mat-dialog-container button, [role="dialog"] button'
        ));
        for (const btn of dialogButtons) {
            const text = (btn.getAttribute('aria-label') || btn.innerText || '').toLowerCase().trim();
            if (safeVerbs.has(text)) {
                btn.click();
                logs.push("Dismissed dialog button: " + text);
                await this.sleep(200);
            }
        }
        
        return { ok: true, logs: logs };
    },

    assertActiveModel: function(expectedModel) {
        const expClean = (expectedModel || 'gemini-4-argon').toLowerCase();
        const card = document.querySelector('.model-selector-card, [data-test-id="model-selector-button"]');
        const raw = card ? (card.innerText || card.getAttribute('aria-label') || '').trim() : '';
        const low = raw.toLowerCase();
        if (low.includes('hydrogen') || low.includes('carbon')) {
            return { ok: false, blocked: true, actual: raw, error: 'Model card loaded blocked model: ' + raw };
        }
        const wantWord = expClean.includes('neon') ? 'neon' : 'argon';
        return { ok: low.includes(wantWord), actual: raw, expected: expectedModel };
    },

    configureRunSettings: async function(opts) {
        const cfg = opts || {};
        const report = { ok: true, applied: {} };

        // 1. Thinking Level (High / Medium / Low)
        if (cfg.thinking) {
            const want = String(cfg.thinking).trim().toLowerCase();
            const sel = document.querySelector('mat-select[aria-label="Thinking Level"], mat-select[aria-label*="Thinking" i]');
            if (sel) {
                const cur = (sel.innerText || '').trim().toLowerCase();
                if (!cur.includes(want)) {
                    sel.click();
                    await this.sleep(350);
                    const options = Array.from(document.querySelectorAll('.cdk-overlay-container mat-option, [role="option"]'));
                    const match = options.find(o => (o.innerText || '').trim().toLowerCase().includes(want));
                    if (match) {
                        match.click();
                        await this.sleep(250);
                        report.applied.thinking = (match.innerText || '').trim();
                    } else {
                        const bd = document.querySelector('.cdk-overlay-backdrop');
                        if (bd) bd.click();
                        report.applied.thinking_warning = 'Option not found: ' + cfg.thinking;
                    }
                } else {
                    report.applied.thinking = cur + ' (already)';
                }
            }
        }

        // 2. Tools switches (Grounding Search, Code execution, URL context)
        const switchTargets = [
            ['search', 'Grounding with Google Search', cfg.search],
            ['code_exec', 'Code execution', cfg.codeExec],
            ['url_context', 'Browse the url context', cfg.urlContext],
        ];
        for (const [key, ariaLabel, desired] of switchTargets) {
            if (typeof desired !== 'boolean') continue;
            const sw = document.querySelector(`button[role="switch"][aria-label="${ariaLabel}"]`)
                || document.querySelector(`button[role="switch"][aria-label*="${ariaLabel.split(' ')[0]}" i]`);
            if (sw) {
                const curChecked = sw.getAttribute('aria-checked') === 'true';
                if (curChecked !== desired) {
                    sw.click();
                    await this.sleep(200);
                }
                report.applied[key] = sw.getAttribute('aria-checked') === 'true';
            }
        }

        // 3. Max output tokens (expand Advanced settings first if needed)
        if (cfg.maxOutputTokens) {
            const clamped = Math.max(1, Math.min(1048576, Number(cfg.maxOutputTokens) || 800000));
            const advBtn = document.querySelector('button[aria-label="Expand or collapse advanced settings"]');
            let tokInput = document.querySelector('input[type="number"][aria-label="Maximum output tokens"]');
            if ((!tokInput || tokInput.offsetWidth === 0) && advBtn) {
                advBtn.click();
                await this.sleep(350);
                tokInput = document.querySelector('input[type="number"][aria-label="Maximum output tokens"]');
            }
            if (tokInput) {
                const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                tokInput.focus();
                setter.call(tokInput, String(clamped));
                tokInput.dispatchEvent(new Event('input', { bubbles: true }));
                tokInput.dispatchEvent(new Event('change', { bubbles: true }));
                tokInput.blur();
                await this.sleep(150);
                report.applied.max_output_tokens = Number(tokInput.value);
            }
        }

        return report;
    },
    
    selectModel: async function(targetModelName) {
        if (!targetModelName) return { ok: true, skipped: true };
        const cleanTarget = targetModelName.toLowerCase().replace(/[^a-z0-9]/g, '');
        
        // Check current model card text in right sidebar
        const modelCard = document.querySelector('.model-selector-card');
        if (modelCard) {
            const curText = (modelCard.innerText || '').toLowerCase().replace(/[^a-z0-9]/g, '');
            if (curText.includes(cleanTarget)) {
                return { ok: true, message: "Model already active: " + modelCard.innerText.split('\\n')[0] };
            }
        }
        
        // Open model selection drawer/dialog
        if (modelCard) {
            modelCard.click();
            await this.sleep(500);
        } else {
            const modelBtn = document.querySelector('[data-test-id="model-selector-button"], mat-select[aria-label*="Model" i]');
            if (modelBtn) {
                modelBtn.click();
                await this.sleep(500);
            }
        }
        
        // Scan options in overlay / drawer
        const options = Array.from(document.querySelectorAll(
            '.cdk-overlay-container mat-option, [role="option"], .model-option-card, .model-item, mat-dialog-container button, .model-picker-item, div[class*="model"]'
        ));
        
        let matched = null;
        for (const opt of options) {
            const optText = (opt.innerText || '').toLowerCase().replace(/[^a-z0-9]/g, '');
            if (optText.includes(cleanTarget)) {
                matched = opt;
                break;
            }
        }
        
        if (matched) {
            matched.click();
            await this.sleep(400);
            
            // Close drawer if close button is present
            const closeBtn = Array.from(document.querySelectorAll('button')).find(b => 
                (b.innerText || '').trim() === 'close' || 
                (b.getAttribute('aria-label') || '').toLowerCase().includes('close')
            );
            if (closeBtn) closeBtn.click();
            
            return { ok: true, message: "Activated model: " + matched.innerText.split('\\n')[0] };
        }
        
        // Close drawer if opened
        const closeBtn = Array.from(document.querySelectorAll('button')).find(b => 
            (b.innerText || '').trim() === 'close' || 
            (b.getAttribute('aria-label') || '').toLowerCase().includes('close')
        );
        if (closeBtn) closeBtn.click();
        
        return { ok: false, error: "Model option not found for: " + targetModelName };
    },
    
    setSystemInstructions: async function(systemText) {
        if (!systemText) return { ok: true, skipped: true };

        const findSysBox = () => (
            document.querySelector('textarea[aria-label*="System instructions" i]') ||
            document.querySelector('textarea[placeholder*="System instructions" i]') ||
            document.querySelector('[aria-label*="System instructions" i] textarea') ||
            document.querySelector('.system-instructions-textarea')
        );

        let sysBox = findSysBox();
        if (!sysBox) {
            const sysCard = document.querySelector('.system-instructions-card, button[aria-label*="System instructions" i]');
            if (sysCard) {
                sysCard.click();
                for (let i = 0; i < 15; i++) {
                    await this.sleep(150);
                    sysBox = findSysBox();
                    if (sysBox) break;
                }
            }
        }

        if (!sysBox) return { ok: false, error: "System instructions textarea not found" };

        sysBox.focus();
        const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
        if (nativeSetter) {
            nativeSetter.call(sysBox, systemText);
        } else {
            sysBox.value = systemText;
        }
        sysBox.dispatchEvent(new Event('input', { bubbles: true }));
        sysBox.dispatchEvent(new Event('change', { bubbles: true }));
        await this.sleep(200);

        // Close modal ONLY if there is an explicit Done/Save/Close button inside a dialog or system instructions drawer
        const doneBtn = Array.from(document.querySelectorAll('mat-dialog-container button, .system-instructions-drawer button')).find(b => {
            const t = (b.innerText || '').trim().toLowerCase();
            const a = (b.getAttribute('aria-label') || '').toLowerCase();
            return t === 'done' || t === 'save' || a.includes('close system');
        });
        if (doneBtn) {
            doneBtn.click();
            await this.sleep(200);
        }
        return { ok: true, message: "System instructions injected", chars: (sysBox.value || '').length };
    },

    injectPrompt: async function(promptText) {
        const orderedSelectors = [
            'textarea[aria-label*="Enter a prompt" i]',
            'textarea[placeholder*="Start typing" i]',
            'ms-prompt-input-wrapper textarea'
        ];
        let ta = null;
        for (const sel of orderedSelectors) {
            const candidate = document.querySelector(sel);
            if (candidate && candidate.offsetParent !== null) {
                ta = candidate;
                break;
            }
        }
        if (!ta) {
            ta = Array.from(document.querySelectorAll('textarea')).find(t => {
                if (t.offsetParent === null) return false;
                const aria = (t.getAttribute('aria-label') || '').toLowerCase();
                const ph = (t.getAttribute('placeholder') || '').toLowerCase();
                return !aria.includes('system') && !ph.includes('system');
            }) || null;
        }
        if (!ta) return { ok: false, error: "Prompt textarea not found" };

        ta.focus();
        const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
        if (nativeSetter) {
            nativeSetter.call(ta, promptText);
        } else {
            ta.value = promptText;
        }
        ta.dispatchEvent(new Event('input', { bubbles: true }));
        ta.dispatchEvent(new Event('change', { bubbles: true }));
        await this.sleep(300);
        return { ok: true, message: "Prompt injected successfully", targetAria: ta.getAttribute('aria-label') || '', chars: (ta.value || '').length };
    },

    clickRun: async function() {
        const runBtn = document.querySelector('button.ctrl-enter-submits') ||
            Array.from(document.querySelectorAll('button')).find(b => {
                if (b.offsetParent === null) return false;
                const txt = (b.innerText || '').trim().toLowerCase();
                const aria = (b.getAttribute('aria-label') || '').toLowerCase();
                if (aria.includes('settings') || txt.includes('settings')) return false;
                return aria === 'run' || aria.includes('run prompt') || txt.startsWith('run');
            });

        if (runBtn && !runBtn.disabled) {
            runBtn.click();
            return { ok: true, method: "button_click" };
        }

        // Fallback: Dispatch Ctrl+Enter on actual prompt textarea (never system instructions)
        const ta = document.querySelector('textarea[aria-label*="Enter a prompt" i]') ||
            document.querySelector('textarea[placeholder*="Start typing" i]');
        if (ta) {
            ta.focus();
            ta.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', ctrlKey: true, bubbles: true }));
            return { ok: true, method: "ctrl_enter" };
        }
        return { ok: false, error: "Run button not available or disabled" };
    },
    
    startFreshChat: async function() {
        const turns = document.querySelectorAll('ms-chat-turn');
        if (turns.length > 0) {
            const newChatBtn = document.querySelector('button[aria-label="New chat"]');
            if (newChatBtn) {
                newChatBtn.click();
                await this.sleep(400);
                const discardBtn = Array.from(document.querySelectorAll('button')).find(b => 
                    (b.innerText || '').toLowerCase().includes('discard and continue')
                );
                if (discardBtn) {
                    discardBtn.click();
                    await this.sleep(500);
                }
            }
        }
        return { ok: true, turns: document.querySelectorAll('ms-chat-turn').length };
    },
    
    _extractAnswerText: function(turn) {
        if (!turn) return "";

        const chunks = Array.from(turn.querySelectorAll('ms-text-chunk')).filter(
            el => !el.closest('ms-thought-chunk, .thought-container, .thought-activity-host, mat-expansion-panel')
        );
        const chunkTexts = chunks
            .map(el => (el.innerText || el.textContent || '').trim())
            .filter(Boolean);
        if (chunkTexts.length > 0) {
            return chunkTexts.join('\n').trim();
        }

        const cmarkNodes = Array.from(turn.querySelectorAll('ms-cmark-node')).filter(el => {
            if (el.closest('ms-thought-chunk, .thought-container, .thought-activity-host, mat-expansion-panel')) return false;
            const parentCmark = el.parentElement ? el.parentElement.closest('ms-cmark-node') : null;
            return !parentCmark;
        });
        const cmarkTexts = cmarkNodes
            .map(el => (el.innerText || el.textContent || '').trim())
            .filter(Boolean);
        if (cmarkTexts.length > 0) {
            return cmarkTexts.join('\n').trim();
        }

        const clone = turn.cloneNode(true);
        Array.from(clone.querySelectorAll(
            'ms-thought-chunk, .thought-container, mat-expansion-panel, button, mat-icon, .actions, .actions-container, .thumb-container, .turn-footer, .role-label'
        )).forEach(el => el.remove());
        let txt = (clone.innerText || clone.textContent || '').trim();
        txt = txt.replace(/^edit\s*more_vert\s*/i, '');
        txt = txt.replace(/^Model\s*/i, '');
        txt = txt.replace(/\s*\d+(\.\d+)?s\s*$/i, '');
        return txt.trim();
    },

    _isVisibleEnabled: function(el) {
        if (!el || el.disabled || el.getAttribute('aria-disabled') === 'true') return false;
        if (el.offsetParent === null) return false;
        const r = el.getBoundingClientRect();
        const s = window.getComputedStyle(el);
        return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
    },

    _isExcludedStopCandidate: function(el) {
        if (!el) return true;
        if (el.closest('.right-panel, .run-settings-panel, ms-run-settings, mat-dialog-container, [role="dialog"], .cdk-overlay-container')) {
            return true;
        }
        const combined = ((el.innerText || '') + ' ' + (el.getAttribute('aria-label') || '') + ' ' + (el.getAttribute('title') || '')).toLowerCase();
        return /settings|stop sequence|close|dismiss|clear|delete|remove|feedback/.test(combined);
    },

    _isStopControlVisible: function() {
        const runBtn = document.querySelector('button.ctrl-enter-submits') || Array.from(document.querySelectorAll('button')).find(b => {
            if (!this._isVisibleEnabled(b) || this._isExcludedStopCandidate(b)) return false;
            const txt = (b.innerText || '').trim().toLowerCase();
            const aria = (b.getAttribute('aria-label') || '').toLowerCase();
            return txt.startsWith('run') || txt.startsWith('stop') || aria === 'run' || aria.startsWith('stop');
        });
        if (runBtn && this._isVisibleEnabled(runBtn) && !this._isExcludedStopCandidate(runBtn)) {
            const runBtnText = ((runBtn.innerText || '') + ' ' + (runBtn.getAttribute('aria-label') || '')).toLowerCase();
            if (/\bstop\b|\bcancel\b/.test(runBtnText)) {
                return true;
            }
        }
        const stopCandidates = Array.from(document.querySelectorAll(
            'button[aria-label*="Cancel" i], button[aria-label*="Stop" i], button.cancel-button, button.stop-button'
        ));
        return stopCandidates.some(btn => {
            if (!this._isVisibleEnabled(btn) || this._isExcludedStopCandidate(btn)) return false;
            const combined = ((btn.innerText || '') + ' ' + (btn.getAttribute('aria-label') || '')).toLowerCase();
            return /\bstop\b|\bcancel\b/.test(combined);
        });
    },

    _detectErrorBanner: function() {
        const errRe = /(quota exceeded|rate limit|internal error|something went wrong|permission denied|resource has been exhausted|model is overloaded|too many requests|err_internet_disconnected|network error|failed to fetch|connection lost|429)/i;
        const transientRe = /(err_internet_disconnected|network error|failed to fetch|connection lost|something went wrong|internal error)/i;

        // Check browser offline / Chrome network error page
        const bodyHead = ((document.body && document.body.innerText) || '').slice(0, 1200);
        if (/ERR_INTERNET_DISCONNECTED|No internet|This site can.?t be reached/i.test(bodyHead)) {
            return { text: bodyHead.split('\n')[0].trim() || 'ERR_INTERNET_DISCONNECTED', transient: true };
        }

        const nodes = Array.from(document.querySelectorAll(
            'mat-snack-bar-container, .mat-mdc-snack-bar-label, .error-banner, .error-message, [role="alert"], ms-error-banner, .turn-error, .error-state, ms-chat-turn .error'
        ));
        for (const el of nodes) {
            if (el.offsetParent === null) continue;
            const r = el.getBoundingClientRect();
            const s = window.getComputedStyle(el);
            if (r.width <= 0 || r.height <= 0 || s.visibility === 'hidden' || s.display === 'none') continue;
            const txt = (el.innerText || el.textContent || '').trim();
            if (!txt) continue;
            if (errRe.test(txt)) {
                return { text: txt.slice(0, 400), transient: transientRe.test(txt) };
            }
        }
        return null;
    },

    _collectAnswerTurns: function() {
        const turns = Array.from(document.querySelectorAll('ms-chat-turn'));
        return turns.filter(t => (
            (t.querySelector('.model') || t.getAttribute('data-turn-role') === 'Model' || t.classList.contains('model-turn'))
            && !t.classList.contains('thought-activity-host')
        ));
    },

    _extractMultiTurnAnswer: function(answerTurns, baselineTurns) {
        const startIdx = Math.max(0, Number(baselineTurns) || 0);
        const targetTurns = answerTurns.slice(startIdx);
        const parts = targetTurns
            .map(t => this._extractAnswerText(t))
            .filter(txt => txt && txt.trim().length > 0);
        return {
            turns: targetTurns,
            text: parts.join('\n\n').trim()
        };
    },

    _turnHasFeedbackButtons: function(turn) {
        const controls = Array.from(turn?.querySelectorAll('button, [role="button"]') || []);
        const labels = controls.filter(control => this._isVisibleEnabled(control)).map(control =>
            [control.getAttribute('aria-label'), control.getAttribute('title'),
                control.getAttribute('mattooltip'), control.textContent].join(' ').toLowerCase());
        return labels.some(label => /thumb[_ -]?up|good response|helpful response|👍/.test(label)) &&
            labels.some(label => /thumb[_ -]?down|bad response|not helpful|👎/.test(label));
    },

    rerunCurrentPrompt: function(baselineTurns) {
        const dismiss = Array.from(document.querySelectorAll('mat-snack-bar-container button, [role="alert"] button'))
            .find(button => this._isVisibleEnabled(button));
        if (dismiss) dismiss.click();
        const answerTurns = this._collectAnswerTurns().slice(baselineTurns);
        const latest = answerTurns.at(-1);
        const controls = latest ? latest.querySelectorAll('button') : [];
        const rerun = Array.from(controls).find(button => {
            const label = [button.getAttribute('aria-label'), button.getAttribute('title'), button.innerText].join(' ');
            return this._isVisibleEnabled(button) && /\brerun\b|\bre-run\b|\bretry\b/.test(label.toLowerCase());
        });
        if (!rerun) return this.clickRun();
        rerun.click();
        return {ok: true, method: 'rerun_btn'};
    },

    getGenerationStatus: function(baselineTurns) {
        const isStopVisible = this._isStopControlVisible();
        const turns = Array.from(document.querySelectorAll('ms-chat-turn'));
        const answerTurns = this._collectAnswerTurns();
        const base = Math.max(0, Number(baselineTurns) || 0);
        const extracted = this._extractMultiTurnAnswer(answerTurns, base);
        const curText = extracted.text;

        const thoughtTurns = turns.filter(t => t.classList.contains('thought-activity-host'));
        let thoughtChars = 0;
        for (const tt of thoughtTurns) {
            thoughtChars += ((tt.innerText || tt.textContent || '').trim()).length;
        }
        for (const at of extracted.turns) {
            const tn = at.querySelector('ms-thought-chunk, .thought-container, mat-expansion-panel');
            if (tn) thoughtChars += ((tn.innerText || tn.textContent || '').trim()).length;
        }

        const errObj = this._detectErrorBanner();
        const headerText = (document.querySelector('.app-header, header, .top-bar') || document.body).innerText || '';
        const tokenMatch = headerText.match(/(\d[\d,]*\s*tokens?)/i);
        const tokenTelemetry = tokenMatch ? tokenMatch[1] : null;

        return {
            is_generating: isStopVisible,
            answer_turns_count: answerTurns.length,
            thought_turns_count: thoughtTurns.length,
            thought_chars: thoughtChars,
            total_turns_count: turns.length,
            text_length: curText.length,
            has_feedback_buttons: this._turnHasFeedbackButtons(extracted.turns.at(-1)),
            has_answer: extracted.turns.length > 0 && curText.length > 0,
            error_banner: errObj ? errObj.text : null,
            is_transient_network_error: Boolean(errObj && errObj.transient),
            token_telemetry: tokenTelemetry
        };
    },

    harvestRichContent: function(baselineTurns) {
        const turns = Array.from(document.querySelectorAll('ms-chat-turn'));
        const answerTurns = this._collectAnswerTurns();
        const base = Math.max(0, Number(baselineTurns) || 0);
        const extracted = this._extractMultiTurnAnswer(answerTurns, base);
        let targetTurns = extracted.turns;
        if (targetTurns.length === 0 && answerTurns.length > 0) {
            targetTurns = [answerTurns[answerTurns.length - 1]];
        }

        // Extract thoughts across all new thought turns or embedded thought chunks
        const thoughtTurns = turns.filter(t => t.classList.contains('thought-activity-host'));
        const thoughtParts = [];
        if (thoughtTurns.length > 0) {
            for (const tt of thoughtTurns.slice(-3)) {
                const tClone = tt.cloneNode(true);
                Array.from(tClone.querySelectorAll('button, mat-icon, .actions')).forEach(el => el.remove());
                const tTxt = (tClone.innerText || tClone.textContent || '').trim();
                if (tTxt) thoughtParts.push(tTxt);
            }
        }
        if (thoughtParts.length === 0) {
            for (const t of targetTurns) {
                const thoughtNode = t.querySelector('ms-thought-chunk, .thought-container, mat-expansion-panel');
                if (thoughtNode) {
                    const tTxt = (thoughtNode.innerText || thoughtNode.textContent || '').trim();
                    if (tTxt) thoughtParts.push(tTxt);
                }
            }
        }
        const thoughtText = thoughtParts.join('\n\n').trim();

        // Extract complete multi-turn answer text
        const fullText = targetTurns
            .map(t => this._extractAnswerText(t))
            .filter(Boolean)
            .join('\n\n')
            .trim();

        // 2. Code Blocks across all target turns
        const codeBlocks = [];
        const seenCode = new Set();
        for (const target of targetTurns) {
            const codeContainers = Array.from(target.querySelectorAll('pre, code-block, .code-container'));
            for (const c of codeContainers) {
                if (c.closest('ms-thought-chunk, .thought-container, mat-expansion-panel')) continue;
                const codeEl = c.querySelector('code') || c;
                const codeText = (codeEl.innerText || '').trim();
                if (!codeText || seenCode.has(codeText)) continue;
                seenCode.add(codeText);

                let lang = "code";
                const langEl = c.querySelector('.header-text, [class*="language-"], .code-block-decoration');
                if (langEl) {
                    lang = (langEl.innerText || '').trim();
                    if (!lang) {
                        const match = (langEl.className || '').match(/language-([a-zA-Z0-9_-]+)/);
                        if (match) lang = match[1];
                    }
                }
                codeBlocks.push({ language: lang || "code", code: codeText });
            }
        }

        // 3. Tables across all target turns
        const tables = [];
        for (const target of targetTurns) {
            const tableNodes = Array.from(target.querySelectorAll('table'));
            for (const tbl of tableNodes) {
                if (tbl.closest('ms-thought-chunk, .thought-container, mat-expansion-panel')) continue;
                const headers = Array.from(tbl.querySelectorAll('th')).map(th => th.innerText.trim());
                const rows = [];
                const trNodes = Array.from(tbl.querySelectorAll('tbody tr, tr')).filter(tr => tr.querySelectorAll('td').length > 0);
                for (const tr of trNodes) {
                    rows.push(Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim()));
                }
                let mdTable = "";
                if (headers.length > 0) {
                    mdTable += "| " + headers.join(" | ") + " |\\n| " + headers.map(() => "---").join(" | ") + " |\\n";
                }
                for (const r of rows) {
                    mdTable += "| " + r.join(" | ") + " |\\n";
                }
                tables.push({ headers, rows, markdown: mdTable });
            }
        }

        // 4. Token telemetry
        const headerText = (document.querySelector('.app-header, header, .top-bar') || document.body).innerText || '';
        const tokenMatch = headerText.match(/(\d[\d,]*\s*tokens?)/i);
        const tokenTelemetry = tokenMatch ? tokenMatch[1] : null;

        return {
            ok: true,
            text: fullText.trim(),
            thoughts: thoughtText,
            code_blocks_count: codeBlocks.length,
            code_blocks: codeBlocks,
            tables_count: tables.length,
            tables: tables,
            token_telemetry: tokenTelemetry
        };
    },
    
    openGetCodeAndHarvest: async function() {
        const getCodeBtn = Array.from(document.querySelectorAll('button')).find(b => 
            (b.innerText || '').toLowerCase().includes('get code') || 
            (b.getAttribute('aria-label') || '').toLowerCase().includes('get code')
        );
        if (!getCodeBtn) return { ok: false, error: 'Get code button not found' };
        getCodeBtn.click();
        
        let snippet = '';
        let tabs = [];
        for (let i = 0; i < 20; i++) {
            await this.sleep(200);
            const dialog = document.querySelector('mat-dialog-container, [role="dialog"], .cdk-overlay-container');
            if (dialog) {
                tabs = Array.from(dialog.querySelectorAll('mat-tab-header [role="tab"], button[role="tab"], .tab')).map(t => (t.innerText || '').trim());
                const codeEl = dialog.querySelector('pre code, pre, textarea');
                if (codeEl && codeEl.innerText.trim().length > 0) {
                    snippet = codeEl.innerText.trim();
                    break;
                }
            }
        }
        
        const closeBtn = Array.from(document.querySelectorAll('mat-dialog-container button, [role="dialog"] button')).find(b => 
            (b.innerText || '').toLowerCase().includes('close') || 
            (b.getAttribute('aria-label') || '').toLowerCase().includes('close')
        );
        if (closeBtn) closeBtn.click();
        
        return { ok: !!snippet, code: snippet, chars: snippet.length, tabs: tabs };
    }
};
"""


# -----------------------------------------------------------------------------
# Main Driver Execution Logic & Zero-Lag Upload / RAM Parking
# -----------------------------------------------------------------------------

def _wait_for_upload_chip_ready(
    profile_dir: str,
    tab_id: int,
    bundle_name: str,
    bundle_stem: str,
    timeout_sec: float = 6.0,
) -> Dict[str, Any]:
    """Polls up to timeout_sec for an AI Studio attachment chip to appear and upload spinner to finish."""
    deadline = time.time() + max(0.5, timeout_sec)
    check_js = f"""(() => {{
        const fileName = {json.dumps(bundle_name)};
        const fileStem = {json.dumps(bundle_stem)};
        const scope = document.querySelector('ms-prompt-input-wrapper, .prompt-input-wrapper, ms-chunk-editor, footer, main') || document.body;
        const isVis = (el) => {{
            if (!el || el.offsetParent === null) return false;
            const r = el.getBoundingClientRect();
            const s = window.getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
        }};
        const chips = Array.from(scope.querySelectorAll(
            'ms-file-chip, .file-chip, .attachment, .attachment-chip, ms-prompt-chunk, ms-media-chunk, [class*="file-chip"], [class*="attachment"]'
        )).filter(isVis);
        const scopeText = (scope.innerText || '');
        const hasName = Boolean((fileName && scopeText.includes(fileName)) || (fileStem && scopeText.includes(fileStem)));
        const spinners = Array.from(scope.querySelectorAll(
            'mat-progress-spinner, mat-spinner, mat-progress-bar, [role="progressbar"], .uploading'
        )).filter(isVis);
        return {{
            chip_detected: chips.length > 0 || hasName,
            chips_count: chips.length,
            has_name: hasName,
            spinner_active: spinners.length > 0,
            ready: (chips.length > 0 || hasName) && spinners.length === 0
        }};
    }})()"""
    last_state: Dict[str, Any] = {}
    while time.time() < deadline:
        res = call_bridge_api(
            "/command",
            method="POST",
            payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": check_js}},
            timeout=10.0,
        )
        st = res.get("result") if isinstance(res, dict) and isinstance(res.get("result"), dict) else {}
        last_state = st
        if st.get("ready"):
            return {"ok": True, "verified_chip": True, "state": st}
        time.sleep(0.5)
    return {
        "ok": False,
        "verified_chip": False,
        "state": last_state,
        "error": f"Attachment chip for '{bundle_name}' not detected/settled in DOM within {timeout_sec}s",
    }


def upload_context_bundle_cdp(
    profile_dir: str,
    tab_id: int,
    bundle_path: Path,
    verify_timeout_sec: float = 6.0,
) -> Dict[str, Any]:
    """Uploads a local context bundle file to AI Studio Playground via CDP DOM.setFileInputFiles (with chip readiness verification)."""
    abs_file = str(bundle_path.resolve())
    call_bridge_api("/command", method="POST", payload={"action": "CDP_COMMAND", "profile": profile_dir, "params": {"tabId": tab_id, "method": "DOM.enable"}})

    def _query_file_input() -> int:
        doc_res = call_bridge_api("/command", method="POST", payload={"action": "CDP_COMMAND", "profile": profile_dir, "params": {"tabId": tab_id, "method": "DOM.getDocument", "params": {"depth": -1, "pierce": True}}})
        root_id = (doc_res.get("result") or {}).get("root", {}).get("nodeId", 0)
        if not root_id:
            return 0
        q_res = call_bridge_api("/command", method="POST", payload={"action": "CDP_COMMAND", "profile": profile_dir, "params": {"tabId": tab_id, "method": "DOM.querySelector", "params": {"nodeId": root_id, "selector": "input[type='file']"}}})
        return int((q_res.get("result") or {}).get("nodeId", 0) or 0)

    node_id = _query_file_input()
    if not node_id:
        # Click Playground '+' / Insert asset button to mount <input type="file">
        call_bridge_api(
            "/command",
            method="POST",
            payload={
                "action": "EVAL_DOM",
                "profile": profile_dir,
                "params": {
                    "tabId": tab_id,
                    "code": """(() => {
                        const addBtn = document.querySelector('button[aria-label*="Insert" i], button[aria-label*="Add" i], ms-add-chunk-menu button, button.add-chunk-button');
                        if (addBtn) { addBtn.click(); return true; }
                        return false;
                    })()""",
                },
            },
        )
        time.sleep(0.5)
        node_id = _query_file_input()

    dispatched_method = None
    if node_id:
        set_res = call_bridge_api(
            "/command",
            method="POST",
            payload={
                "action": "CDP_COMMAND",
                "profile": profile_dir,
                "params": {"tabId": tab_id, "method": "DOM.setFileInputFiles", "params": {"nodeId": node_id, "files": [abs_file]}},
            },
        )
        if set_res.get("ok"):
            # Dismiss any open '+' menu backdrop cleanly
            call_bridge_api("/command", method="POST", payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": "const bd = document.querySelector('.cdk-overlay-backdrop'); if (bd) bd.click();"}})
            dispatched_method = "DOM.setFileInputFiles"
            chip_res = _wait_for_upload_chip_ready(
                profile_dir, tab_id, bundle_path.name, bundle_path.stem, timeout_sec=verify_timeout_sec
            )
            if chip_res.get("verified_chip"):
                return {"ok": True, "verified_chip": True, "method": dispatched_method, "file": abs_file, "chip_state": chip_res.get("state")}

    # In-memory DataTransfer drop/paste fallback (never steals Windows OS clipboard)
    b64_data = base64.b64encode(bundle_path.read_bytes()).decode("ascii")
    drop_js = f"""(() => {{
        const b64 = {json.dumps(b64_data)};
        const binStr = atob(b64);
        const bytes = new Uint8Array(binStr.length);
        for (let i = 0; i < binStr.length; i++) bytes[i] = binStr.charCodeAt(i);
        const dt = new DataTransfer();
        dt.items.add(new File([bytes], {json.dumps(bundle_path.name)}, {{ type: 'text/plain', lastModified: Date.now() }}));
        const ta = document.querySelector('textarea[aria-label*="Enter a prompt" i], .cdk-textarea-autosize.textarea, textarea');
        if (!ta) return {{ ok: false, error: 'Prompt textarea not found for DataTransfer upload' }};
        ta.focus();
        ta.dispatchEvent(new DragEvent('drop', {{ bubbles: true, cancelable: true, dataTransfer: dt }}));
        return {{ ok: true, method: 'DataTransfer.drop' }};
    }})()"""
    res = call_bridge_api("/command", method="POST", payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": drop_js}})
    drop_out = res.get("result") if isinstance(res, dict) and isinstance(res.get("result"), dict) else {}
    if drop_out.get("ok"):
        chip_res = _wait_for_upload_chip_ready(
            profile_dir, tab_id, bundle_path.name, bundle_path.stem, timeout_sec=min(4.0, verify_timeout_sec)
        )
        if chip_res.get("verified_chip"):
            return {"ok": True, "verified_chip": True, "method": "DataTransfer.drop", "file": abs_file, "chip_state": chip_res.get("state")}
        return {"ok": False, "verified_chip": False, "method": dispatched_method or "DataTransfer.drop", "error": chip_res.get("error", "Attachment chip not detected")}
    return {"ok": False, "verified_chip": False, "method": dispatched_method or "none", "error": drop_out.get("error") or "Upload failed"}


def park_tab_about_blank(profile_dir: str, tab_id: int) -> None:
    """Parks idle agent-owned AI Studio Playground tab at about:blank to free ~500-800 MB Angular V8 heap."""
    try:
        call_bridge_api(
            "/command",
            method="POST",
            payload={
                "action": "CDP_COMMAND",
                "profile": profile_dir,
                "agent_guarded": True,
                "params": {"tabId": tab_id, "method": "Page.navigate", "params": {"url": "about:blank"}},
            },
            timeout=10.0,
        )
    except Exception:
        pass


def reclaim_finished_tab(profile_dir: str, tab_id: int) -> None:
    """Close an owned tab cleanly via CLOSE_TAB; fall back to parking at about:blank only if CLOSE_TAB fails."""
    try:
        result = call_bridge_api(
            "/command",
            method="POST",
            payload={"action": "CLOSE_TAB", "profile": profile_dir, "agent_guarded": True, "params": {"tabId": tab_id}},
            timeout=5.0,
        )
        if result.get("ok"):
            print(f"[AIStudioSubagent] Closed finished agent tab {tab_id}.")
            return
        print(f"[AIStudioSubagent] CLOSE_TAB failed ({result.get('error')}); falling back to parking at about:blank.")
        park_tab_about_blank(profile_dir, tab_id)
    except Exception as exc:
        print(f"[AIStudioSubagent] Could not close finished tab {tab_id} ({exc}); attempting fallback park.", file=sys.stderr)
        try:
            park_tab_about_blank(profile_dir, tab_id)
        except Exception:
            pass


def ensure_extension_ready(preferred_profile: str, target_url: str = "https://aistudio.google.com/prompts/new_chat") -> Dict[str, Any]:
    """Ensures Chrome is running with the extension connected for the specified profile."""
    status = call_bridge_api("/status")
    connected = status.get("connected_extensions", [])

    for c in connected:
        if c.get("dir_name") == preferred_profile or c.get("email") == preferred_profile:
            return c

    # Prefer interactive /profile/open when host is on WinSta0\Default
    print(f"[AIStudioSubagent] Chrome extension not connected for {preferred_profile}. Launching...")
    if status.get("interactive_desktop"):
        launch_res = call_bridge_api("/profile/open", method="POST", payload={"profile": preferred_profile, "url": target_url, "auto_close_idle": True}, timeout=25.0)
    else:
        launch_res = call_bridge_api("/launch", method="POST", payload={"profile": preferred_profile, "url": target_url})
    if not launch_res.get("ok"):
        raise RuntimeError(f"Failed to launch Chrome for {preferred_profile}: {launch_res.get('error')}")

    print(f"[AIStudioSubagent] Waiting up to 15s for Chrome extension to register with bridge...")
    start_wait = time.time()
    while time.time() - start_wait < 15.0:
        time.sleep(1.5)
        st = call_bridge_api("/status")
        for c in st.get("connected_extensions", []):
            if c.get("dir_name") == preferred_profile or c.get("email") == preferred_profile:
                print(f"[AIStudioSubagent] Connected to {preferred_profile} ({c.get('email')})!")
                return c

    # Fallback to any connected extension
    st = call_bridge_api("/status")
    if st.get("connected_extensions_count", 0) > 0:
        fallback = st["connected_extensions"][0]
        print(f"[AIStudioSubagent] Using connected profile fallback: {fallback.get('dir_name')} ({fallback.get('email')})")
        return fallback

    raise ConnectionError(f"Chrome launched for {preferred_profile}, but extension failed to connect to {BRIDGE_URL}/ws within 15s.")


def _get_owned_tab_ids_for_profile(profile_dir: Optional[str]) -> set[str]:
    """Queries bridge GET /resources to obtain strictly agent-owned tab IDs for profile_dir."""
    if not profile_dir:
        return set()
    try:
        res = call_bridge_api("/resources", method="GET", timeout=5.0)
        if isinstance(res, dict) and res.get("ok"):
            prof_tabs = (res.get("owned_tabs") or {}).get(profile_dir) or {}
            return {str(k) for k in prof_tabs.keys()}
    except Exception:
        pass
    return set()


def find_or_open_ai_studio_tab(
    client: Dict[str, Any],
    target_url: str = "https://aistudio.google.com/prompts/new_chat",
    navigate_if_different: bool = True,
    owner: str = "aistudio_subagent",
    task: str = "",
) -> Tuple[int, bool]:
    """Strict Agent-Owned Tab Reuse: ONLY reuses tabs listed in /resources owned_tabs; never hijacks user tabs."""
    profile_dir = client.get("dir_name")
    owned_ids = _get_owned_tab_ids_for_profile(profile_dir)
    tabs_res = call_bridge_api("/command", method="POST", payload={"action": "LIST_TABS", "profile": profile_dir})
    tabs = tabs_res.get("tabs", [])

    # Search strictly among AGENT-OWNED tabs (prefer AI Studio tab, then parked about:blank tab)
    owned_aistudio_tab = None
    owned_blank_tab = None
    for t in tabs:
        tid_str = str(t.get("id"))
        if tid_str not in owned_ids:
            continue
        t_url = t.get("url") or ""
        if "aistudio.google.com" in t_url:
            owned_aistudio_tab = t
            break
        if t_url.strip().lower() in ("about:blank", "chrome://newtab/", "chrome://newtab") and owned_blank_tab is None:
            owned_blank_tab = t

    chosen_tab = owned_aistudio_tab or owned_blank_tab
    if chosen_tab is not None:
        tab_id = chosen_tab["id"]
        t_url = chosen_tab.get("url") or ""
        print(f"[AIStudioSubagent] Reusing agent-owned tab (tabId: {tab_id}, url: {t_url})")
        call_bridge_api("/command", method="POST", payload={"action": "CDP_COMMAND", "profile": profile_dir, "params": {"tabId": tab_id, "method": "Page.bringToFront"}})

        current_base = t_url.split("?")[0].rstrip("/")
        target_base = target_url.split("?")[0].rstrip("/")
        needs_nav = False

        if "aistudio.google.com" not in t_url or "/onboarding" in t_url:
            needs_nav = True
        elif navigate_if_different and current_base != target_base:
            needs_nav = True
        elif navigate_if_different and "?model=" in target_url and target_url not in t_url:
            needs_nav = True

        if needs_nav:
            print(f"[AIStudioSubagent] Navigating agent-owned tab to target surface -> {target_url}...")
            call_bridge_api(
                "/command",
                method="POST",
                payload={
                    "action": "CDP_COMMAND",
                    "profile": profile_dir,
                    "agent_guarded": True,
                    "params": {"tabId": tab_id, "method": "Page.navigate", "params": {"url": target_url}},
                },
            )
            time.sleep(3.5)

        return tab_id, True

    # No agent-owned tab found -> Open a fresh tab (server.py enforces MAX_AGENT_TABS=6 & registers ownership)
    print(f"[AIStudioSubagent] No agent-owned AI Studio tab found on {profile_dir}. Opening new agent tab -> {target_url}...")
    open_res = call_bridge_api(
        "/command",
        method="POST",
        payload={
            "action": "OPEN_TAB",
            "profile": profile_dir,
            "owner": owner,
            "surface": "aistudio",
            "task": task,
            "agent_guarded": True,
            "params": {"url": target_url, "active": True},
        },
    )
    if open_res.get("code") == "AGENT_CAPACITY_REACHED":
        raise RuntimeError(f"AGENT_CAPACITY_REACHED: {open_res.get('error')}")
    tab_id = open_res.get("tabId")
    if not tab_id:
        raise RuntimeError(f"Failed to open AI Studio tab: {open_res}")
    return tab_id, False


def capture_tab_screenshot(client: Dict[str, Any], tab_id: int, output_path: str) -> bool:
    """Captures a screenshot of the tab via CDP and saves it to output_path."""
    try:
        profile_dir = client.get("dir_name")
        res = call_bridge_api(
            "/command",
            method="POST",
            payload={
                "action": "CDP_COMMAND",
                "profile": profile_dir,
                "params": {
                    "tabId": tab_id,
                    "method": "Page.captureScreenshot",
                    "params": {"format": "png"},
                },
            },
        )
        data = res.get("result", {}).get("data")
        if res.get("ok") and data:
            p = Path(output_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(base64.b64decode(data))
            print(f"[AIStudioSubagent] Diagnostic screenshot saved -> {output_path}")
            return True
        else:
            print(f"[AIStudioSubagent] Screenshot capture failed: {res}", file=sys.stderr)
            return False
    except Exception as e:
        print(f"[AIStudioSubagent] Error capturing screenshot: {e}", file=sys.stderr)
        return False


def ask_ai_studio(
    prompt: str = "",
    context_files: Optional[List[str]] = None,
    preferred_profile: Optional[str] = None,
    model_name: str = "gemini-4-argon",
    system_instructions: Optional[str] = None,
    system_skill: Optional[str] = None,
    thinking: str = "High",
    max_output_tokens: int = 800000,
    search: bool = False,
    code_exec: bool = False,
    url_context: bool = False,
    timeout_sec: int = 300,
    output_file: Optional[str] = None,
    screenshot_path: Optional[str] = None,
    agent_id: str = "aistudio_subagent",
    session_id: Optional[str] = None,
    target_mode: str = "chat",
    surface: str = "playground",
    get_code: bool = False,
    get_code_output: Optional[str] = None,
    continue_chat: bool = False,
    keep_tab: bool = False,
    stall_reload_sec: float = 90.0,
    poll_interval_sec: float = 2.0,
    max_recovery_retries: int = 2,
) -> Dict[str, Any]:
    """Executes Playground-only consulting & codebase audits on AI Studio (4 Argon / 4 Neon)."""
    start_time = time.time()
    sid = session_id or f"studio_{int(start_time)}"
    surface_clean = surface.lower().strip()

    if surface_clean in ("apps", "build", "gallery", "my_apps", "library"):
        return {
            "ok": False,
            "code": "SURFACE_RETIRED",
            "error": (
                f"AI Studio surface '{surface_clean}' (/apps Builder / Gallery) is retired. "
                "Use Playground (--surface playground) with gemini-4-argon / gemini-4-neon for consulting & audits, "
                "and Antigravity Hydrogen locally for code edits."
            ),
        }

    validated_model = validate_aistudio_model(model_name)
    bucket_name = "aistudio_neon" if "neon" in validated_model else "aistudio_argon"
    max_tokens_clamped = max(1, min(1048576, int(max_output_tokens or 800000)))

    merged_sys = (system_instructions or "").strip()
    if system_skill:
        skill_text = resolve_system_skill(system_skill)
        merged_sys = f"{skill_text}\n\n{merged_sys}".strip() if merged_sys else skill_text

    if surface_clean == "freeform" or target_mode == "freeform":
        target_url = f"https://aistudio.google.com/prompts/new_freeform?model={validated_model}"
    else:
        target_url = f"https://aistudio.google.com/prompts/new_chat?model={validated_model}"

    print("\n" + "=" * 80)
    print(" GOOGLE AI STUDIO PLAYGROUND ORCHESTRATOR (Stateless High-Context)")
    print("=" * 80)
    print(f"Profile Preference : {preferred_profile or 'Waterfall Drain (Tier 1 Alt First)'}")
    print(f"Target Model       : {validated_model} (Thinking: {thinking}, MaxTokens: {max_tokens_clamped:,})")
    print(f"Tools              : Search={'ON' if search else 'OFF'} | CodeExec={'ON' if code_exec else 'OFF'} | URL={'ON' if url_context else 'OFF'}")
    print(f"Target URL         : {target_url}")
    if system_skill:
        print(f"System Skill       : {system_skill}")
    if prompt:
        print(f"Prompt             : {prompt[:70]}...")
    if context_files:
        print(f"Context Files      : {len(context_files)} file(s)")
    print(f"Timeout            : {timeout_sec}s")
    print("=" * 80 + "\n")

    # 1. Surface-Scoped & Bucket-Aware Lease Acquisition via Profile Lock Manager
    leased_profile = preferred_profile or "Profile 13"
    if profile_lock_manager:
        task_desc = f"AI Studio ({validated_model})"
        if prompt:
            task_desc += f": {prompt[:30]}"
        target_p, err = profile_lock_manager.acquire_profile_lease(
            agent_id=agent_id,
            preferred_profile=preferred_profile,
            task=task_desc,
            session_id=sid,
            lease_seconds=float(timeout_sec + 60),
            surface="aistudio",
            bucket=bucket_name,
        )
        if not target_p:
            return {"ok": False, "error": err or "No AI Studio profile available on bucket " + bucket_name}
        leased_profile = target_p
        print(f"[AIStudioSubagent] Active lease granted on: {leased_profile} (bucket={bucket_name})")

    heartbeat = HeartbeatThread(leased_profile, agent_id=agent_id, surface="aistudio")
    heartbeat.start()
    tab_id: Optional[int] = None
    profile_dir: str = leased_profile

    try:
        # 2. Ensure Extension is Ready & Connected
        client = ensure_extension_ready(leased_profile, target_url=target_url)
        profile_dir = client.get("dir_name", leased_profile)

        # 3. Agent-Owned Tab Reuse: Open or navigate directly via ?model= URL (never hijacks user tabs)
        tab_id, was_existing = find_or_open_ai_studio_tab(
            client,
            target_url=target_url,
            navigate_if_different=True,
            owner=agent_id,
            task=(prompt or "")[:60],
        )
        try:
            call_bridge_api(
                "/command", method="POST", timeout=5.0,
                payload={"action": "CDP_COMMAND", "profile": profile_dir, "agent_guarded": True,
                         "params": {"tabId": tab_id, "method": "Emulation.setFocusEmulationEnabled",
                                    "params": {"enabled": True}}},
            )
        except Exception as exc:
            print(f"[AIStudioSubagent] Focus emulation unavailable: {exc}", file=sys.stderr)
        time.sleep(3.0 if was_existing else 5.5)

        # Check auth redirect (NEEDS_REAUTH)
        url_check = call_bridge_api(
            "/command",
            method="POST",
            payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": "window.location.href"}},
        ).get("result", "")
        if "accounts.google.com" in str(url_check):
            if profile_lock_manager:
                profile_lock_manager.mark_profile_needs_reauth(profile_dir, "aistudio")
            return {"ok": False, "code": "NEEDS_REAUTH", "error": f"Profile {profile_dir} redirected to sign-in ({url_check})."}

        # 4. Inject Helper Library into Tab
        call_bridge_api(
            "/command",
            method="POST",
            payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": AI_STUDIO_HELPERS_JS}},
        )

        # 5. Dismiss safe modals & run 3-Stage Popup Self-Healer
        call_bridge_api(
            "/command",
            method="POST",
            payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": "window.__agyStudio.handleOnboardingAndModals();"}},
        )
        if popup_healer:
            heal_res = popup_healer.dismiss_blocking_popups(
                eval_fn=lambda code: call_bridge_api("/command", method="POST", payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": code}}),
                screenshot_fn=lambda out_p: capture_tab_screenshot(client, tab_id, out_p),
                surface="aistudio",
                target_point=(0.45, 0.85),
            )
            if heal_res.get("blocked"):
                return {"ok": False, "code": "POPUP_BLOCKING_INPUT", "error": f"Unknown blocking modal on AI Studio: {heal_res.get('anomaly_screenshot')}"}

        if not continue_chat:
            call_bridge_api(
                "/command",
                method="POST",
                payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": "window.__agyStudio.startFreshChat();"}},
            )
            time.sleep(0.5)

        if screenshot_path:
            capture_tab_screenshot(client, tab_id, screenshot_path)

        # 6. Mandatory Post-Load Model Card Assertion (NEVER allow Gemini 4 Hydrogen!)
        # Poll briefly on cold tab loads until Angular mounts .model-selector-card
        assert_res = {}
        for _wait_i in range(12):
            assert_res = (
                call_bridge_api(
                    "/command",
                    method="POST",
                    payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": f"window.__agyStudio.assertActiveModel({json.dumps(validated_model)});"}},
                ).get("result")
                or {}
            )
            if assert_res.get("ok") or assert_res.get("blocked") or (assert_res.get("actual") or "").strip():
                break
            time.sleep(0.7)
        if not assert_res.get("ok"):
            print(f"[AIStudioSubagent] Model card check: {assert_res}. Attempting fallback UI selection -> {validated_model}...")
            call_bridge_api(
                "/command",
                method="POST",
                payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": f"window.__agyStudio.selectModel({json.dumps(validated_model)});"}},
            )
            time.sleep(0.5)
            assert_res = (
                call_bridge_api(
                    "/command",
                    method="POST",
                    payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": f"window.__agyStudio.assertActiveModel({json.dumps(validated_model)});"}},
                ).get("result")
                or {}
            )
            if assert_res.get("blocked") or not assert_res.get("ok"):
                return {
                    "ok": False,
                    "code": "MODEL_ASSERTION_FAILED",
                    "error": f"Refusing to run prompt: active AI Studio model card did not match {validated_model} ({assert_res}).",
                }

        # 7. Configure Run Settings (Thinking, 800k output tokens, Search OFF, CodeExec, URL context)
        run_cfg_res = call_bridge_api(
            "/command",
            method="POST",
            payload={
                "action": "EVAL_DOM",
                "profile": profile_dir,
                "params": {
                    "tabId": tab_id,
                    "code": f"window.__agyStudio.configureRunSettings({json.dumps({'thinking': thinking, 'maxOutputTokens': max_tokens_clamped, 'search': bool(search), 'codeExec': bool(code_exec), 'urlContext': bool(url_context)})});",
                },
            },
        ).get("result") or {}
        print(f"[AIStudioSubagent] Run Settings configured: {run_cfg_res}")

        # 8. Inject System Instructions (Persona + inline instructions)
        if merged_sys:
            print(f"[AIStudioSubagent] Injecting System Instructions ({len(merged_sys)} chars)...")
            call_bridge_api(
                "/command",
                method="POST",
                payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": f"window.__agyStudio.setSystemInstructions({json.dumps(merged_sys)});"}},
            )

        # 9. Zero-Lag CDP File Upload when -f files exist OR prompt exceeds 10k chars
        short_prompt = _scrub_for_cloud(prompt or "")
        est_tokens = int(len(short_prompt) / 3.8)
        if context_files or len(short_prompt) > 10000:
            bundle_parts: List[str] = []
            if context_files:
                bundle_text, file_tokens = bundle_context_files(context_files)
                est_tokens += file_tokens
                bundle_parts.append(bundle_text)
            if len(short_prompt) > 10000:
                bundle_parts.append(f"=== FULL CONTEXT / PROMPT ===\n{short_prompt}\n")
                short_prompt = (
                    "Read the attached context bundle file thoroughly and respond to all instructions inside it. "
                    + short_prompt[:500]
                )
            combined_bundle = _scrub_for_cloud("\n\n".join(bundle_parts))
            bundle_file = Path(r"./temp_read") / f"aistudio_context_{int(time.time() * 1000)}.txt"
            bundle_file.parent.mkdir(parents=True, exist_ok=True)
            bundle_file.write_text(combined_bundle, encoding="utf-8")
            print(f"[AIStudioSubagent] Uploading context bundle ({len(combined_bundle):,} chars) via CDP DOM.setFileInputFiles -> {bundle_file.name}...")
            up_res = upload_context_bundle_cdp(profile_dir, tab_id, bundle_file)
            print(f"[AIStudioSubagent] Upload result: {up_res}")
            if not up_res.get("ok") or not up_res.get("verified_chip"):
                # Safe inline fallback when attachment chip was not verified so context is NEVER silently dropped
                if len(combined_bundle) <= 60000:
                    print(f"[AIStudioSubagent] Attachment chip not verified in DOM; falling back to inline prompt injection ({len(combined_bundle):,} chars).")
                    short_prompt = f"{combined_bundle}\n\n### TASK INSTRUCTIONS:\n{short_prompt}"
                else:
                    print(f"[AIStudioSubagent] Warning: attachment chip not verified and bundle exceeds 60k inline cap ({len(combined_bundle):,} chars).", file=sys.stderr)
            time.sleep(0.8)

        harvested_code = None
        if get_code and not short_prompt:
            print("[AIStudioSubagent] Harvesting <> Get code snippet from active Playground contract...")
            h_res = call_bridge_api(
                "/command",
                method="POST",
                payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": "window.__agyStudio.openGetCodeAndHarvest();"}},
            )
            harvested_code = (h_res.get("result") or {}).get("code")
            if harvested_code and get_code_output:
                p = Path(get_code_output)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(harvested_code, encoding="utf-8")
            return {
                "ok": True,
                "surface": "playground",
                "profile": leased_profile,
                "model": validated_model,
                "harvested_code": harvested_code,
                "duration_seconds": round(time.time() - start_time, 1),
            }

        # 10. Inject Concise Prompt & Run
        if short_prompt:
            print("[AIStudioSubagent] Injecting prompt payload into AI Studio editor...")
            call_bridge_api(
                "/command",
                method="POST",
                payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": f"window.__agyStudio.injectPrompt({json.dumps(short_prompt)});"}},
            )

            # Record baseline turns
            pre_status = call_bridge_api(
                "/command",
                method="POST",
                payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": "window.__agyStudio.getGenerationStatus(0);"}},
            ).get("result") or {}
            baseline_answer_turns = int(pre_status.get("answer_turns_count", 0) or 0)

            # Trigger Run
            print("[AIStudioSubagent] Triggering Run (execution started)...")
            call_bridge_api(
                "/command",
                method="POST",
                payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": "window.__agyStudio.clickRun();"}},
            )
            time.sleep(min(2.0, max(0.0, poll_interval_sec)))

            def _recover_mid_poll(reason: str, do_reload: bool = True) -> None:
                print(f"\n[AIStudioSubagent] Mid-poll recovery ({reason}, reload={do_reload})...", file=sys.stderr)
                try:
                    if popup_healer:
                        popup_healer.dismiss_blocking_popups(
                            eval_fn=lambda code: call_bridge_api("/command", method="POST", payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": code}}),
                            screenshot_fn=lambda out_p: capture_tab_screenshot(client, tab_id, out_p),
                            surface="aistudio",
                            target_point=(0.45, 0.85),
                        )
                    call_bridge_api(
                        "/command",
                        method="POST",
                        payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": "window.__agyStudio && window.__agyStudio.handleOnboardingAndModals();"}},
                    )
                except Exception:
                    pass
                if do_reload:
                    try:
                        call_bridge_api(
                            "/command",
                            method="POST",
                            payload={"action": "CDP_COMMAND", "profile": profile_dir, "params": {"tabId": tab_id, "method": "Page.reload"}},
                            timeout=15.0,
                        )
                        time.sleep(min(3.5, max(0.05, poll_interval_sec)))
                        call_bridge_api(
                            "/command",
                            method="POST",
                            payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": AI_STUDIO_HELPERS_JS}},
                        )
                        if popup_healer:
                            popup_healer.dismiss_blocking_popups(
                                eval_fn=lambda code: call_bridge_api("/command", method="POST", payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": code}}),
                                screenshot_fn=lambda out_p: capture_tab_screenshot(client, tab_id, out_p),
                                surface="aistudio",
                                target_point=(0.45, 0.85),
                            )
                    except Exception:
                        pass

            # Await Stream Completion with error-banner fast-fail & bounded network/stall/popup recovery
            def _rerun_in_place() -> bool:
                try:
                    result = call_bridge_api(
                        "/command", method="POST", timeout=5.0,
                        payload={"action": "EVAL_DOM", "profile": profile_dir,
                                 "params": {"tabId": tab_id, "code": f"window.__agyStudio.rerunCurrentPrompt({baseline_answer_turns});"}},
                    )
                    return bool(result.get("ok") and (result.get("result") or {}).get("ok"))
                except Exception:
                    return False

            print(f"[AIStudioSubagent] Monitoring generation stream (timeout: {timeout_sec}s)...")
            poll_start = time.time()
            last_activity_ts = poll_start
            last_length = 0
            last_thought_chars = 0
            last_thought_turns = 0
            last_is_gen = False
            stable_count = 0
            completed_cleanly = False
            recovery_attempts = 0
            eval_failures = 0
            empty_rerun_until = None

            while time.time() - poll_start < timeout_sec:
                time.sleep(max(0.0, poll_interval_sec))
                try:
                    status_res = call_bridge_api(
                        "/command",
                        method="POST",
                        payload={
                            "action": "EVAL_DOM",
                            "profile": profile_dir,
                            "params": {"tabId": tab_id, "code": f"window.__agyStudio.getGenerationStatus({baseline_answer_turns});"},
                        },
                    )
                except Exception as exc:
                    status_res = {"ok": False, "error": str(exc)}

                if not isinstance(status_res, dict) or not status_res.get("ok") or not isinstance(status_res.get("result"), dict):
                    eval_failures += 1
                    if recovery_attempts < max_recovery_retries:
                        recovery_attempts += 1
                        _recover_mid_poll(f"transient EVAL_DOM failure #{eval_failures}", do_reload=(eval_failures >= 2))
                        last_activity_ts = time.time()
                        continue
                    err_diag = r"./temp_read\aistudio_timeout_diag.png"
                    capture_tab_screenshot(client, tab_id, err_diag)
                    return {
                        "ok": False,
                        "code": "EVAL_DOM_TRANSIENT_FAILURE",
                        "error": f"Bridge EVAL_DOM failed repeatedly during AI Studio poll: {status_res}",
                        "profile": leased_profile,
                        "model": validated_model,
                        "diagnostic_screenshot": err_diag,
                        "recovery_attempts": recovery_attempts,
                        "duration_seconds": round(time.time() - start_time, 1),
                    }

                eval_failures = 0
                st_data = status_res.get("result") or {}
                is_gen = bool(st_data.get("is_generating", False))
                last_is_gen = is_gen
                cur_len = int(st_data.get("text_length", 0) or 0)
                cur_answer_turns = int(st_data.get("answer_turns_count", 0) or 0)
                cur_thought_chars = int(st_data.get("thought_chars", 0) or 0)
                cur_thought_turns = int(st_data.get("thought_turns_count", 0) or 0)
                has_answer = bool(st_data.get("has_answer", False))
                err_banner = st_data.get("error_banner")
                is_transient_net = bool(st_data.get("is_transient_network_error", False))
                telemetry = st_data.get("token_telemetry")

                if cur_len > last_length or cur_thought_chars > last_thought_chars or cur_thought_turns > last_thought_turns:
                    last_activity_ts = time.time()
                last_thought_chars = max(last_thought_chars, cur_thought_chars)
                last_thought_turns = max(last_thought_turns, cur_thought_turns)

                elapsed = round(time.time() - poll_start, 1)
                t_str = f" | Tokens: {telemetry}" if telemetry else ""
                print(f"\r[AIStudioSubagent] [{elapsed}s] Generating: {is_gen} | Answer Chars: {cur_len}{t_str}    ", end="", flush=True)

                # Fast-fail on error banners (with bounded in-place Rerun retry for transient network errors — never reload stateless Playground into blank!)
                if err_banner:
                    if is_transient_net and recovery_attempts < max_recovery_retries:
                        recovery_attempts += 1
                        _recover_mid_poll(f"transient network/DOM error: {err_banner}", do_reload=False)
                        _rerun_in_place()
                        time.sleep(2.0)
                        last_activity_ts = time.time()
                        continue
                    print(f"\n[AIStudioSubagent] Error banner detected on AI Studio: {err_banner}", file=sys.stderr)
                    if profile_lock_manager and re.search(r"quota|rate limit|resource has been exhausted|too many requests|429", str(err_banner), re.I):
                        profile_lock_manager.mark_bucket_cooldown(leased_profile, bucket_name, 1800, reason=str(err_banner))
                    err_diag = r"./temp_read\aistudio_error_diag.png"
                    capture_tab_screenshot(client, tab_id, err_diag)
                    return {
                        "ok": False,
                        "code": "AISTUDIO_ERROR_BANNER",
                        "error": f"AI Studio error banner detected: {err_banner}",
                        "error_banner": err_banner,
                        "profile": leased_profile,
                        "model": validated_model,
                        "diagnostic_screenshot": err_diag,
                        "recovery_attempts": recovery_attempts,
                        "duration_seconds": round(time.time() - start_time, 1),
                    }

                if is_gen and empty_rerun_until is not None:
                    empty_rerun_until = 0  # Retry has visibly started. Treat its next empty completion as final.
                if cur_len == 0 and not is_gen and st_data.get("has_feedback_buttons"):
                    if empty_rerun_until is None and recovery_attempts < max_recovery_retries:
                        recovery_attempts += 1
                        if _rerun_in_place():
                            empty_rerun_until = time.time() + 8.0
                            continue
                    if empty_rerun_until is not None and time.time() < empty_rerun_until:
                        continue
                    return {
                        "ok": False, "code": "EMPTY_MODEL_RESPONSE",
                        "error": "AI Studio finished without returning answer text.",
                        "profile": leased_profile, "model": validated_model,
                        "recovery_attempts": recovery_attempts,
                        "duration_seconds": round(time.time() - start_time, 1),
                    }

                # Extended 0-char stall -> NEVER reload a stateless Playground tab while High Thinking is actively generating!
                # Only run non-destructive popup healing when generation is NOT active and no answer appeared.
                if cur_len == 0 and not is_gen and (time.time() - last_activity_ts) >= stall_reload_sec and recovery_attempts < max_recovery_retries:
                    recovery_attempts += 1
                    _recover_mid_poll(f"0-char stall for >= {stall_reload_sec}s while idle", do_reload=False)
                    last_activity_ts = time.time()
                    continue

                turn_active = (cur_answer_turns > baseline_answer_turns and has_answer) or (baseline_answer_turns == 0 and has_answer)
                if turn_active and not is_gen and cur_len > 0:
                    if cur_len == last_length:
                        stable_count += 1
                        if stable_count >= 2:
                            print(f"\n[AIStudioSubagent] Generation complete! Harvesting rich output...")
                            completed_cleanly = True
                            break
                    else:
                        last_length = cur_len
                        stable_count = 0
                else:
                    last_length = cur_len
                    stable_count = 0

            # Rich Harvest (across ALL model turns after baseline_answer_turns)
            harvest_res = call_bridge_api(
                "/command",
                method="POST",
                payload={
                    "action": "EVAL_DOM",
                    "profile": profile_dir,
                    "params": {"tabId": tab_id, "code": f"window.__agyStudio.harvestRichContent({baseline_answer_turns});"},
                },
            )
            response_data = harvest_res.get("result") or {}
            raw_text = response_data.get("text", "")
            thoughts = response_data.get("thoughts")

            # Detect account verification gate rendered inline as a model error turn
            if re.search(r"must be verified before it can continue|aistudio\.google\.com/verify-account", raw_text or "", re.I):
                if profile_lock_manager:
                    profile_lock_manager.mark_profile_needs_reauth(profile_dir, "aistudio")
                return {
                    "ok": False,
                    "code": "NEEDS_VERIFY",
                    "error": f"Profile {profile_dir} requires one-time AI Studio verification: {(raw_text or '').strip()[:240]}",
                    "profile": leased_profile,
                    "model": validated_model,
                    "duration_seconds": round(time.time() - start_time, 1),
                }

            # Truthful Empty-Harvest Failure: NEVER return ok: True with an empty answer!
            if len((raw_text or "").strip()) == 0:
                diag_path = r"./temp_read\aistudio_timeout_diag.png"
                capture_tab_screenshot(client, tab_id, diag_path)
                return {
                    "ok": False,
                    "code": "EMPTY_HARVEST_TIMEOUT",
                    "error": (
                        f"AI Studio timed out or harvested an empty answer after {round(time.time() - start_time, 1)}s "
                        f"(completed={completed_cleanly}, last_generating={last_is_gen}, last_chars={last_length}). "
                        f"Diagnostic screenshot saved to {diag_path}."
                    ),
                    "profile": leased_profile,
                    "model": validated_model,
                    "diagnostic_screenshot": diag_path,
                    "recovery_attempts": recovery_attempts,
                    "duration_seconds": round(time.time() - start_time, 1),
                }
        else:
            response_data = {}
            raw_text = ""
            thoughts = None

        # Harvest code snippet if requested
        if get_code:
            print("[AIStudioSubagent] Harvesting <> Get code snippet from active Playground session...")
            h_res = call_bridge_api(
                "/command",
                method="POST",
                payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": "window.__agyStudio.openGetCodeAndHarvest();"}},
            )
            harvested_code = (h_res.get("result") or {}).get("code")
            if harvested_code and get_code_output:
                p = Path(get_code_output)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(harvested_code, encoding="utf-8")
                print(f"[AIStudioSubagent] <> Get code snippet saved -> {p.as_posix()}")

        duration = round(time.time() - start_time, 1)

        # Save Output to File
        if not output_file:
            timestamp_slug = time.strftime("%Y%m%d_%H%M%S")
            output_file = f"c:\\Users\\Flh\\Desktop\\brain\\temp_read\\aistudio_response_{timestamp_slug}.md"

        out_path = Path(output_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        report_content = f"# Google AI Studio Playground Output\n\n"
        report_content += f"- **Model**: `{validated_model}`\n"
        report_content += f"- **Profile**: `{leased_profile}`\n"
        report_content += f"- **Duration**: `{duration}s`\n"
        if response_data.get("token_telemetry"):
            report_content += f"- **Telemetry**: `{response_data.get('token_telemetry')}`\n"
        report_content += f"- **Context Files**: `{len(context_files) if context_files else 0}`\n\n"

        if thoughts:
            report_content += f"<details>\n<summary>Model Thinking Trace</summary>\n\n```text\n{thoughts}\n```\n\n</details>\n\n"

        if raw_text:
            report_content += f"## Response\n\n{raw_text}\n\n"

        if harvested_code:
            report_content += f"## Exported SDK Code (<> Get code)\n\n```python\n{harvested_code}\n```\n"

        out_path.write_text(report_content, encoding="utf-8")
        print(f"[AIStudioSubagent] Deliverable saved -> {out_path.as_posix()}")

        return {
            "ok": True,
            "surface": surface_clean,
            "profile": leased_profile,
            "model": validated_model,
            "duration_seconds": duration,
            "output_file": str(out_path),
            "text": raw_text,
            "thoughts": thoughts,
            "harvested_code": harvested_code,
            "code_blocks": response_data.get("code_blocks", []),
            "tables": response_data.get("tables", []),
            "token_telemetry": response_data.get("token_telemetry"),
        }

    finally:
        heartbeat.stop()
        if tab_id and not keep_tab and not continue_chat:
            reclaim_finished_tab(profile_dir, tab_id)
        if profile_lock_manager:
            profile_lock_manager.release_profile_lease(leased_profile, agent_id=agent_id, surface="aistudio")
            print(f"[AIStudioSubagent] Lease released on {leased_profile} (surface=aistudio).")


# -----------------------------------------------------------------------------
# CLI Entry Point
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query Google AI Studio Playground (4 Argon / 4 Neon) via authentic Chrome bridge.")
    parser.add_argument("prompt", nargs="?", default="", help="Task prompt or consulting query")
    parser.add_argument("-f", "--files", nargs="*", default=[], help="Context files to bundle & upload via CDP")
    parser.add_argument("--profile", default=None, help="Target Chrome profile (defaults to Waterfall Drain Tier 1 Alt Pool)")
    parser.add_argument("--model", default="gemini-4-argon", help="Playground model: gemini-4-argon (default) or gemini-4-neon")
    parser.add_argument("--thinking", choices=["High", "Medium", "Low"], default="High", help="Thinking Level (default: High)")
    parser.add_argument("--max-output-tokens", type=int, default=800000, help="Maximum output tokens (default: 800000, max: 1048576)")
    parser.add_argument("--search", choices=["on", "off"], default="off", help="Grounding with Google Search (default: off)")
    parser.add_argument("--code-exec", choices=["on", "off"], default="off", help="Code execution toggle (default: off)")
    parser.add_argument("--url-context", choices=["on", "off"], default="off", help="URL context toggle (default: off)")
    parser.add_argument("--system", default=None, help="Inline system instructions for the model")
    parser.add_argument("--system-skill", default=None, help="Persona name in .agents/gemini_skills/ or path to markdown system prompt")
    parser.add_argument("--surface", choices=["playground", "freeform", "apps", "build", "gallery", "my_apps", "library"], default="playground", help="Playground only (/apps retired)")
    parser.add_argument("--get-code", action="store_true", help="Harvest <> Get code snippet from active Playground")
    parser.add_argument("--get-code-output", default=None, help="File path to save harvested <> Get code snippet")
    parser.add_argument("--timeout", type=int, default=300, help="Max timeout seconds (default: 300)")
    parser.add_argument("-o", "--output", default=None, help="Path to save markdown output")
    parser.add_argument("--screenshot", default=None, help="Save diagnostic screenshot to file")
    parser.add_argument("--session-id", default=None, help="Session identifier for tracking")
    parser.add_argument("--continue-chat", action="store_true", help="Continue in existing chat turns instead of starting fresh")
    parser.add_argument("--keep-tab", action="store_true", help="Keep the finished Playground tab active")

    args = parser.parse_args()

    default_prompt = args.prompt
    if not default_prompt and args.surface == "playground" and not args.get_code:
        default_prompt = "Explain the core architectural advantage of Google AI Studio's high context window."

    try:
        res = ask_ai_studio(
            prompt=default_prompt,
            context_files=args.files,
            preferred_profile=args.profile,
            model_name=args.model,
            system_instructions=args.system,
            system_skill=args.system_skill,
            thinking=args.thinking,
            max_output_tokens=args.max_output_tokens,
            search=(args.search == "on"),
            code_exec=(args.code_exec == "on"),
            url_context=(args.url_context == "on"),
            timeout_sec=args.timeout,
            output_file=args.output,
            screenshot_path=args.screenshot,
            session_id=args.session_id,
            surface=args.surface,
            get_code=args.get_code,
            get_code_output=args.get_code_output,
            continue_chat=args.continue_chat,
            keep_tab=args.keep_tab,
        )
        if res.get("ok"):
            print("\n" + "=" * 80)
            print(" GOOGLE AI STUDIO RESPONSE SUMMARY")
            print("=" * 80)
            if res.get("text"):
                preview = res["text"][:600] + ("..." if len(res["text"]) > 600 else "")
                print(preview)
            elif res.get("harvested_code"):
                print("Harvested SDK Client Code:")
                print(res["harvested_code"][:500] + ("..." if len(res["harvested_code"]) > 500 else ""))
            print("=" * 80)
            if res.get("output_file"):
                print(f"Delivered to: {res.get('output_file')}")
            print(f"Time Taken  : {res.get('duration_seconds')}s\n")
        else:
            print(f"Execution Error: {res.get('error')}", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)
