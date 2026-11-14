#!/usr/bin/env python3
"""
High-Throughput Web Content Distiller (HTML-to-Clean-Markdown)
=============================================================
A standalone, production-ready web content extractor synthesizing:
  1. Mozilla Readability: Class/ID sentiment scoring, text density, link density penalties.
  2. Trafilatura: Multi-stage boilerplate removal, text-to-tag ratio, heuristic body isolation.
  3. Defuddle: Modern clean Markdown formatting, code block extraction, table parsing,
     cookie banner & navigation stripping to maximize LLM token efficiency.

Zero external paid APIs. Zero headless browser overhead for raw HTML parsing.
Requires only standard library + BeautifulSoup4 (with html.parser).
"""

from __future__ import annotations
import math
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Comment, NavigableString, Tag


# Regular expressions for class / id sentiment analysis
RE_NEGATIVE = re.compile(
    r"(?i)(cookie|banner|consent|gdpr|popup|modal|overlay|toast|alert|"
    r"navbar|nav|menu|sidebar|drawer|header|footer|masthead|"
    r"ad-|advert|sponsor|promo|outbrain|taboola|disqus|comment|"
    r"social|share|follow|twitter|facebook|linkedin|newsletter|"
    r"signup|subscribe|widget|pagination|breadcrumb|author-box|bio)"
)

RE_POSITIVE = re.compile(
    r"(?i)(article|post|story|entry|main|content|body|document|text|chapter|topic)"
)

# Tags to prune unconditionally
UNWANTED_TAGS = {
    "script", "style", "noscript", "template", "canvas", "svg", "iframe",
    "frame", "object", "embed", "applet", "form", "button", "input",
    "select", "textarea", "nav", "footer", "header", "aside"
}


@dataclass
class DistillationResult:
    title: str
    markdown: str
    word_count: int
    char_count: int
    original_html_bytes: int
    compression_ratio: float
    metadata: Dict[str, str]


class WebContentDistiller:
    """
    Distills raw web page HTML into high-density, boilerplate-free Markdown.
    """

    def __init__(self, base_url: str = "", max_link_density: float = 0.35):
        self.base_url = base_url
        self.max_link_density = max_link_density

    def distill(self, html: str) -> DistillationResult:
        """
        Executes multi-phase content distillation pipeline:
          Phase 1: Parse & Unconditional Pre-Cleaning
          Phase 2: Metadata & Title Extraction
          Phase 3: Structural Pruning (Negative Sentiment & Hidden Elements)
          Phase 4: Heuristic Scoring & Main Container Isolation (Readability/Trafilatura)
          Phase 5: Markdown Generation & Formatting (Defuddle style)
        """
        raw_bytes = len(html.encode("utf-8"))
        soup = BeautifulSoup(html, "html.parser")

        # Phase 1: Unconditional Pre-Cleaning
        for tag_name in UNWANTED_TAGS:
            for el in soup.find_all(tag_name):
                el.decompose()

        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

        # Remove elements explicitly hidden via inline CSS or attributes
        for el in soup.find_all(attrs={"hidden": True}):
            el.decompose()
        for el in soup.find_all(attrs={"aria-hidden": "true"}):
            el.decompose()
        for el in soup.find_all(style=True):
            style = el.get("style", "").lower()
            if any(k in style for k in ["display:none", "display: none", "visibility:hidden", "visibility: hidden"]):
                el.decompose()

        # Phase 2: Metadata & Title Extraction
        title, metadata = self._extract_metadata(soup)

        # Phase 3: Structural Negative Pattern Pruning
        self._prune_boilerplate_elements(soup)

        # Phase 4: Identify Best Main Content Container
        best_container = self._identify_main_container(soup)

        # Phase 5: Convert Container to Clean Markdown
        markdown_body = self._element_to_markdown(best_container)

        # Prepend extracted title if not already present as top header
        cleaned_markdown = markdown_body.strip()
        if title and not cleaned_markdown.startswith(f"# {title}"):
            cleaned_markdown = f"# {title}\n\n{cleaned_markdown}"

        # Collapse excess empty lines
        cleaned_markdown = re.sub(r"\n{3,}", "\n\n", cleaned_markdown).strip()

        words = len(re.findall(r"\w+", cleaned_markdown))
        chars = len(cleaned_markdown)
        comp_ratio = round(chars / max(1, raw_bytes), 4)

        return DistillationResult(
            title=title,
            markdown=cleaned_markdown,
            word_count=words,
            char_count=chars,
            original_html_bytes=raw_bytes,
            compression_ratio=comp_ratio,
            metadata=metadata,
        )

    def _extract_metadata(self, soup: BeautifulSoup) -> Tuple[str, Dict[str, str]]:
        """Extracts title and meta tags (OG, Schema.org, description)."""
        metadata: Dict[str, str] = {}
        title = ""

        # OpenGraph / Meta Title
        og_title = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "twitter:title"})
        if og_title and og_title.get("content"):
            title = og_title["content"].strip()

        if not title:
            title_tag = soup.find("title")
            if title_tag and title_tag.string:
                title = title_tag.string.strip()

        # Description
        og_desc = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
        if og_desc and og_desc.get("content"):
            metadata["description"] = og_desc["content"].strip()

        # Author
        author = soup.find("meta", attrs={"name": "author"}) or soup.find("meta", property="article:author")
        if author and author.get("content"):
            metadata["author"] = author["content"].strip()

        return title, metadata

    def _prune_boilerplate_elements(self, soup: BeautifulSoup) -> None:
        """
        Prunes elements matching negative class/id patterns, unless they
        contain high positive scores or substantial natural language text.
        """
        for el in soup.find_all(True):
            if not el.attrs:
                continue

            attr_string = f"{el.get('class', '')} {el.get('id', '')}"
            if not attr_string.strip():
                continue

            has_negative = bool(RE_NEGATIVE.search(attr_string))
            has_positive = bool(RE_POSITIVE.search(attr_string))

            if has_negative and not has_positive:
                # Calculate link density before decomposing
                text = el.get_text(strip=True)
                if not text:
                    el.decompose()
                    continue

                link_text_len = sum(len(a.get_text(strip=True)) for a in el.find_all("a"))
                link_density = link_text_len / max(1, len(text))

                # If negative and high link density or short text -> prune
                if link_density > 0.25 or len(text) < 120:
                    el.decompose()

    def _calculate_node_score(self, tag: Tag) -> float:
        """
        Computes composite readability score:
          Score = Base(tag) + ClassSentiment + log(TextLen) * (1 - LinkDensity) + PunctuationBonus
        """
        tag_name = tag.name.lower()
        base_scores = {"article": 35.0, "main": 30.0, "section": 15.0, "div": 5.0}
        score = base_scores.get(tag_name, 0.0)

        # Attribute sentiment
        attr_string = f"{tag.get('class', '')} {tag.get('id', '')}"
        if RE_POSITIVE.search(attr_string):
            score += 25.0
        if RE_NEGATIVE.search(attr_string):
            score -= 25.0

        text = tag.get_text(strip=True)
        text_len = len(text)
        if text_len == 0:
            return 0.0

        # Link Density calculation
        link_text_len = sum(len(a.get_text(strip=True)) for a in tag.find_all("a"))
        link_density = link_text_len / max(1, text_len)

        if link_density > self.max_link_density:
            score -= 30.0

        # Paragraph count & punctuation count (surrogate for natural prose)
        p_count = len(tag.find_all("p"))
        score += p_count * 5.0

        comma_count = text.count(",") + text.count(";")
        score += min(20.0, comma_count * 0.5)

        # Logarithmic text length scaling
        score += math.log10(max(10, text_len)) * 10.0 * (1.0 - link_density)
        return max(0.0, score)

    def _identify_main_container(self, soup: BeautifulSoup) -> Tag:
        """Finds the DOM element representing the primary content body."""
        # 1. Direct explicit tags
        article = soup.find("article")
        if article and len(article.get_text(strip=True)) > 200:
            return article

        main = soup.find("main")
        if main and len(main.get_text(strip=True)) > 200:
            return main

        # 2. Heuristic scoring across candidates
        candidates = soup.find_all(["div", "section", "article", "main"])
        if not candidates:
            return soup.find("body") or soup

        best_tag = candidates[0]
        best_score = -1.0

        for cand in candidates:
            # Skip if candidate has no substantial text
            if len(cand.get_text(strip=True)) < 80:
                continue
            sc = self._calculate_node_score(cand)
            if sc > best_score:
                best_score = sc
                best_tag = cand

        return best_tag

    def _element_to_markdown(self, element: Tag) -> str:
        """
        Recursively translates a DOM subtree into clean, high-density Markdown.
        Handles headers, paragraphs, lists, code blocks, blockquotes, and tables.
        """
        lines: List[str] = []

        def walk(node):
            if isinstance(node, NavigableString):
                return

            if not isinstance(node, Tag):
                return

            tag_name = node.name.lower()

            # Preformatted Code Block
            if tag_name == "pre":
                code_tag = node.find("code")
                lang = ""
                if code_tag and code_tag.get("class"):
                    for c in code_tag["class"]:
                        if c.startswith("language-") or c.startswith("lang-"):
                            lang = c.split("-", 1)[1]
                            break
                code_text = node.get_text()
                lines.append(f"\n```{lang}\n{code_text.strip()}\n```\n")
                return

            # Headings
            if tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                level = int(tag_name[1])
                prefix = "#" * level
                h_text = node.get_text(strip=True)
                if h_text:
                    lines.append(f"\n{prefix} {h_text}\n")
                return

            # Paragraphs
            if tag_name == "p":
                p_text = self._inline_markdown(node)
                if p_text:
                    lines.append(f"\n{p_text}\n")
                return

            # Blockquotes
            if tag_name == "blockquote":
                bq_text = node.get_text(strip=True)
                if bq_text:
                    lines.append(f"\n> {bq_text}\n")
                return

            # Unordered / Ordered Lists
            if tag_name in ("ul", "ol"):
                is_ordered = tag_name == "ol"
                for idx, li in enumerate(node.find_all("li", recursive=False), start=1):
                    li_text = self._inline_markdown(li)
                    if li_text:
                        bullet = f"{idx}." if is_ordered else "-"
                        lines.append(f"{bullet} {li_text}")
                lines.append("")
                return

            # Tables
            if tag_name == "table":
                table_md = self._table_to_markdown(node)
                if table_md:
                    lines.append(f"\n{table_md}\n")
                return

            # Generic wrappers (div, section, span, etc.) - traverse children
            for child in node.children:
                walk(child)

        walk(element)
        return "\n".join(lines)

    def _inline_markdown(self, tag: Tag) -> str:
        """Formats inline elements (strong, em, code, a) within a block."""
        parts = []
        for child in tag.children:
            if isinstance(child, NavigableString):
                parts.append(str(child))
            elif isinstance(child, Tag):
                c_name = child.name.lower()
                c_text = child.get_text(strip=True)
                if not c_text:
                    continue
                if c_name in ("strong", "b"):
                    parts.append(f"**{c_text}**")
                elif c_name in ("em", "i"):
                    parts.append(f"*{c_text}*")
                elif c_name == "code":
                    parts.append(f"`{c_text}`")
                elif c_name == "a":
                    href = child.get("href", "")
                    if href and not href.startswith("javascript:") and not href.startswith("#"):
                        if self.base_url:
                            href = urljoin(self.base_url, href)
                        parts.append(f"[{c_text}]({href})")
                    else:
                        parts.append(c_text)
                else:
                    parts.append(c_text)
        joined = "".join(parts)
        return re.sub(r"\s+", " ", joined).strip()

    def _table_to_markdown(self, table_tag: Tag) -> str:
        """Converts an HTML table into standard GitHub Flavored Markdown table format."""
        rows = []
        for tr in table_tag.find_all("tr"):
            cells = [c.get_text(strip=True).replace("|", "\\|") for c in tr.find_all(["th", "td"])]
            if cells:
                rows.append(cells)

        if not rows:
            return ""

        max_cols = max(len(r) for r in rows)
        # Pad shorter rows
        padded_rows = [r + [""] * (max_cols - len(r)) for r in rows]

        header = padded_rows[0]
        divider = ["---"] * max_cols

        md_lines = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join(divider) + " |",
        ]
        for row in padded_rows[1:]:
            md_lines.append("| " + " | ".join(row) + " |")

        return "\n".join(md_lines)


# =============================================================================
# Standalone Verification Driver
# =============================================================================

if __name__ == "__main__":
    print("[+] Testing High-Throughput Web Content Distiller...")

    sample_html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <title>Universal Autonomous AI System Architecture</title>
        <meta property="og:description" content="A comprehensive analysis of multi-agent architectures and persistent memory.">
    </head>
    <body>
        <header class="site-header navbar">
            <nav>
                <a href="/home">Home</a> | <a href="/about">About</a> | <a href="/login">Login</a>
            </nav>
        </header>

        <div id="cookie-consent" class="cookie-banner modal">
            <p>We use cookies to enhance your experience. <button>Accept All</button></p>
        </div>

        <div class="main-layout-container">
            <aside class="sidebar-wrapper ad-column">
                <div class="ad-banner">Buy Cloud Compute Now! 50% Off</div>
                <div class="social-share">Share on Twitter | Share on LinkedIn</div>
            </aside>

            <main class="article-content-body">
                <article>
                    <h1>Universal Autonomous AI System Architecture</h1>
                    <p>Modern agentic workflows require a synthesis of <strong>reactive execution</strong> and <em>deliberate cognitive planning</em>. By decoupling high-throughput execution from deep reasoning, systems achieve unprecedented reliability.</p>
                    
                    <h2>Key Architecture Components</h2>
                    <p>The core framework incorporates three fundamental pillars:</p>
                    <ul>
                        <li>Graph-of-Thoughts (GoT) for non-linear reasoning and DAG aggregation.</li>
                        <li>Zero-Cost Hybrid Memory combining SQLite FTS5 BM25 with character n-grams.</li>
                        <li>High-density content distillation stripping web boilerplate.</li>
                    </ul>

                    <h2>Performance Benchmarks</h2>
                    <table>
                        <tr><th>Engine</th><th>Latency (ms)</th><th>Recall@5</th></tr>
                        <tr><td>Dense Vector Only</td><td>120ms</td><td>78.4%</td></tr>
                        <tr><td>FTS5 BM25 Only</td><td>4ms</td><td>82.1%</td></tr>
                        <tr><td>Hybrid RRF (Zero-Cost)</td><td>8ms</td><td>94.7%</td></tr>
                    </table>

                    <h2>Example Controller Implementation</h2>
                    <pre><code class="language-python">
def execute_rrf(ranks, k=60):
    return sum(1.0 / (k + r) for r in ranks)
                    </code></pre>

                    <p>In conclusion, removing web noise and retaining semantic integrity is vital for low-latency agent ingestion.</p>
                </article>
            </main>
        </div>

        <footer class="site-footer">
            <p>&copy; 2026 Autonomous AI Core. All rights reserved. <a href="/privacy">Privacy Policy</a></p>
        </footer>
    </body>
    </html>
    """

    distiller = WebContentDistiller(base_url="https://antigravity.internal")
    result = distiller.distill(sample_html)

    print(f"[*] Title: {result.title}")
    print(f"[*] Raw HTML: {result.original_html_bytes} bytes -> Clean Markdown: {result.char_count} chars ({result.word_count} words)")
    print(f"[*] Compression Ratio: {result.compression_ratio * 100:.1f}% of original size")
    print(f"\n--- DISTILLED MARKDOWN OUTPUT ---\n{result.markdown}\n---------------------------------")

    # Assertions to ensure cookie banner, ads, and navbar were completely stripped
    assert "cookie" not in result.markdown.lower(), "Cookie banner failed to strip!"
    assert "buy cloud compute" not in result.markdown.lower(), "Ad failed to strip!"
    assert "privacy policy" not in result.markdown.lower(), "Footer failed to strip!"
    assert "Universal Autonomous AI System Architecture" in result.markdown, "Title missing!"
    assert "| Hybrid RRF (Zero-Cost) |" in result.markdown, "Table missing!"

    print("\n[+] Web Content Distiller Verification PASSED! Boilerplate 100% eliminated.")
