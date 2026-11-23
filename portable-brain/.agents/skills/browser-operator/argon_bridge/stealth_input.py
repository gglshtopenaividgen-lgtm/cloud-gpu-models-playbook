#!/usr/bin/env python3
"""stealth_input.py - Anti-Bot & Anti-Captcha Human-Like Input Synthesis Layer.

Provides:
  - Cubic Bézier curve mouse trajectory generation with ease-in-out pacing & micro-jitter.
  - Spatial click target jitter and human-like hold/hesitation durations.
  - Log-normal human typing cadence with word-boundary pauses.
  - Rich response extraction schema for gemini.google.com.
"""

from __future__ import annotations

import math
import random
import time
from typing import Any, Callable, Dict, List, Tuple

# Current persistent cursor position tracker
_CURRENT_CURSOR: Tuple[int, int] = (500, 350)


def get_current_cursor() -> Tuple[int, int]:
    global _CURRENT_CURSOR
    return _CURRENT_CURSOR


def set_current_cursor(x: int, y: int) -> None:
    global _CURRENT_CURSOR
    _CURRENT_CURSOR = (x, y)


def generate_human_curve(
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    deviation_scale: float = 0.25,
) -> List[Tuple[int, int]]:
    """Generates a smooth cubic Bézier trajectory with human-like jitter and ease-in-out velocity."""
    dx = end_x - start_x
    dy = end_y - start_y
    dist = math.hypot(dx, dy)

    if dist < 8:
        return [(end_x, end_y)]

    # Compute randomized control points
    deviation = min(max(dist * deviation_scale, 25.0), 120.0)
    angle_offset = random.uniform(-0.4, 0.4)

    ctrl1_x = start_x + dx * 0.3 + math.sin(angle_offset) * deviation + random.uniform(-10, 10)
    ctrl1_y = start_y + dy * 0.3 + math.cos(angle_offset) * deviation + random.uniform(-10, 10)

    ctrl2_x = start_x + dx * 0.7 - math.sin(angle_offset) * (deviation * 0.7) + random.uniform(-8, 8)
    ctrl2_y = start_y + dy * 0.7 - math.cos(angle_offset) * (deviation * 0.7) + random.uniform(-8, 8)

    # Calculate steps based on distance (4 - 8 intermediate points)
    num_steps = max(int(dist / 90), 4)
    num_steps = min(num_steps, 8)

    points: List[Tuple[int, int]] = []
    for i in range(1, num_steps + 1):
        t = i / num_steps
        # Smoothstep ease-in-out pacing: S(t) = 3t^2 - 2t^3
        t_eased = 3 * (t ** 2) - 2 * (t ** 3)

        u = 1.0 - t_eased
        # Cubic Bézier: (1-t)^3*P0 + 3(1-t)^2*t*P1 + 3(1-t)*t^2*P2 + t^3*P3
        x = (u ** 3) * start_x + 3 * (u ** 2) * t_eased * ctrl1_x + 3 * u * (t_eased ** 2) * ctrl2_x + (t_eased ** 3) * end_x
        y = (u ** 3) * start_y + 3 * (u ** 2) * t_eased * ctrl1_y + 3 * u * (t_eased ** 2) * ctrl2_y + (t_eased ** 3) * end_y

        # Micro-jitter: human hand tremor (0.5 - 1.2px)
        jitter_x = random.gauss(0, 0.6) if i < num_steps else 0.0
        jitter_y = random.gauss(0, 0.6) if i < num_steps else 0.0

        points.append((int(round(x + jitter_x)), int(round(y + jitter_y))))

    return points


def dispatch_stealth_click(
    call_api_fn: Callable[..., Dict[str, Any]],
    tab_id: int,
    target_x: int,
    target_y: int,
    randomize_target: bool = True,
    target_radius: int = 4,
) -> Tuple[int, int]:
    """Dispatches a human-like mouse approach, hover hesitation, hold time, and click release via CDP."""
    # 1. Apply spatial target jitter so clicks don't hit identical pixel coordinates
    if randomize_target:
        final_x = target_x + random.randint(-target_radius, target_radius)
        final_y = target_y + random.randint(-target_radius, target_radius)
    else:
        final_x, final_y = target_x, target_y

    start_x, start_y = get_current_cursor()

    # 2. Traverse natural Bézier curve
    trajectory = generate_human_curve(start_x, start_y, final_x, final_y)
    for px, py in trajectory:
        call_api_fn(
            "/command",
            {
                "action": "CDP_COMMAND",
                "params": {
                    "tabId": tab_id,
                    "method": "Input.dispatchMouseEvent",
                    "params": {"type": "mouseMoved", "x": px, "y": py, "button": "none", "buttons": 0},
                },
            },
        )
        # Dynamic inter-step delay (8ms - 22ms)
        time.sleep(random.uniform(0.009, 0.021))

    set_current_cursor(final_x, final_y)

    # 3. Human hesitation over target before clicking (90ms - 240ms)
    time.sleep(random.uniform(0.09, 0.24))

    # 4. Mouse down with explicit buttons bitmask: 1
    call_api_fn(
        "/command",
        {
            "action": "CDP_COMMAND",
            "params": {
                "tabId": tab_id,
                "method": "Input.dispatchMouseEvent",
                "params": {"type": "mousePressed", "x": final_x, "y": final_y, "button": "left", "buttons": 1, "clickCount": 1},
            },
        },
    )

    # 5. Realistic human button hold duration (50ms - 115ms)
    time.sleep(random.uniform(0.05, 0.115))

    # 6. Mouse release with explicit buttons bitmask: 0
    call_api_fn(
        "/command",
        {
            "action": "CDP_COMMAND",
            "params": {
                "tabId": tab_id,
                "method": "Input.dispatchMouseEvent",
                "params": {"type": "mouseReleased", "x": final_x, "y": final_y, "button": "left", "buttons": 0, "clickCount": 1},
            },
        },
    )

    # 7. Post-click recovery delay (70ms - 160ms)
    time.sleep(random.uniform(0.07, 0.16))
    return final_x, final_y


def dispatch_stealth_type(
    call_api_fn: Callable[..., Dict[str, Any]],
    tab_id: int,
    text: str,
    fast_mode: bool = False,
) -> None:
    """Simulates realistic human typing cadence with word-boundary pauses."""
    if fast_mode:
        # Fast bulk insert for huge code blocks / prompts via CDP Input.insertText
        call_api_fn(
            "/command",
            {
                "action": "CDP_COMMAND",
                "params": {
                    "tabId": tab_id,
                    "method": "Input.insertText",
                    "params": {"text": text},
                },
            },
        )
        time.sleep(random.uniform(0.2, 0.4))
        return

    # Character-by-character typing for short queries / inputs
    for i, char in enumerate(text):
        call_api_fn(
            "/command",
            {
                "action": "CDP_COMMAND",
                "params": {
                    "tabId": tab_id,
                    "method": "Input.dispatchKeyEvent",
                    "params": {"type": "keyDown", "text": char},
                },
            },
        )
        call_api_fn(
            "/command",
            {
                "action": "CDP_COMMAND",
                "params": {
                    "tabId": tab_id,
                    "method": "Input.dispatchKeyEvent",
                    "params": {"type": "keyUp"},
                },
            },
        )

        # Log-normal cadence: ~55ms mean, micro-pauses at spaces/punctuation
        if char in " .,?!;:\n":
            time.sleep(random.uniform(0.12, 0.28))
        else:
            time.sleep(max(0.025, random.gauss(0.055, 0.02)))


# Complete JavaScript parser for extracting full structured rich content from Gemini
RICH_HARVEST_JS = r"""
return (function() {
    const immersive = document.querySelector('deep-research-immersive-panel, immersive-panel, [data-test-id*="immersive"], .deep-research-report');
    const responses = Array.from(document.querySelectorAll('model-response'));
    if (!responses.length && !immersive) return { ok: false, error: 'No model response found in DOM' };

    const lastResp = responses.length ? responses[responses.length - 1] : null;
    let target = lastResp;
    if (immersive && (immersive.innerText || '').trim().length > ((lastResp ? lastResp.innerText : '') || '').trim().length) {
        target = immersive;
    }
    const taskStepsNode = target.querySelector('spark-thinking-steps');
    const taskStepsText = taskStepsNode ? (taskStepsNode.innerText || '').trim() : '';
    const explicitContent = target.querySelector('message-content, .model-response-text, .markdown, .response-content');
    const contentRoot = explicitContent || target;

    // 1. Full Formatted Text (preserving headings, lists, tables, code blocks)
    let rawBody = (contentRoot.innerText || '').trim();
    if (taskStepsNode) {
        if (/\bgemini said\b/i.test(rawBody)) {
            rawBody = rawBody.replace(/^[\s\S]*?\bGemini said\s*/i, '').trim();
        } else if (taskStepsText && rawBody.startsWith(taskStepsText)) {
            rawBody = rawBody.slice(taskStepsText.length).trim();
        }
    }
    let fullText = rawBody.replace(/^(?:Analyzing\s*|Show code\s*|Gemini said\s*)+/i, '').trim();
    if (!fullText || fullText.toLowerCase() === 'show code' || fullText.toLowerCase() === 'analyzing') {
        const codeResult = target.querySelector('.code-result-container, code-block, pre');
        if (codeResult && (codeResult.textContent || '').trim()) {
            fullText = (codeResult.textContent || '').trim();
        } else {
            let fallbackText = (target.textContent || '').trim();
            if (taskStepsNode && /\bgemini said\b/i.test(fallbackText)) {
                fallbackText = fallbackText.replace(/^[\s\S]*?\bGemini said\s*/i, '').trim();
            }
            fullText = fallbackText.replace(/^(?:Analyzing\s*|Show code\s*|Gemini said\s*)+/i, '').trim();
        }
    }
    
    // 2. Tables (Parsed to Markdown & 2D JSON)
    const tables = [];
    const tableNodes = Array.from(target.querySelectorAll('table'));
    for (const tbl of tableNodes) {
        const headers = Array.from(tbl.querySelectorAll('th')).map(th => th.innerText.trim());
        const rows = [];
        const trNodes = Array.from(tbl.querySelectorAll('tbody tr, tr')).filter(tr => tr.querySelectorAll('td').length > 0);
        for (const tr of trNodes) {
            const cells = Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim());
            rows.push(cells);
        }
        
        let mdTable = "";
        if (headers.length > 0) {
            mdTable += "| " + headers.join(" | ") + " |\n";
            mdTable += "| " + headers.map(() => "---").join(" | ") + " |\n";
        }
        for (const r of rows) {
            mdTable += "| " + r.join(" | ") + " |\n";
        }
        
        tables.push({
            headers: headers,
            rows: rows,
            markdown: mdTable
        });
    }
    
    // 3. Code Blocks (With Language Header & Raw Text)
    const codeBlocks = [];
    const codeContainers = Array.from(target.querySelectorAll('code-block, pre'));
    const seenCode = new Set();
    for (const container of codeContainers) {
        const codeEl = container.tagName.toLowerCase() === 'pre' ? (container.querySelector('code') || container) : (container.querySelector('code, pre') || container);
        const codeText = (codeEl.innerText || '').trim();
        if (!codeText || seenCode.has(codeText)) continue;
        seenCode.add(codeText);
        
        let lang = "";
        const langEl = container.querySelector('.code-block-decoration, .header-text, .code-header, [class*="language-"]');
        if (langEl) {
            lang = langEl.innerText || '';
            if (!lang) {
                const match = (langEl.className || '').match(/language-([a-zA-Z0-9_-]+)/);
                if (match) lang = match[1];
            }
        }
        codeBlocks.push({
            language: (lang || "code").trim(),
            code: codeText
        });
    }
    
    // 4. Images & Visual Assets
    const images = [];
    const imgNodes = Array.from(target.querySelectorAll('img')).filter(img => img.offsetWidth > 40 && img.offsetHeight > 40);
    for (const img of imgNodes) {
        images.push({
            src: img.src,
            alt: img.alt || '',
            width: img.naturalWidth || img.offsetWidth,
            height: img.naturalHeight || img.offsetHeight
        });
    }
    
    // 5. Canvas Visuals (to base64 dataURL)
    const canvases = [];
    const canvasNodes = Array.from(target.querySelectorAll('canvas')).filter(cv => cv.offsetWidth > 20 && cv.offsetHeight > 20);
    for (let i = 0; i < canvasNodes.length; i++) {
        try {
            canvases.push({
                index: i,
                dataUrl: canvasNodes[i].toDataURL('image/png'),
                width: canvasNodes[i].width,
                height: canvasNodes[i].height
            });
        } catch (e) {
            canvases.push({ index: i, error: e.message });
        }
    }
    
    // 6. Citations & Grounding Sources
    const sources = [];
    const searchRoot = immersive || target;
    const sourceLinks = Array.from(searchRoot.querySelectorAll('a[href^="http"], [data-test-id*="grounding"], .citation, .source-chip'));
    for (const a of sourceLinks) {
        const href = a.getAttribute('href') || a.getAttribute('data-url') || '';
        const title = (a.innerText || a.getAttribute('title') || a.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ');
        if (href && !href.includes('google.com/preferences') && !sources.some(s => s.url === href)) {
            sources.push({ title: title || href, url: href });
        }
    }

    let markdownOut = fullText;
    if (sources.length > 0 && !markdownOut.includes('## Grounded Sources')) {
        markdownOut += '\n\n---\n## Grounded Sources & Citations\n' +
            sources.map((s, idx) => `${idx + 1}. [${s.title}](${s.url})`).join('\n');
    }
    
    return {
        ok: true,
        text: fullText,
        markdown: markdownOut,
        task_steps: taskStepsText,
        tables_count: tables.length,
        tables: tables,
        code_blocks_count: codeBlocks.length,
        code_blocks: codeBlocks,
        images_count: images.length,
        images: images,
        canvases_count: canvases.length,
        canvases: canvases,
        sources_count: sources.length,
        sources: sources
    };
})();
"""
