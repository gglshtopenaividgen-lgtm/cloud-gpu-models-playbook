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


def call_bridge_api(
    endpoint: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """Helper to query local bridge daemon."""
    url = f"{BRIDGE_URL}{endpoint}"
    data = json.dumps(payload).encode("utf-8") if payload else None
    headers = {"Content-Type": "application/json"} if payload else {}

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return json.loads(res.read().decode("utf-8"))
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
    """Background thread that automatically renews the profile lease every 25 seconds."""

    def __init__(self, profile_name: str, agent_id: str, interval_sec: float = 25.0):
        super().__init__(daemon=True)
        self.profile_name = profile_name
        self.agent_id = agent_id
        self.interval_sec = interval_sec
        self.stop_event = threading.Event()

    def run(self):
        while not self.stop_event.is_set():
            if self.stop_event.wait(self.interval_sec):
                break
            try:
                call_bridge_api(
                    "/lock/renew",
                    method="POST",
                    payload={"profile": self.profile_name, "holder": self.agent_id, "ttl": 300.0},
                    timeout=5.0,
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
        
        // 4. Dismiss generic dialogs and backdrops
        const dialogButtons = Array.from(document.querySelectorAll(
            'mat-dialog-container button, [role="dialog"] button, .cdk-overlay-container button'
        ));
        for (const btn of dialogButtons) {
            const text = (btn.innerText || btn.getAttribute('aria-label') || '').toLowerCase().trim();
            if (['get started', 'i agree', 'accept', 'got it', 'close', 'dismiss'].includes(text)) {
                btn.click();
                logs.push("Dismissed dialog button: " + text);
                await this.sleep(200);
            }
        }
        
        return { ok: true, logs: logs };
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
        
        const sysCard = document.querySelector('.system-instructions-card, button[aria-label*="System instructions" i]');
        if (sysCard) {
            sysCard.click();
            await this.sleep(300);
        }
        
        let sysBox = document.querySelector(
            'textarea[placeholder*="System instructions" i], [aria-label*="System instructions" i] textarea, .system-instructions-textarea'
        );
        
        if (!sysBox) return { ok: false, error: "System instructions textarea not found" };
        
        sysBox.focus();
        sysBox.value = systemText;
        sysBox.dispatchEvent(new Event('input', { bubbles: true }));
        sysBox.dispatchEvent(new Event('change', { bubbles: true }));
        
        // Close modal if there's a done/close button
        const doneBtn = Array.from(document.querySelectorAll('button')).find(b => 
            (b.innerText || '').trim() === 'Done' || (b.innerText || '').trim() === 'Save'
        );
        if (doneBtn) {
            doneBtn.click();
            await this.sleep(200);
        }
        return { ok: true, message: "System instructions injected" };
    },
    
    injectPrompt: async function(promptText) {
        const ta = document.querySelector(
            'textarea[aria-label*="Enter a prompt" i], .cdk-textarea-autosize.textarea, textarea[placeholder*="Start typing" i], textarea'
        );
        if (!ta) return { ok: false, error: "Prompt textarea not found" };
        
        ta.focus();
        ta.value = promptText;
        ta.dispatchEvent(new Event('input', { bubbles: true }));
        ta.dispatchEvent(new Event('change', { bubbles: true }));
        await this.sleep(300);
        return { ok: true, message: "Prompt injected successfully" };
    },
    
    clickRun: async function() {
        const runBtn = document.querySelector(
            'button.ctrl-enter-submits, button[aria-label*="Run" i]'
        ) || Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').includes('Run'));
        
        if (runBtn && !runBtn.disabled) {
            runBtn.click();
            return { ok: true, method: "button_click" };
        }
        
        // Fallback: Dispatch Ctrl+Enter on prompt textarea
        const ta = document.querySelector('textarea');
        if (ta) {
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
    
    getGenerationStatus: function() {
        const runBtn = document.querySelector('button.ctrl-enter-submits') || Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').includes('Run'));
        const runBtnText = runBtn ? (runBtn.innerText || '').trim() : '';
        const isStopVisible = runBtnText.toLowerCase().includes('stop') || !!document.querySelector('button[aria-label*="Cancel" i], button[aria-label*="Stop" i], button.cancel-button');
        
        const turns = Array.from(document.querySelectorAll('ms-chat-turn'));
        const answerTurns = turns.filter(t => t.querySelector('.model') && !t.classList.contains('thought-activity-host'));
        const activeAnswerTurn = answerTurns.length > 0 ? answerTurns[answerTurns.length - 1] : null;
        const textChunk = activeAnswerTurn ? activeAnswerTurn.querySelector('ms-text-chunk') : null;
        const curText = textChunk ? (textChunk.innerText || '').trim() : (activeAnswerTurn ? (activeAnswerTurn.innerText || '').trim() : '');
        
        const thoughtTurns = turns.filter(t => t.classList.contains('thought-activity-host'));
        
        const headerText = (document.querySelector('.app-header, header, .top-bar') || document.body).innerText || '';
        const tokenMatch = headerText.match(/([0-9,]+\s*tokens?)/i);
        const tokenTelemetry = tokenMatch ? tokenMatch[1] : null;
        
        return {
            is_generating: isStopVisible,
            answer_turns_count: answerTurns.length,
            thought_turns_count: thoughtTurns.length,
            total_turns_count: turns.length,
            text_length: curText.length,
            has_answer: !!textChunk && curText.length > 0,
            token_telemetry: tokenTelemetry
        };
    },
    
    harvestRichContent: function() {
        const turns = Array.from(document.querySelectorAll('ms-chat-turn'));
        const answerTurns = turns.filter(t => t.querySelector('.model') && !t.classList.contains('thought-activity-host'));
        const target = answerTurns.length > 0 ? answerTurns[answerTurns.length - 1] : null;
        
        // Extract thoughts if any
        const thoughtTurns = turns.filter(t => t.classList.contains('thought-activity-host'));
        let thoughtText = "";
        if (thoughtTurns.length > 0) {
            const tClone = thoughtTurns[thoughtTurns.length - 1].cloneNode(true);
            Array.from(tClone.querySelectorAll('button, mat-icon, .actions')).forEach(el => el.remove());
            thoughtText = (tClone.innerText || '').trim();
        }
        
        // Extract answer text from ms-text-chunk or clone
        let fullText = "";
        if (target) {
            const textChunk = target.querySelector('ms-text-chunk');
            if (textChunk) {
                fullText = (textChunk.innerText || '').trim();
            } else {
                const clone = target.cloneNode(true);
                Array.from(clone.querySelectorAll('button, mat-icon, .actions, .actions-container, .thumb-container')).forEach(el => el.remove());
                fullText = (clone.innerText || '').trim();
                fullText = fullText.replace(/^edit\s*more_vert\s*/i, '');
                fullText = fullText.replace(/\s*\d+(\.\d+)?s\s*$/i, '');
            }
        }
        
        // 2. Code Blocks
        const codeBlocks = [];
        if (target) {
            const codeContainers = Array.from(target.querySelectorAll('pre, code-block, .code-container'));
            const seenCode = new Set();
            for (const c of codeContainers) {
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
        
        // 3. Tables
        const tables = [];
        if (target) {
            const tableNodes = Array.from(target.querySelectorAll('table'));
            for (const tbl of tableNodes) {
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
        const tokenMatch = headerText.match(/([0-9,]+\s*tokens?)/i);
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
    },
    
    searchShowcaseApps: async function(query) {
        const input = document.querySelector('input');
        if (input) {
            input.focus();
            input.value = query;
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            await this.sleep(1200);
        }
        const cards = Array.from(document.querySelectorAll('ms-showcase-card, .showcase-card, mat-card, .app-card, [class*="showcase-card"], ms-app-card, .grid > div, .card')).map(c => {
            const lines = (c.innerText || '').split('\n').map(l => l.trim()).filter(Boolean);
            return { title: lines[0] || 'Unknown', tags: lines.slice(1, 4), fullText: c.innerText };
        }).filter(c => c.title !== 'Unknown');
        return { ok: true, query: query, count: cards.length, apps: cards.slice(0, 20) };
    },
    
    remixShowcaseApp: async function(appTitle, newName, newDesc) {
        const cards = Array.from(document.querySelectorAll('ms-showcase-card, .showcase-card, mat-card, .app-card, [class*="showcase-card"], ms-app-card, .grid > div'));
        const targetCard = cards.find(c => (c.innerText || '').toLowerCase().includes((appTitle || '').toLowerCase()));
        if (!targetCard) return { ok: false, error: 'App card not found: ' + appTitle };
        
        const remixBtn = Array.from(targetCard.querySelectorAll('button, a')).find(b => (b.innerText || '').trim() === 'Remix');
        if (!remixBtn) return { ok: false, error: 'Remix button not found on card' };
        remixBtn.click();
        await this.sleep(1000);
        
        const dialog = document.querySelector('mat-dialog-container');
        if (dialog) {
            if (newName) {
                const nameInput = dialog.querySelector('input');
                if (nameInput) {
                    nameInput.focus();
                    nameInput.value = newName;
                    nameInput.dispatchEvent(new Event('input', { bubbles: true }));
                }
            }
            if (newDesc) {
                const descInput = dialog.querySelector('textarea');
                if (descInput) {
                    descInput.focus();
                    descInput.value = newDesc;
                    descInput.dispatchEvent(new Event('input', { bubbles: true }));
                }
            }
            const applyBtn = Array.from(dialog.querySelectorAll('button')).find(b => (b.innerText || '').trim() === 'Apply');
            if (applyBtn) {
                applyBtn.click();
                return { ok: true, message: 'Remix applied successfully' };
            }
        }
        return { ok: true, message: 'Remix initiated' };
    },
    
    dispatchBuildApp: async function(description) {
        const ta = document.querySelector('textarea.prompt-textarea, textarea[placeholder*="Describe an app" i], textarea');
        if (!ta) return { ok: false, error: 'App prompt textarea not found' };
        ta.focus();
        ta.value = description;
        ta.dispatchEvent(new Event('input', { bubbles: true }));
        ta.dispatchEvent(new Event('change', { bubbles: true }));
        await this.sleep(300);
        
        const buildBtn = document.querySelector('button.build-button, button[aria-label*="Send" i]');
        if (buildBtn) {
            buildBtn.classList.remove('button-hidden');
            buildBtn.click();
            return { ok: true, method: 'build_button' };
        }
        ta.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
        return { ok: true, method: 'enter_key' };
    },
    
    getAppBuilderStatus: async function() {
        const isWorking = !!document.querySelector('.working, [aria-label*="Working" i], [aria-label*="Stop" i]') || 
                          (document.body.innerText || '').includes('Running for') ||
                          (document.body.innerText || '').includes('Generating app');
        
        const fileItems = Array.from(document.querySelectorAll('div, span, button, li, .file-tree-item, .file-item')).filter(el => {
            const text = (el.innerText || '').trim();
            return (text.endsWith('.json') || text.endsWith('.html') || text.endsWith('.css') || text.endsWith('.ts') || text.endsWith('.js')) && !text.includes('\n');
        }).map(el => (el.innerText || '').trim());
        
        const titleEl = document.querySelector('.app-title, .title, header h1, header h2') || Array.from(document.querySelectorAll('button, div')).find(b => (b.className || '').includes('title'));
        const appTitle = titleEl ? (titleEl.innerText || '').trim() : 'Untitled';
        
        return {
            is_working: isWorking,
            files: Array.from(new Set(fileItems)),
            app_title: appTitle
        };
    },
    
    exportAppProject: async function(exportType = 'zip') {
        const exportBtn = Array.from(document.querySelectorAll('button')).find(b => 
            (b.innerText || '').toLowerCase().includes('export') || 
            (b.getAttribute('aria-label') || '').toLowerCase().includes('export')
        );
        if (!exportBtn) return { ok: false, error: 'Export button not found' };
        exportBtn.click();
        await this.sleep(600);
        
        const menuItems = Array.from(document.querySelectorAll('.mat-mdc-menu-content button, [role="menuitem"], .cdk-overlay-container button'));
        let targetItem = null;
        const cleanType = (exportType || '').toLowerCase();
        if (cleanType.includes('antigravity')) {
            targetItem = menuItems.find(b => (b.innerText || '').toLowerCase().includes('antigravity'));
        } else if (cleanType.includes('github')) {
            targetItem = menuItems.find(b => (b.innerText || '').toLowerCase().includes('github'));
        } else {
            targetItem = menuItems.find(b => (b.innerText || '').toLowerCase().includes('zip') || (b.innerText || '').toLowerCase().includes('download'));
        }
        if (targetItem) {
            targetItem.click();
            return { ok: true, selected: targetItem.innerText.split('\n')[0].trim() };
        }
        return { ok: false, error: 'Export option not found for ' + exportType, available: menuItems.map(m => m.innerText.split('\n')[0].trim()) };
    }
};
"""


# -----------------------------------------------------------------------------
# Main Driver Execution Logic
# -----------------------------------------------------------------------------

def ensure_extension_ready(preferred_profile: str, target_url: str = "https://aistudio.google.com/prompts/new_chat") -> Dict[str, Any]:
    """Ensures Chrome is running with the extension connected for the specified profile."""
    status = call_bridge_api("/status")
    connected = status.get("connected_extensions", [])

    # Check if preferred profile is connected
    for c in connected:
        if c.get("dir_name") == preferred_profile or c.get("email") == preferred_profile:
            return c

    # Not connected -> Launch Chrome window with extension
    print(f"[AIStudioSubagent] Chrome extension not connected for {preferred_profile}. Launching...")
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


def find_or_open_ai_studio_tab(
    client: Dict[str, Any],
    target_url: str = "https://aistudio.google.com/prompts/new_chat",
    navigate_if_different: bool = True,
) -> Tuple[int, bool]:
    """Single-Tab Invariant: Reuses existing aistudio.google.com tab to preserve low-RAM bounds."""
    profile_dir = client.get("dir_name")
    tabs_res = call_bridge_api("/command", method="POST", payload={"action": "LIST_TABS", "profile": profile_dir})
    tabs = tabs_res.get("tabs", [])

    # Search for open AI Studio tab
    for t in tabs:
        t_url = t.get("url") or ""
        if "aistudio.google.com" in t_url:
            tab_id = t["id"]
            print(f"[AIStudioSubagent] Reusing existing AI Studio tab (tabId: {tab_id}, url: {t_url}) [Single-Tab Invariant]")
            # Bring tab to front
            call_bridge_api("/command", method="POST", payload={"action": "CDP_COMMAND", "profile": profile_dir, "params": {"tabId": tab_id, "method": "Page.bringToFront"}})
            
            # Check if navigation to target surface or model is required
            current_base = t_url.split("?")[0].rstrip("/")
            target_base = target_url.split("?")[0].rstrip("/")
            needs_nav = False
            
            if "/onboarding" in t_url:
                needs_nav = True
            elif navigate_if_different and current_base != target_base:
                needs_nav = True
            elif navigate_if_different and "?model=" in target_url and target_url not in t_url:
                needs_nav = True
                
            if needs_nav:
                print(f"[AIStudioSubagent] Navigating tab to target surface -> {target_url}...")
                call_bridge_api("/command", method="POST", payload={"action": "CDP_COMMAND", "profile": profile_dir, "params": {"tabId": tab_id, "method": "Page.navigate", "params": {"url": target_url}}})
                time.sleep(3.5)
                
            return tab_id, True

    # No AI Studio tab found -> Open exactly ONE tab
    print(f"[AIStudioSubagent] No open AI Studio tab found. Opening single tab -> {target_url}...")
    open_res = call_bridge_api(
        "/command",
        method="POST",
        payload={
            "action": "OPEN_TAB",
            "profile": profile_dir,
            "params": {"url": target_url, "active": True},
        },
    )
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
    preferred_profile: str = "Profile 14",
    model_name: str = "gemini-4-argon",
    system_instructions: Optional[str] = None,
    timeout_sec: int = 300,
    output_file: Optional[str] = None,
    screenshot_path: Optional[str] = None,
    agent_id: str = "aistudio_subagent",
    session_id: Optional[str] = None,
    target_mode: str = "chat",  # chat or freeform
    surface: str = "playground",  # playground, freeform, apps, build, gallery, my_apps, library
    get_code: bool = False,
    get_code_output: Optional[str] = None,
    search_gallery: Optional[str] = None,
    remix_target: Optional[str] = None,
    remix_name: Optional[str] = None,
    remix_desc: Optional[str] = None,
    export_app: Optional[str] = None,
    continue_chat: bool = False,
) -> Dict[str, Any]:
    """Executes queries and workflows across all Google AI Studio platform surfaces."""
    start_time = time.time()
    sid = session_id or f"studio_{int(start_time)}"
    surface_clean = surface.lower().strip()

    if surface_clean in ("apps", "build"):
        target_url = "https://aistudio.google.com/apps"
    elif surface_clean == "gallery":
        target_url = "https://aistudio.google.com/apps?source=showcase"
    elif surface_clean == "my_apps":
        target_url = "https://aistudio.google.com/apps?source=user"
    elif surface_clean == "library":
        target_url = "https://aistudio.google.com/library"
    elif surface_clean == "freeform" or target_mode == "freeform":
        target_url = f"https://aistudio.google.com/prompts/new_freeform?model={model_name}"
    else:
        target_url = f"https://aistudio.google.com/prompts/new_chat?model={model_name}"

    print("\n" + "=" * 80)
    print(" GOOGLE AI STUDIO FULL-PLATFORM ORCHESTRATOR")
    print("=" * 80)
    print(f"Profile Preference : {preferred_profile}")
    print(f"Target Model       : {model_name}")
    print(f"Surface Mode       : {surface_clean} ({target_url})")
    if prompt:
        print(f"Prompt             : {prompt[:70]}...")
    if context_files:
        print(f"Context Files      : {len(context_files)} file(s)")
    if get_code:
        print(f"Get Code Harvest   : Enabled (output: {get_code_output or 'auto'})")
    if search_gallery:
        print(f"Gallery Search     : '{search_gallery}'")
    if remix_target:
        print(f"Gallery Remix      : '{remix_target}'")
    print(f"Timeout            : {timeout_sec}s")
    print("=" * 80 + "\n")

    # 1. Lease Acquisition via Profile Lock Manager
    leased_profile = preferred_profile
    if profile_lock_manager:
        task_desc = f"AI Studio ({surface_clean}:{model_name})"
        if prompt:
            task_desc += f": {prompt[:30]}"
        target_p, err = profile_lock_manager.acquire_profile_lease(
            agent_id=agent_id,
            preferred_profile=preferred_profile,
            task=task_desc,
            session_id=sid,
            lease_seconds=float(timeout_sec + 60),
        )
        if target_p:
            leased_profile = target_p
            print(f"[AIStudioSubagent] Active lease granted on: {leased_profile}")
        else:
            print(f"[AIStudioSubagent] Warning acquiring lease: {err}. Proceeding with: {leased_profile}")

    heartbeat = HeartbeatThread(leased_profile, agent_id=agent_id)
    heartbeat.start()

    try:
        # 2. Ensure Extension is Ready & Connected
        client = ensure_extension_ready(leased_profile, target_url=target_url)
        profile_dir = client.get("dir_name", leased_profile)

        # 3. Single-Tab Invariant: Find or open AI Studio tab & navigate
        tab_id, was_existing = find_or_open_ai_studio_tab(client, target_url=target_url, navigate_if_different=True)
        time.sleep(3.0 if was_existing else 6.0)

        # 4. Inject Helper Library into Tab
        call_bridge_api(
            "/command",
            method="POST",
            payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": AI_STUDIO_HELPERS_JS}},
        )

        # 5. Handle Onboarding, Cookie Banners, & Modals
        call_bridge_api(
            "/command",
            method="POST",
            payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": "window.__agyStudio.handleOnboardingAndModals();"}},
        )
        time.sleep(0.5)

        # ---------------------------------------------------------------------
        # SURFACE: GALLERY
        # ---------------------------------------------------------------------
        if surface_clean == "gallery":
            print("[AIStudioSubagent] Operating on Showcase Gallery surface...")
            gallery_data = {}
            if search_gallery:
                print(f"[AIStudioSubagent] Searching showcase apps for: '{search_gallery}'...")
                res = call_bridge_api(
                    "/command",
                    method="POST",
                    payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": f"window.__agyStudio.searchShowcaseApps({json.dumps(search_gallery)});"}},
                )
                gallery_data["search_results"] = res.get("result", {})
                print(f"[AIStudioSubagent] Discovered {gallery_data['search_results'].get('count', 0)} showcase app(s).")

            if remix_target:
                print(f"[AIStudioSubagent] Remixing showcase app: '{remix_target}'...")
                res = call_bridge_api(
                    "/command",
                    method="POST",
                    payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": f"window.__agyStudio.remixShowcaseApp({json.dumps(remix_target)}, {json.dumps(remix_name)}, {json.dumps(remix_desc)});"}},
                )
                gallery_data["remix_status"] = res.get("result", {})
                print(f"[AIStudioSubagent] Remix status: {gallery_data['remix_status']}")

            if screenshot_path:
                capture_tab_screenshot(client, tab_id, screenshot_path)

            return {
                "ok": True,
                "surface": "gallery",
                "profile": leased_profile,
                "duration_seconds": round(time.time() - start_time, 1),
                "data": gallery_data,
            }

        # ---------------------------------------------------------------------
        # SURFACE: APP BUILDER (BUILD / APPS)
        # ---------------------------------------------------------------------
        if surface_clean in ("apps", "build"):
            print("[AIStudioSubagent] Operating on App Builder (/apps) surface...")
            if not prompt:
                raise ValueError("App Builder mode requires a prompt describing the app to build.")

            print(f"[AIStudioSubagent] Injecting app description prompt: {prompt[:80]}...")
            call_bridge_api(
                "/command",
                method="POST",
                payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": f"window.__agyStudio.dispatchBuildApp({json.dumps(prompt)});"}},
            )
            time.sleep(3.0)

            # Monitor generation stream
            print(f"[AIStudioSubagent] Monitoring app generation loop (timeout: {timeout_sec}s)...")
            poll_start = time.time()
            seen_files = set()
            while time.time() - poll_start < timeout_sec:
                time.sleep(3.0)
                st_res = call_bridge_api(
                    "/command",
                    method="POST",
                    payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": "window.__agyStudio.getAppBuilderStatus();"}},
                )
                st = st_res.get("result") or {}
                files = st.get("files", [])
                is_working = st.get("is_working", False)
                new_files = [f for f in files if f not in seen_files]
                for nf in new_files:
                    seen_files.add(nf)
                    print(f"\n[AIStudioSubagent] [+] Generated File: {nf}")

                elapsed = round(time.time() - poll_start, 1)
                print(f"\r[AIStudioSubagent] [{elapsed}s] App Builder Generating: {is_working} | Total Files: {len(seen_files)}    ", end="", flush=True)

                if not is_working and len(seen_files) > 0 and elapsed > 15.0:
                    print(f"\n[AIStudioSubagent] App generation complete!")
                    break

            if screenshot_path:
                capture_tab_screenshot(client, tab_id, screenshot_path)

            export_result = None
            if export_app:
                print(f"[AIStudioSubagent] Triggering export: {export_app}...")
                exp_res = call_bridge_api(
                    "/command",
                    method="POST",
                    payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": f"window.__agyStudio.exportAppProject({json.dumps(export_app)});"}},
                )
                export_result = exp_res.get("result")
                print(f"[AIStudioSubagent] Export result: {export_result}")

            return {
                "ok": True,
                "surface": "apps",
                "profile": leased_profile,
                "duration_seconds": round(time.time() - start_time, 1),
                "generated_files": list(seen_files),
                "export_result": export_result,
            }

        # ---------------------------------------------------------------------
        # SURFACE: PLAYGROUND & FREEFORM
        # ---------------------------------------------------------------------
        if not continue_chat:
            call_bridge_api(
                "/command",
                method="POST",
                payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": "window.__agyStudio.startFreshChat();"}},
            )
            time.sleep(0.5)

        if screenshot_path:
            capture_tab_screenshot(client, tab_id, screenshot_path)

        # Model selection (if not already locked by URL)
        if model_name:
            call_bridge_api(
                "/command",
                method="POST",
                payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": f"window.__agyStudio.selectModel({json.dumps(model_name)});"}},
            )

        # Inject System Instructions
        if system_instructions:
            print(f"[AIStudioSubagent] Injecting System Instructions ({len(system_instructions)} chars)...")
            call_bridge_api(
                "/command",
                method="POST",
                payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": f"window.__agyStudio.setSystemInstructions({json.dumps(system_instructions)});"}},
            )

        # Bundle Context Files & Synthesize Prompt
        full_prompt = prompt
        est_tokens = int(len(prompt) / 3.8)
        if context_files:
            bundle_text, file_tokens = bundle_context_files(context_files)
            est_tokens += file_tokens
            full_prompt = f"### BUNDLED CONTEXT FILES ({len(context_files)} files, ~{file_tokens} tokens):\n\n{bundle_text}\n\n### TASK INSTRUCTIONS:\n{prompt}"
            print(f"[AIStudioSubagent] Bundled {len(context_files)} context files. Total payload: ~{est_tokens:,} tokens ({len(full_prompt):,} chars).")

        harvested_code = None
        if get_code and not full_prompt:
            # Just harvest code directly without running prompt
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
                print(f"[AIStudioSubagent] <> Get code snippet saved -> {p.as_posix()}")

            return {
                "ok": True,
                "surface": "playground",
                "profile": leased_profile,
                "model": model_name,
                "harvested_code": harvested_code,
                "duration_seconds": round(time.time() - start_time, 1),
            }

        # Inject Prompt into AI Studio Prompt Box
        if full_prompt:
            print("[AIStudioSubagent] Injecting prompt payload into AI Studio editor...")
            call_bridge_api(
                "/command",
                method="POST",
                payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": f"window.__agyStudio.injectPrompt({json.dumps(full_prompt)});"}},
            )

            # Record baseline turns
            pre_status = call_bridge_api(
                "/command",
                method="POST",
                payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": "window.__agyStudio.getGenerationStatus();"}},
            ).get("result") or {}
            baseline_answer_turns = pre_status.get("answer_turns_count", 0)

            # Trigger Run
            print("[AIStudioSubagent] Triggering Run (execution started)...")
            call_bridge_api(
                "/command",
                method="POST",
                payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": "window.__agyStudio.clickRun();"}},
            )
            time.sleep(2.0)

            # Await Stream Completion
            print(f"[AIStudioSubagent] Monitoring generation stream (timeout: {timeout_sec}s)...")
            poll_start = time.time()
            last_length = 0
            stable_count = 0

            while time.time() - poll_start < timeout_sec:
                time.sleep(2.0)
                status_res = call_bridge_api(
                    "/command",
                    method="POST",
                    payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": "window.__agyStudio.getGenerationStatus();"}},
                )
                st_data = status_res.get("result") or {}
                is_gen = st_data.get("is_generating", False)
                cur_len = st_data.get("text_length", 0)
                cur_answer_turns = st_data.get("answer_turns_count", 0)
                has_answer = st_data.get("has_answer", False)
                telemetry = st_data.get("token_telemetry")

                elapsed = round(time.time() - poll_start, 1)
                t_str = f" | Tokens: {telemetry}" if telemetry else ""
                print(f"\r[AIStudioSubagent] [{elapsed}s] Generating: {is_gen} | Answer Chars: {cur_len}{t_str}    ", end="", flush=True)

                turn_active = (cur_answer_turns > baseline_answer_turns and has_answer) or (baseline_answer_turns == 0 and has_answer)
                if turn_active and not is_gen and cur_len > 0:
                    if cur_len == last_length:
                        stable_count += 1
                        if stable_count >= 2:
                            print(f"\n[AIStudioSubagent] Generation complete! Harvesting rich output...")
                            break
                    else:
                        last_length = cur_len
                        stable_count = 0
                else:
                    last_length = cur_len
                    stable_count = 0

            # Rich Harvest
            harvest_res = call_bridge_api(
                "/command",
                method="POST",
                payload={"action": "EVAL_DOM", "profile": profile_dir, "params": {"tabId": tab_id, "code": "window.__agyStudio.harvestRichContent();"}},
            )
            response_data = harvest_res.get("result") or {}
            raw_text = response_data.get("text", "")
            thoughts = response_data.get("thoughts")
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
            output_file = f"<BRAIN_ROOT>\\temp_read\\aistudio_response_{timestamp_slug}.md"

        out_path = Path(output_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        report_content = f"# Google AI Studio Reasoning Output\n\n"
        report_content += f"- **Model**: `{model_name}`\n"
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
            "model": model_name,
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
        if profile_lock_manager:
            profile_lock_manager.release_profile_lease(leased_profile, agent_id=agent_id)
            print(f"[AIStudioSubagent] Lease released on {leased_profile}.")


# -----------------------------------------------------------------------------
# CLI Entry Point
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query Google AI Studio (2M Context & Full Platform) via authentic Chrome bridge.")
    parser.add_argument("prompt", nargs="?", default="", help="Task prompt, query, or app description")
    parser.add_argument("-f", "--files", nargs="*", default=[], help="Context files to bundle (codebase, logs, schemas)")
    parser.add_argument("--profile", default="Profile 14", help="Target Chrome profile directory (default: 'Profile 14')")
    parser.add_argument("--model", default="gemini-4-argon", help="Model to select (e.g. gemini-4-argon, gemini-3.8-flash, gemini-3.5-flash-lite)")
    parser.add_argument("--system", default=None, help="System instructions for the model")
    parser.add_argument("--surface", choices=["playground", "freeform", "apps", "build", "gallery", "my_apps", "library"], default="playground", help="Target AI Studio surface")
    parser.add_argument("--get-code", action="store_true", help="Harvest <> Get code snippet from active Playground")
    parser.add_argument("--get-code-output", default=None, help="File path to save harvested <> Get code snippet")
    parser.add_argument("--search-gallery", default=None, help="Search query to filter showcase apps in the Gallery")
    parser.add_argument("--remix", default=None, help="Title of showcase app to Remix")
    parser.add_argument("--remix-name", default=None, help="New name for remixed app")
    parser.add_argument("--remix-desc", default=None, help="New description for remixed app")
    parser.add_argument("--export-app", choices=["zip", "antigravity", "github"], default=None, help="Export app to .zip, Antigravity, or GitHub")
    parser.add_argument("--timeout", type=int, default=300, help="Max timeout seconds (default: 300)")
    parser.add_argument("-o", "--output", default=None, help="Path to save markdown output")
    parser.add_argument("--screenshot", default=None, help="Save diagnostic screenshot to file")
    parser.add_argument("--session-id", default=None, help="Session identifier for multi-turn tracking")
    parser.add_argument("--continue-chat", action="store_true", help="Continue in existing chat turns instead of starting fresh")

    args = parser.parse_args()

    default_prompt = args.prompt
    if not default_prompt and args.surface == "playground" and not args.get_code:
        default_prompt = "Explain the core architectural advantage of Google AI Studio's 2M token context window."

    try:
        res = ask_ai_studio(
            prompt=default_prompt,
            context_files=args.files,
            preferred_profile=args.profile,
            model_name=args.model,
            system_instructions=args.system,
            timeout_sec=args.timeout,
            output_file=args.output,
            screenshot_path=args.screenshot,
            session_id=args.session_id,
            surface=args.surface,
            get_code=args.get_code,
            get_code_output=args.get_code_output,
            search_gallery=args.search_gallery,
            remix_target=args.remix,
            remix_name=args.remix_name,
            remix_desc=args.remix_desc,
            export_app=args.export_app,
            continue_chat=args.continue_chat,
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
            elif res.get("generated_files"):
                print("Generated Full-Stack Files:")
                for gf in res["generated_files"][:10]:
                    print(f"  - {gf}")
            elif res.get("data", {}).get("search_results"):
                sr = res["data"]["search_results"]
                print(f"Discovered {sr.get('count', 0)} Showcase Apps for '{sr.get('query')}':")
                for app in sr.get("apps", [])[:10]:
                    print(f"  - {app.get('title')}: {' | '.join(app.get('tags', []))}")
            elif res.get("data", {}).get("remix_status"):
                print(f"Remix status: {res['data']['remix_status']}")
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
