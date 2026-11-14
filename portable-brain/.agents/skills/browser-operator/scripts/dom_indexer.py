#!/usr/bin/env python3
"""
Jev-Style Sub-Second DOM Element Indexer & Browser Action Operator
Part of the browser-operator universal skill.
Runs locally via Playwright Chromium.
Indexes interactive elements into concise numbered IDs [1], [2], [3]
and executes atomic browser actions without passing expensive visual screenshot tokens to LLMs.
"""

import argparse
import asyncio
import json
import os
import sys
from typing import Dict, List, Any, Optional
from playwright.async_api import async_playwright, Page, ElementHandle, TimeoutError as PlaywrightTimeoutError

DOM_INDEX_JS = """
(() => {
    const isVisible = (el) => {
        if (!el.isConnected) return false;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    };

    const interactiveSelectors = [
        'a[href]', 'button', 'input', 'textarea', 'select',
        '[role="button"]', '[role="link"]', '[role="tab"]',
        '[role="checkbox"]', '[role="radio"]', '[role="menuitem"]',
        '[onclick]', '[tabindex]:not([tabindex="-1"])'
    ];

    const elements = Array.from(document.querySelectorAll(interactiveSelectors.join(',')))
        .filter(isVisible);

    const indexed = [];
    let idCounter = 1;

    for (const el of elements) {
        // Tag and role
        const tag = el.tagName.toLowerCase();
        const role = el.getAttribute('role') || tag;
        const inputType = el.getAttribute('type') || '';

        // Text or label
        let text = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ');
        if (!text && el.getAttribute('aria-label')) {
            text = el.getAttribute('aria-label').trim();
        }
        if (!text && el.getAttribute('placeholder')) {
            text = 'placeholder: ' + el.getAttribute('placeholder').trim();
        }
        if (!text && el.getAttribute('title')) {
            text = el.getAttribute('title').trim();
        }
        if (!text && el.getAttribute('name')) {
            text = 'name: ' + el.getAttribute('name').trim();
        }
        if (!text && el.getAttribute('value')) {
            text = 'val: ' + el.getAttribute('value').trim();
        }

        // Value for inputs
        let val = '';
        if (tag === 'input' || tag === 'textarea' || tag === 'select') {
            val = el.value || '';
        }

        let desc = text ? text.substring(0, 80) : '';
        let extra = '';
        if (inputType) extra += ` (${inputType})`;
        if (val) extra += ` [value: "${val.substring(0, 40)}"]`;
        if (tag === 'a' && el.getAttribute('href')) {
            const href = el.getAttribute('href');
            if (!href.startsWith('javascript:')) extra += ` [href: ${href.substring(0, 60)}]`;
        }

        // Mark DOM element with index attribute for fast execution targeting
        el.setAttribute('data-agy-index', idCounter.toString());

        indexed.push({
            id: idCounter,
            tag: tag,
            role: role,
            description: desc,
            extra: extra
        });
        idCounter++;
    }

    return indexed;
})()
"""

async def inspect_page(url: str, headed: bool = False, delay: float = 1.5, timeout: int = 20000) -> List[Dict[str, Any]]:
    """Opens page, runs DOM distillation, and returns indexed interactive element table."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=not headed,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            if delay > 0:
                await asyncio.sleep(delay)

            title = await page.title()
            indexed = await page.evaluate(DOM_INDEX_JS)
            return {"title": title, "url": url, "elements": indexed}
        finally:
            await browser.close()

async def execute_action_sequence(
    url: str,
    actions: List[Dict[str, Any]],
    headed: bool = False,
    delay: float = 1.0,
    screenshot_path: Optional[str] = None
) -> Dict[str, Any]:
    """Navigates to URL and executes a sequential chain of atomic actions by element ID."""
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=not headed,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            if delay > 0:
                await asyncio.sleep(delay)

            # Re-index
            await page.evaluate(DOM_INDEX_JS)

            for idx, act in enumerate(actions, 1):
                act_type = act.get("action")
                elem_id = act.get("target_id")
                value = act.get("value", "")

                selector = f'[data-agy-index="{elem_id}"]'
                try:
                    el = await page.wait_for_selector(selector, timeout=5000)
                    if not el:
                        results.append({"step": idx, "action": act_type, "id": elem_id, "success": False, "error": "Element not found"})
                        continue

                    if act_type == "click":
                        await el.click()
                        await asyncio.sleep(0.8)
                    elif act_type == "type":
                        await el.fill(value)
                        await asyncio.sleep(0.3)
                    elif act_type == "press":
                        await page.keyboard.press(value or "Enter")
                        await asyncio.sleep(0.8)
                    elif act_type == "select":
                        await el.select_option(value)
                        await asyncio.sleep(0.5)
                    elif act_type == "scroll":
                        await page.evaluate(f"window.scrollBy(0, {int(value or 500)})")
                        await asyncio.sleep(0.5)

                    # Re-run DOM indexing after state changes
                    await page.evaluate(DOM_INDEX_JS)
                    results.append({"step": idx, "action": act_type, "id": elem_id, "success": True})
                except Exception as e:
                    results.append({"step": idx, "action": act_type, "id": elem_id, "success": False, "error": str(e)})

            if screenshot_path:
                os.makedirs(os.path.dirname(os.path.abspath(screenshot_path)), exist_ok=True)
                await page.screenshot(path=screenshot_path, full_page=True)

            final_title = await page.title()
            final_url = page.url
            return {
                "initial_url": url,
                "final_url": final_url,
                "final_title": final_title,
                "steps": results,
                "screenshot": screenshot_path
            }
        finally:
            await browser.close()

def main():
    parser = argparse.ArgumentParser(description="Jev-Style DOM Element Indexer & Browser Operator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Inspect subcommand
    p_inspect = subparsers.add_parser("inspect", help="Inspect and print indexed interactive element table")
    p_inspect.add_argument("url", help="Target URL")
    p_inspect.add_argument("--headed", action="store_true", help="Run headed browser")
    p_inspect.add_argument("--json", action="store_true", help="Output raw JSON")
    p_inspect.add_argument("--delay", type=float, default=1.5, help="Hydration wait in seconds")

    # Run actions subcommand
    p_run = subparsers.add_parser("run", help="Execute action sequence by element index")
    p_run.add_argument("url", help="Target URL")
    p_run.add_argument("--actions", required=True, help="JSON array of actions e.g. '[{\"action\":\"click\",\"target_id\":2}]'")
    p_run.add_argument("--screenshot", default=None, help="Save final screenshot path")
    p_run.add_argument("--headed", action="store_true", help="Run headed browser")

    args = parser.parse_args()

    if args.command == "inspect":
        res = asyncio.run(inspect_page(args.url, headed=args.headed, delay=args.delay))
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"\n=================================================================")
            print(f"PAGE: {res.get('title')} ({res.get('url')})")
            print(f"INTERACTIVE ELEMENT INDEX (Jev-Ultrafast Action Space):")
            print(f"=================================================================")
            for el in res.get("elements", []):
                e_id = f"[{el['id']}]".ljust(6)
                role = f"{el['role']}".ljust(12)
                desc = el['description']
                extra = f" {el['extra']}" if el.get('extra') else ""
                print(f"{e_id} {role} {desc}{extra}")
            print(f"\nTotal interactive elements: {len(res.get('elements', []))}")

    elif args.command == "run":
        try:
            action_list = json.loads(args.actions)
        except Exception as e:
            print(f"Error parsing --actions JSON: {e}", file=sys.stderr)
            sys.exit(1)

        res = asyncio.run(execute_action_sequence(
            url=args.url,
            actions=action_list,
            headed=args.headed,
            screenshot_path=args.screenshot
        ))
        print(json.dumps(res, indent=2))

if __name__ == "__main__":
    main()
