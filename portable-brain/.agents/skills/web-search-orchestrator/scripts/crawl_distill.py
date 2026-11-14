#!/usr/bin/env python3
"""
Local Headless Web Crawler and Markdown Distiller
Part of the web-search-orchestrator universal skill.
Runs locally via Playwright & BeautifulSoup with zero external API fees or credit limits.
Bypasses client-side JS rendering (React/Vue/SPAs) and distills pages into clean Markdown.
"""

import argparse
import asyncio
import os
import re
import sys
from bs4 import BeautifulSoup, Comment
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

try:
    from content_distiller import WebContentDistiller
except ImportError:
    try:
        from .content_distiller import WebContentDistiller
    except ImportError:
        WebContentDistiller = None

def html_to_clean_markdown(html: str, base_url: str = "") -> str:
    """
    Distills raw HTML into clean, high-density Markdown by stripping
    non-semantic wrapper divs, styles, scripts, tracking tags, and navigation.
    """
    if WebContentDistiller:
        try:
            res = WebContentDistiller.distill(html, base_url=base_url)
            return res.markdown
        except Exception:
            pass

    soup = BeautifulSoup(html, "html.parser")

    # Remove all scripts, styles, iframes, svgs, and comments
    for tag in soup(["script", "style", "svg", "noscript", "iframe", "canvas", "meta", "link"]):
        tag.decompose()

    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # Remove elements explicitly styled as hidden
    for el in soup.find_all(style=True):
        style = el.get("style", "").lower()
        if "display:none" in style or "display: none" in style or "visibility:hidden" in style or "visibility: hidden" in style:
            el.decompose()

    # Distill content hierarchy
    output_lines = []

    # Title
    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        output_lines.append(f"# {title_tag.string.strip()}\n")

    # Process body elements sequentially
    body = soup.find("body") or soup
    for el in body.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "pre", "table", "blockquote"]):
        text = re.sub(r"\s+", " ", el.get_text()).strip()
        if not text:
            continue

        tag_name = el.name
        if tag_name == "h1":
            output_lines.append(f"\n# {text}\n")
        elif tag_name == "h2":
            output_lines.append(f"\n## {text}\n")
        elif tag_name == "h3":
            output_lines.append(f"\n### {text}\n")
        elif tag_name in ("h4", "h5", "h6"):
            output_lines.append(f"\n#### {text}\n")
        elif tag_name == "p":
            output_lines.append(f"\n{text}\n")
        elif tag_name == "li":
            output_lines.append(f"- {text}")
        elif tag_name == "pre":
            output_lines.append(f"\n```\n{text}\n```\n")
        elif tag_name == "blockquote":
            output_lines.append(f"\n> {text}\n")
        elif tag_name == "table":
            # Simple tabular extraction
            rows = []
            for tr in el.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                if cells:
                    rows.append(" | ".join(cells))
            if rows:
                output_lines.append("\n" + "\n".join(rows) + "\n")

    # Collapse excessive blank lines
    raw_markdown = "\n".join(output_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", raw_markdown).strip()
    return cleaned

async def crawl(url: str, wait_selector: str = None, timeout: int = 20000, headed: bool = False, delay_seconds: float = 1.5) -> str:
    """Crawls a dynamic web page with Playwright and extracts distilled markdown."""
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
            # Navigate
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            
            # If selector specified, wait for it
            if wait_selector:
                await page.wait_for_selector(wait_selector, timeout=min(timeout, 8000))
            elif delay_seconds > 0:
                await asyncio.sleep(delay_seconds)  # Allow client-side JS hydration

            html = await page.content()
            markdown = html_to_clean_markdown(html, base_url=url)
            return markdown
        except PlaywrightTimeoutError:
            # Fallback to whatever HTML content is currently loaded
            try:
                html = await page.content()
                return html_to_clean_markdown(html, base_url=url)
            except Exception as e:
                return f"Error: Page navigation timed out after {timeout}ms: {e}"
        except Exception as e:
            return f"Error: Crawling failed: {e}"
        finally:
            await browser.close()

def main():
    parser = argparse.ArgumentParser(description="Local Headless Web Crawler and Markdown Distiller (Crawl4AI/Playwright)")
    parser.add_argument("url", help="Target URL to crawl")
    parser.add_argument("--wait-selector", default=None, help="CSS selector to wait for before extracting")
    parser.add_argument("--timeout", type=int, default=20000, help="Navigation timeout in milliseconds")
    parser.add_argument("--delay", type=float, default=1.5, help="Post-load hydration delay in seconds")
    parser.add_argument("--max-lines", type=int, default=0, help="Limit output to first N lines")
    parser.add_argument("--output", default=None, help="Save distilled markdown to file")
    parser.add_argument("--headed", action="store_true", help="Launch browser in headed mode for visual debugging")

    args = parser.parse_args()

    markdown = asyncio.run(crawl(
        url=args.url,
        wait_selector=args.wait_selector,
        timeout=args.timeout,
        headed=args.headed,
        delay_seconds=args.delay
    ))

    lines = markdown.splitlines()
    if args.max_lines > 0 and len(lines) > args.max_lines:
        markdown = "\n".join(lines[:args.max_lines]) + f"\n\n... [Truncated at {args.max_lines} lines]"

    if args.output:
        out_path = os.path.abspath(args.output)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(markdown)
        print(f"[+] Distilled markdown saved to: {out_path} ({len(lines)} lines)")
    else:
        print(markdown)

if __name__ == "__main__":
    main()
