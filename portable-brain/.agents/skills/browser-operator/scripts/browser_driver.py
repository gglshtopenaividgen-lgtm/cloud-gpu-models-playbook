#!/usr/bin/env python3
"""
Standalone Resilient Stealth Browser Agent Driver
Part of browser-operator universal skill.
Synthesizes browser-use and Stagehand architectures with zero third-party SaaS dependencies.
Features:
  1. Full anti-bot evasion: navigator.webdriver removal, window.chrome mock, WebGL RTX 4070 spoof, plugin array emulation.
  2. DOM tree distillation into concise sequential numeric IDs [1], [2], [3] (95%+ token reduction).
  3. Resilient DOM stability detection using MutationObserver quiescence + requestAnimationFrame layout ticks.
  4. Dual-path action execution: Playwright locator click with spatial center coordinate fallback.
  5. High-contrast visual [ID] badges overlay for multimodal screenshot verification.
"""

import argparse
import asyncio
import json
import os
import sys
from typing import Dict, List, Any, Optional, Tuple

try:
    from playwright.async_api import (
        async_playwright,
        Playwright,
        Browser,
        BrowserContext,
        Page,
        TimeoutError as PlaywrightTimeoutError
    )
except ImportError:
    print("[!] Playwright is not installed. Run: pip install playwright && playwright install chromium", file=sys.stderr)
    sys.exit(1)

# ==============================================================================
# 1. STEALTH EVASION SCRIPT (Injected into every frame before page scripts execute)
# ==============================================================================
STEALTH_EVASION_JS = """
(() => {
    // 1. Purge navigator.webdriver
    delete Object.getPrototypeOf(navigator).webdriver;
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
        configurable: true
    });

    // 2. Emulate realistic window.chrome runtime
    window.chrome = {
        app: {
            isInstalled: false,
            InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
            RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' }
        },
        runtime: {
            OnInstalledReason: { CHROME_UPDATE: 'chrome_update', INSTALL: 'install', UPDATE: 'update' },
            PlatformArch: { X86_64: 'x86-64', ARM64: 'arm64' },
            PlatformOs: { WIN: 'win', MAC: 'mac', LINUX: 'linux' },
            connect: function() {},
            sendMessage: function() {}
        },
        csi: function() {},
        loadTimes: function() {}
    };

    // 3. Normalize Permissions query
    const origPermissionsQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            origPermissionsQuery(parameters)
    );

    // 4. Spoof WebGL Vendor & Renderer (NVIDIA RTX 4070 Desktop GPU profile)
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(param) {
        if (param === 0x9245) return 'Google Inc. (NVIDIA)'; // UNMASKED_VENDOR_WEBGL
        if (param === 0x9246) return 'ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 Direct3D11 vs_5_0 ps_5_0, D3D11)'; // UNMASKED_RENDERER_WEBGL
        return getParameter.apply(this, arguments);
    };

    // 5. Spoof standard desktop plugins
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            const plugins = [
                { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
                { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
            ];
            plugins.item = (i) => plugins[i];
            plugins.namedItem = (name) => plugins.find(p => p.name === name);
            plugins.refresh = () => {};
            return plugins;
        }
    });
})();
"""

# ==============================================================================
# 2. DOM DISTILLATION & NUMERIC INDEXING ENGINE (JavaScript)
# ==============================================================================
DOM_DISTILLATION_JS = """
(() => {
    const isVisible = (el) => {
        if (!el.isConnected) return false;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) return false;
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    };

    const interactiveSelectors = [
        'a[href]', 'button', 'input', 'textarea', 'select', 'details', 'summary',
        '[role="button"]', '[role="link"]', '[role="tab"]', '[role="checkbox"]',
        '[role="radio"]', '[role="menuitem"]', '[role="combobox"]', '[role="switch"]',
        '[onclick]', '[tabindex]:not([tabindex="-1"])'
    ];

    const elements = Array.from(document.querySelectorAll(interactiveSelectors.join(',')))
        .filter(isVisible);

    const indexedItems = [];
    let counter = 1;

    for (const el of elements) {
        const tag = el.tagName.toLowerCase();
        const role = el.getAttribute('role') || tag;
        const type = el.getAttribute('type') || '';
        const rect = el.getBoundingClientRect();

        // Extract primary semantic label
        let text = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ');
        if (!text && el.getAttribute('aria-label')) {
            text = el.getAttribute('aria-label').trim();
        }
        if (!text && el.getAttribute('placeholder')) {
            text = `placeholder: "${el.getAttribute('placeholder').trim()}"`;
        }
        if (!text && el.getAttribute('title')) {
            text = el.getAttribute('title').trim();
        }
        if (!text && el.getAttribute('name')) {
            text = `name: ${el.getAttribute('name').trim()}`;
        }
        if (!text && el.getAttribute('value')) {
            text = `val: ${el.getAttribute('value').trim()}`;
        }

        // Current input state
        let value = '';
        if (['input', 'textarea', 'select'].includes(tag)) {
            value = el.value || '';
        }

        // Mark DOM element with index attribute for fast target resolution
        el.setAttribute('data-agent-id', counter.toString());

        indexedItems.push({
            id: counter,
            tag: tag,
            role: role,
            type: type,
            text: text.substring(0, 100),
            value: value.substring(0, 60),
            href: (tag === 'a' && el.getAttribute('href') && !el.getAttribute('href').startsWith('javascript:')) 
                ? el.getAttribute('href').substring(0, 80) : '',
            bbox: {
                x: Math.round(rect.x),
                y: Math.round(rect.y),
                width: Math.round(rect.width),
                height: Math.round(rect.height),
                cx: Math.round(rect.x + rect.width / 2),
                cy: Math.round(rect.y + rect.height / 2)
            }
        });
        counter++;
    }

    return {
        title: document.title,
        url: window.location.href,
        elements: indexedItems
    };
})()
"""

# ==============================================================================
# 3. DOM STABILITY ENGINE (MutationObserver + Layout Quiescence)
# ==============================================================================
DOM_STABILITY_JS = """
async ({ quietMs, timeoutMs }) => {
    return new Promise((resolve) => {
        let debounceTimer = null;
        let timeoutTimer = null;
        let observer = null;

        const cleanupAndFinish = () => {
            if (observer) observer.disconnect();
            if (debounceTimer) clearTimeout(debounceTimer);
            if (timeoutTimer) clearTimeout(timeoutTimer);
            // Ensure 2 layout ticks complete before returning
            window.requestAnimationFrame(() => {
                window.requestAnimationFrame(() => {
                    resolve({ status: "stable" });
                });
            });
        };

        observer = new MutationObserver(() => {
            if (debounceTimer) clearTimeout(debounceTimer);
            debounceTimer = setTimeout(cleanupAndFinish, quietMs);
        });

        observer.observe(document.body || document.documentElement, {
            childList: true,
            subtree: true,
            attributes: true,
            characterData: true
        });

        // Initial debounce trigger (resolves if DOM is already static)
        debounceTimer = setTimeout(cleanupAndFinish, quietMs);

        // Global safety fallback
        timeoutTimer = setTimeout(() => {
            if (observer) observer.disconnect();
            resolve({ status: "timeout_fallback" });
        }, timeoutMs);
    });
}
"""

# ==============================================================================
# 4. STANDALONE BROWSER AGENT DRIVER CLASS
# ==============================================================================
class BrowserAgentDriver:
    """
    Lightweight, resilient Playwright browser agent driver.
    Provides DOM numeric indexing, stealth evasion, coordinate mapping, and stable actions.
    """

    def __init__(self, headed: bool = False, viewport: Tuple[int, int] = (1366, 768)):
        self.headed = headed
        self.viewport_width, self.viewport_height = viewport
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.element_cache: Dict[int, Dict[str, Any]] = {}

    async def start(self) -> None:
        """Launches stealth Chromium browser and initializes page context."""
        self.playwright = await async_playwright().start()

        # Stealth launch arguments
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--disable-extensions",
            f"--window-size={self.viewport_width},{self.viewport_height}"
        ]

        self.browser = await self.playwright.chromium.launch(
            headless=not self.headed,
            args=launch_args,
            ignore_default_args=["--enable-automation"]
        )

        self.context = await self.browser.new_context(
            viewport={"width": self.viewport_width, "height": self.viewport_height},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="America/New_York",
            has_touch=False
        )

        # Inject stealth evasions before any page script executes
        await self.context.add_init_script(STEALTH_EVASION_JS)
        self.page = await self.context.new_page()

    async def wait_for_dom_stable(self, quiet_ms: int = 350, timeout_ms: int = 5000) -> None:
        """Waits until DOM mutations settle for quiet_ms milliseconds."""
        if not self.page:
            return
        try:
            await self.page.evaluate(DOM_STABILITY_JS, {"quietMs": quiet_ms, "timeoutMs": timeout_ms})
        except Exception:
            # Fallback if page is reloading
            await asyncio.sleep(0.3)

    async def navigate(self, url: str, timeout: int = 30000) -> Dict[str, Any]:
        """Navigates to URL, waits for domcontentloaded, and stabilizes the DOM."""
        if not self.page:
            raise RuntimeError("Driver not started. Call await start() first.")

        await self.page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        await self.wait_for_dom_stable()
        return await self.extract_state()

    async def extract_state(self) -> Dict[str, Any]:
        """Runs DOM distillation, populates numeric index cache, and generates concise state."""
        if not self.page:
            raise RuntimeError("Page is not initialized.")

        data = await self.page.evaluate(DOM_DISTILLATION_JS)
        elements = data.get("elements", [])

        # Update internal element coordinate cache
        self.element_cache = {el["id"]: el for el in elements}

        # Format concise text representation for LLM prompt
        prompt_lines = [
            f"PAGE TITLE: {data.get('title')}",
            f"URL: {data.get('url')}",
            "INTERACTIVE ELEMENTS (Select target by numeric ID [x]):"
        ]

        for el in elements:
            e_id = f"[{el['id']}]"
            tag_role = f"{el['role']}" + (f"({el['type']})" if el['type'] else "")
            text = el['text']
            extra = []
            if el['value']:
                extra.append(f'val: "{el["value"]}"')
            if el['href']:
                extra.append(f'href: "{el["href"]}"')
            extra_str = f" [{' | '.join(extra)}]" if extra else ""
            coords = f" @({el['bbox']['cx']}, {el['bbox']['cy']})"

            prompt_lines.append(f"{e_id.ljust(5)} {tag_role.ljust(12)} {text}{extra_str}{coords}")

        return {
            "title": data.get("title"),
            "url": data.get("url"),
            "element_count": len(elements),
            "state_prompt": "\n".join(prompt_lines),
            "elements": elements
        }

    async def click_id(self, target_id: int, retry_count: int = 2) -> bool:
        """
        Resilient click on element by numeric ID.
        Attempts locator click, then falls back to center spatial coordinate dispatch.
        """
        if not self.page:
            raise RuntimeError("Page not initialized.")

        selector = f'[data-agent-id="{target_id}"]'

        for attempt in range(retry_count + 1):
            try:
                locator = self.page.locator(selector)
                if await locator.count() > 0:
                    await locator.scroll_into_view_if_needed(timeout=2000)
                    await locator.click(timeout=3000)
                    await self.wait_for_dom_stable()
                    return True
            except Exception:
                pass

            # Coordinate Fallback: Use spatial center coordinates from cache
            cached = self.element_cache.get(target_id)
            if cached and "bbox" in cached:
                try:
                    cx = cached["bbox"]["cx"]
                    cy = cached["bbox"]["cy"]
                    await self.page.mouse.click(cx, cy)
                    await self.wait_for_dom_stable()
                    return True
                except Exception:
                    pass

            # If detached, re-extract state and retry
            if attempt < retry_count:
                await self.extract_state()
                await asyncio.sleep(0.3)

        return False

    async def type_id(self, target_id: int, text: str, clear: bool = True, press_enter: bool = False) -> bool:
        """Fills input by numeric ID with simulated human keyboard events."""
        if not self.page:
            raise RuntimeError("Page not initialized.")

        selector = f'[data-agent-id="{target_id}"]'
        try:
            locator = self.page.locator(selector)
            await locator.scroll_into_view_if_needed(timeout=2000)
            await locator.click()

            if clear:
                # Select all and delete to properly trigger reactive framework inputs
                await self.page.keyboard.press("Control+A")
                await self.page.keyboard.press("Backspace")

            await self.page.keyboard.type(text, delay=25)

            if press_enter:
                await self.page.keyboard.press("Enter")

            await self.wait_for_dom_stable()
            return True
        except Exception:
            return False

    async def select_id(self, target_id: int, value: str) -> bool:
        """Selects an option in a <select> element by value or label."""
        if not self.page:
            raise RuntimeError("Page not initialized.")
        selector = f'[data-agent-id="{target_id}"]'
        try:
            locator = self.page.locator(selector)
            await locator.scroll_into_view_if_needed(timeout=2000)
            try:
                await locator.select_option(value=value, timeout=3000)
            except Exception:
                await locator.select_option(label=value, timeout=3000)
            await self.wait_for_dom_stable()
            return True
        except Exception:
            return False

    async def hover_id(self, target_id: int) -> bool:
        """Hovers mouse pointer over element by numeric ID."""
        if not self.page:
            raise RuntimeError("Page not initialized.")
        selector = f'[data-agent-id="{target_id}"]'
        try:
            locator = self.page.locator(selector)
            await locator.scroll_into_view_if_needed(timeout=2000)
            await locator.hover(timeout=3000)
            await self.wait_for_dom_stable()
            return True
        except Exception:
            return False

    async def extract_content(self) -> Dict[str, Any]:
        """Extracts clean readable text, tables, and links from the page."""
        if not self.page:
            raise RuntimeError("Page is not initialized.")
        js = """
        (() => {
            const tables = Array.from(document.querySelectorAll('table')).map((tbl, idx) => {
                const headers = Array.from(tbl.querySelectorAll('th')).map(th => (th.innerText || '').trim());
                const rows = Array.from(tbl.querySelectorAll('tr'))
                    .filter(tr => !tr.querySelector('th'))
                    .map(tr => Array.from(tr.querySelectorAll('td')).map(td => (td.innerText || '').trim()))
                    .filter(r => r.some(Boolean));
                return { table_id: `tbl_${idx}`, headers, rows: rows.slice(0, 60) };
            });
            const links = Array.from(document.querySelectorAll('a[href]'))
                .filter(a => a.offsetWidth > 0 && !a.getAttribute('href').startsWith('javascript:'))
                .slice(0, 100)
                .map(a => ({ text: (a.innerText || a.getAttribute('aria-label') || '').trim(), href: a.href }));
            const clone = document.body.cloneNode(true);
            clone.querySelectorAll('script, style, svg, noscript').forEach(n => n.remove());
            const text = (clone.innerText || '').split('\\n').map(l => l.trim()).filter(Boolean).slice(0, 200).join('\\n');
            return { title: document.title, url: window.location.href, tables, links, markdown_content: text };
        })()
        """
        return await self.page.evaluate(js)

    async def press_key(self, key_combination: str) -> None:
        """Dispatches key combos e.g. 'Enter', 'Escape', 'Control+Shift+R'."""
        if not self.page:
            return
        await self.page.keyboard.press(key_combination)
        await self.wait_for_dom_stable()

    async def scroll(self, direction: str = "down", amount: int = 500) -> None:
        """Scrolls the active window viewport."""
        if not self.page:
            return
        delta = amount if direction == "down" else -amount
        await self.page.evaluate(f"window.scrollBy({{ top: {delta}, behavior: 'smooth' }});")
        await asyncio.sleep(0.3)
        await self.wait_for_dom_stable()

    async def capture_screenshot(self, output_path: str, overlay_badges: bool = False) -> str:
        """
        Captures screenshot. If overlay_badges=True, injects visual [ID] badges
        over elements before capturing, then cleans them up immediately.
        """
        if not self.page:
            raise RuntimeError("Page not initialized.")

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        if overlay_badges:
            # Inject floating high-contrast badges
            overlay_js = """
            (() => {
                const overlay = document.createElement('div');
                overlay.id = '__agent_badge_overlay';
                overlay.style.position = 'fixed';
                overlay.style.top = '0';
                overlay.style.left = '0';
                overlay.style.width = '100vw';
                overlay.style.height = '100vh';
                overlay.style.pointerEvents = 'none';
                overlay.style.zIndex = '2147483647';
                document.body.appendChild(overlay);

                document.querySelectorAll('[data-agent-id]').forEach(el => {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        const badge = document.createElement('div');
                        badge.innerText = el.getAttribute('data-agent-id');
                        badge.style.position = 'absolute';
                        badge.style.left = `${rect.left}px`;
                        badge.style.top = `${rect.top}px`;
                        badge.style.backgroundColor = '#facc15';
                        badge.style.color = '#000000';
                        badge.style.fontSize = '10px';
                        badge.style.fontWeight = 'bold';
                        badge.style.padding = '1px 3px';
                        badge.style.borderRadius = '3px';
                        badge.style.border = '1px solid #000000';
                        badge.style.boxShadow = '0 1px 3px rgba(0,0,0,0.4)';
                        overlay.appendChild(badge);
                    }
                });
            })()
            """
            await self.page.evaluate(overlay_js)

        await self.page.screenshot(path=output_path, full_page=False)

        if overlay_badges:
            # Remove badge overlay from live DOM
            await self.page.evaluate("document.getElementById('__agent_badge_overlay')?.remove()")

        return output_path

    async def close(self) -> None:
        """Gracefully closes browser context and terminates Playwright instance."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()


# ==============================================================================
# 5. CLI ENTRYPOINT
# ==============================================================================
async def async_main():
    parser = argparse.ArgumentParser(description="Standalone Resilient Stealth Browser Agent Driver")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Inspect command
    p_inspect = subparsers.add_parser("inspect", help="Navigate to URL and output concise numeric element index")
    p_inspect.add_argument("url", help="Target URL")
    p_inspect.add_argument("--headed", action="store_true", help="Launch visible browser")
    p_inspect.add_argument("--screenshot", default=None, help="Save screenshot path")
    p_inspect.add_argument("--badges", action="store_true", help="Draw ID badges on screenshot")
    p_inspect.add_argument("--json", action="store_true", help="Output raw JSON instead of text table")

    # Read command
    p_read = subparsers.add_parser("read", help="Extract clean text, tables, and links from URL")
    p_read.add_argument("url", help="Target URL")
    p_read.add_argument("--headed", action="store_true", help="Launch visible browser")
    p_read.add_argument("--json", action="store_true", help="Output JSON")

    # Run command
    p_run = subparsers.add_parser("run", help="Execute sequence of atomic actions")
    p_run.add_argument("url", help="Target URL")
    p_run.add_argument("--actions", required=True, help="JSON list of actions e.g. '[{\"action\":\"type\",\"id\":1,\"val\":\"hello\"},{\"action\":\"click\",\"id\":2}]'")
    p_run.add_argument("--headed", action="store_true", help="Launch visible browser")
    p_run.add_argument("--screenshot", default=None, help="Save final screenshot path")

    args = parser.parse_args()
    driver = BrowserAgentDriver(headed=args.headed)

    try:
        await driver.start()

        if args.command == "inspect":
            state = await driver.navigate(args.url)
            if args.screenshot:
                await driver.capture_screenshot(args.screenshot, overlay_badges=args.badges)
                print(f"[+] Screenshot captured: {args.screenshot}")

            if args.json:
                print(json.dumps(state, indent=2))
            else:
                print(state["state_prompt"])
                print(f"\nTotal interactive elements: {state['element_count']}")

        elif args.command == "read":
            await driver.navigate(args.url)
            content = await driver.extract_content()
            if args.json:
                print(json.dumps(content, indent=2))
            else:
                print(f"# {content.get('title')}\nURL: {content.get('url')}\n\n{content.get('markdown_content')}")

        elif args.command == "run":
            state = await driver.navigate(args.url)
            try:
                action_list = json.loads(args.actions)
            except Exception as e:
                print(f"Error parsing --actions JSON: {e}", file=sys.stderr)
                sys.exit(1)

            results = []
            for act in action_list:
                a_type = act.get("action")
                target_id = act.get("id") or act.get("target_id")
                val = act.get("val") or act.get("value", "")

                if a_type == "click":
                    ok = await driver.click_id(int(target_id))
                    results.append({"action": "click", "id": target_id, "success": ok})
                elif a_type == "hover":
                    ok = await driver.hover_id(int(target_id))
                    results.append({"action": "hover", "id": target_id, "success": ok})
                elif a_type == "type":
                    press_enter = act.get("enter", False)
                    ok = await driver.type_id(int(target_id), str(val), press_enter=press_enter)
                    results.append({"action": "type", "id": target_id, "success": ok})
                elif a_type == "select":
                    ok = await driver.select_id(int(target_id), str(val))
                    results.append({"action": "select", "id": target_id, "success": ok})
                elif a_type == "press":
                    await driver.press_key(str(val))
                    results.append({"action": "press", "key": val, "success": True})
                elif a_type == "scroll":
                    direction = act.get("direction", "down")
                    amount = act.get("amount", 500)
                    await driver.scroll(direction=direction, amount=amount)
                    results.append({"action": "scroll", "direction": direction, "success": True})
                elif a_type == "wait":
                    await asyncio.sleep(float(act.get("seconds", 1.0)))
                    await driver.wait_for_dom_stable()
                    results.append({"action": "wait", "success": True})
                elif a_type == "read":
                    content = await driver.extract_content()
                    results.append({"action": "read", "success": True, "data": content})

            if args.screenshot:
                await driver.capture_screenshot(args.screenshot)
                print(f"[+] Final screenshot captured: {args.screenshot}")

            print(json.dumps(results, indent=2))

    finally:
        await driver.close()


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
