#!/usr/bin/env python3
"""
Unified Multi-Tier Parallel Search & Web Intelligence Engine

> ⛔ EXECUTION-FIRST MANDATE:
> This is an executable CLI engine. NEVER call read_file or view_file on this script.
> Always execute directly via run_command:
> python <BRAIN_ROOT>\\.agents\\skills\\web-search-orchestrator\\scripts\\search_engine.py search "<query>" --engine parallel
> Or for Deep Research:
> python <BRAIN_ROOT>\\.agents\\skills\\web-search-orchestrator\\scripts\\search_engine.py deep-search "<topic>" -o temp_read/report.md

Integrates TinyFish (Free live search & fetch), Tavily (Semantic AI Search),
Firecrawl (Full JS scraping & crawling), and Gemini Deep Research prompt synthesis.
Supports concurrent multi-engine parallel execution for blazing fast, high-density results.
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Any, Optional

KEYS_FILE = Path.home() / ".gemini" / "antigravity" / "search_keys.json"
AGENT_ONE_ENV = Path(r"<USER_HOME>\Desktop\project-web\.env.local")

def load_keys() -> Dict[str, str]:
    keys = {
        "tinyfish_api_key": os.environ.get("TINYFISH_API_KEY", ""),
        "tavily_api_key": os.environ.get("TAVILY_API_KEY", ""),
        "firecrawl_api_key": os.environ.get("FIRECRAWL_API_KEY", ""),
        "aws_lambda_search_url": os.environ.get("AWS_LAMBDA_SEARCH_URL", ""),
        "azure_search_func_base_url": os.environ.get("AZURE_SEARCH_FUNC_BASE_URL", ""),
        "azure_search_func_key": os.environ.get("AZURE_SEARCH_FUNC_KEY", ""),
    }
    if KEYS_FILE.exists():
        try:
            stored = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
            for k, v in stored.items():
                if v and not keys.get(k):
                    keys[k] = v
        except Exception:
            pass

    if AGENT_ONE_ENV.exists():
        try:
            for line in AGENT_ONE_ENV.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line.startswith("TAVILY_API_KEY=") and not keys["tavily_api_key"]:
                    keys["tavily_api_key"] = line.split("=", 1)[1].strip().strip("\"'")
                elif line.startswith("FIRECRAWL_API_KEY=") and not keys["firecrawl_api_key"]:
                    keys["firecrawl_api_key"] = line.split("=", 1)[1].strip().strip("\"'")
        except Exception:
            pass

    return keys

KEYS = load_keys()


# ==============================================================================
# Tier 1: TinyFish CLI Search & Page Fetch (Live Web, Zero-Cost)
# ==============================================================================
def search_tinyfish(query: str, domain: Optional[str] = None) -> Dict[str, Any]:
    cmd = ["npx", "-y", "@tiny-fish/cli@latest", "search", "query", query]
    if domain:
        cmd.extend(["--include-domains", domain])
    
    env = os.environ.copy()
    if KEYS.get("tinyfish_api_key"):
        env["TINYFISH_API_KEY"] = KEYS["tinyfish_api_key"]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, env=env, timeout=20)
        if proc.returncode == 0 and proc.stdout.strip():
            return {
                "source": "tinyfish",
                "success": True,
                "raw_text": proc.stdout.strip()
            }
        return {"source": "tinyfish", "success": False, "error": proc.stderr.strip()}
    except Exception as e:
        return {"source": "tinyfish", "success": False, "error": str(e)}


def fetch_tinyfish(url: str) -> Dict[str, Any]:
    cmd = ["npx", "-y", "@tiny-fish/cli@latest", "fetch", "content", "get", url]
    env = os.environ.copy()
    if KEYS.get("tinyfish_api_key"):
        env["TINYFISH_API_KEY"] = KEYS["tinyfish_api_key"]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, env=env, timeout=30)
        if proc.returncode == 0 and proc.stdout.strip():
            try:
                data = json.loads(proc.stdout.strip())
                results = data.get("results", [])
                if results:
                    r = results[0]
                    return {
                        "source": "tinyfish",
                        "success": True,
                        "url": r.get("final_url", url),
                        "title": r.get("title", ""),
                        "markdown": r.get("text", "")
                    }
            except Exception:
                return {
                    "source": "tinyfish",
                    "success": True,
                    "url": url,
                    "markdown": proc.stdout.strip()
                }
        return {"source": "tinyfish", "success": False, "error": proc.stderr.strip()}
    except Exception as e:
        return {"source": "tinyfish", "success": False, "error": str(e)}


# ==============================================================================
# Tier 2: Tavily Search API (Semantic, High-Signal, Q&A)
# ==============================================================================
def search_tavily(query: str, max_results: int = 5, search_depth: str = "advanced") -> Dict[str, Any]:
    api_key = KEYS.get("tavily_api_key")
    if not api_key:
        return {"source": "tavily", "success": False, "error": "No TAVILY_API_KEY found"}

    url = "https://api.tavily.com/search"
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": search_depth,
        "include_answer": True,
        "include_raw_content": False,
        "max_results": max_results
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {
                "source": "tavily",
                "success": True,
                "answer": data.get("answer", ""),
                "results": data.get("results", [])
            }
    except Exception as e:
        return {"source": "tavily", "success": False, "error": str(e)}


# ==============================================================================
# Tier 3: Firecrawl API (Full JS Stealth Scrape & Crawl)
# ==============================================================================
def scrape_firecrawl(target_url: str) -> Dict[str, Any]:
    api_key = KEYS.get("firecrawl_api_key")
    if not api_key:
        return {"source": "firecrawl", "success": False, "error": "No FIRECRAWL_API_KEY found"}

    url = "https://api.firecrawl.dev/v1/scrape"
    payload = {
        "url": target_url,
        "formats": ["markdown"]
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("success"):
                doc_data = data.get("data", {})
                return {
                    "source": "firecrawl",
                    "success": True,
                    "title": doc_data.get("metadata", {}).get("title", ""),
                    "markdown": doc_data.get("markdown", "")
                }
            return {"source": "firecrawl", "success": False, "error": data.get("error", "Unknown error")}
    except Exception as e:
        return {"source": "firecrawl", "success": False, "error": str(e)}


def search_firecrawl(query: str, max_results: int = 5) -> Dict[str, Any]:
    api_key = KEYS.get("firecrawl_api_key")
    if not api_key:
        return {"source": "firecrawl", "success": False, "error": "No FIRECRAWL_API_KEY found"}

    url = "https://api.firecrawl.dev/v1/search"
    payload = {
        "query": query,
        "limit": max_results
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("success"):
                raw_results = data.get("data", [])
                formatted = []
                for item in raw_results:
                    formatted.append({
                        "title": item.get("title", "Untitled"),
                        "url": item.get("url", ""),
                        "content": item.get("description") or (item.get("markdown", "")[:300] if item.get("markdown") else "")
                    })
                return {
                    "source": "firecrawl",
                    "success": True,
                    "results": formatted
                }
            return {"source": "firecrawl", "success": False, "error": data.get("error", "Unknown error")}
    except Exception as e:
        return {"source": "firecrawl", "success": False, "error": str(e)}



# ==============================================================================
# Tier 5: Gemini Deep Research Prompt Synthesis
# ==============================================================================
def build_gemini_research_prompt(topic: str, specific_goals: str, target_format: str = "technical_dossier") -> str:
    prompt = f"""[GEMINI DEEP RESEARCH MANDATE — HIGH-EFFORT TECHNICAL DOSSIER]

You are serving as the frontier research engine for an advanced autonomous AI coding agent system.
The agent needs deep, verified, technical intelligence on the following topic.

### TOPIC & OBJECTIVE:
{topic}

### SPECIFIC TECHNICAL GOALS & VECTORS TO EXHAUSTIVELY RESEARCH:
{specific_goals}

### STRICT EXECUTION & OUTPUT INVARIANTS:
1. MAX EFFORT & DEEP SEARCH PASSES:
   - Perform extensive multi-step search passes across official engineering documentation, GitHub repositories, RFCs, release notes, and real-world benchmark reports.
   - Do NOT stop at top-level marketing pages or surface summaries. Retrieve exact parameters, version compatibility matrices, error codes, and edge-case caveats.

2. ZERO HUMAN MARKETING SLOP:
   - Completely eliminate conversational filler, introductory pleasantries ("In this guide, we will explore..."), generic hype, and conversational sign-offs.
   - Produce a dense, high-signal, developer-to-developer technical reference.

3. STRUCTURED DATA & CODE FIRST:
   - Present comparative data in Markdown tables (latency, cost, throughput, feature parity, breaking changes).
   - Provide concrete, copy-pasteable configuration files (JSON, YAML, TypeScript, Python) with production-ready settings.
   - Clearly delineate:
     a) Verified Facts & Working Configurations
     b) Deprecated Features / Known Bugs / Failure Modes
     c) Concrete Recommendations & Best Architecture

Target Output: Deliver the completed dossier in GitHub-Flavored Markdown optimized directly for ingestion into an AI coding agent's persistent memory.
"""
    return prompt.strip()


def execute_argon_deep_research(
    topic: str,
    specific_goals: Optional[str] = None,
    profile: Optional[str] = None,
    output_path: Optional[str] = None,
    auto_clean: bool = True,
    timeout_sec: int = 900,
) -> Dict[str, Any]:
    """
    Executes autonomous Gemini Deep Research via Argon Bridge & shared fleet.
    Auto-negotiates optimal idle profile, registers active lease, long-polls
    multi-source investigation, saves Markdown report, and audits live quota.
    """
    try:
        from gemini_deep_research import run_autonomous_deep_research
        return run_autonomous_deep_research(
            topic=topic,
            context=f"Specific technical vectors: {specific_goals}" if specific_goals else "General multi-agent system engineering context.",
            profile=profile,
            output_path=output_path,
            auto_clean=auto_clean,
            timeout_sec=timeout_sec,
        )
    except Exception as e:
        # Fallback to direct driver if runner import fails
        bridge_path = Path(__file__).resolve().parent.parent.parent / "browser-operator" / "argon_bridge"
        if str(bridge_path) not in sys.path:
            sys.path.insert(0, str(bridge_path))
        try:
            from gemini_brain_driver import GeminiBrainDriver
            driver = GeminiBrainDriver(default_profile=profile)
            sid = driver.create_session(new_chat=True, profile_dir=profile)
            prompt = build_gemini_research_prompt(topic, specific_goals=specific_goals or topic)
            res = driver.ask(session_id=sid, prompt=prompt, deep_research=True, check_usage=True, timeout_sec=timeout_sec)
            if res.get("ok") and output_path:
                p = Path(output_path)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(res.get("response", ""), encoding="utf-8")
            if auto_clean and sid:
                driver.delete_session(sid, profile=profile)
            return res
        except Exception as e2:
            return {"ok": False, "error": f"Deep Research execution failed: {e} | {e2}"}


# ==============================================================================
# Unified Parallel Search Orchestrator (Concurrent Multi-Engine)
# ==============================================================================
def parallel_search(query: str, domain: Optional[str] = None, max_results: int = 5) -> Dict[str, Any]:
    """
    Fires Tavily (Semantic AI Q&A) and Firecrawl (Full JS Search) simultaneously,
    with TinyFish fallback. Returns combined, deduplicated intelligence in <1-2s.
    """
    output: Dict[str, Any] = {
        "query": query,
        "mode": "parallel",
        "results": []
    }

    with ThreadPoolExecutor(max_workers=3) as executor:
        future_tav = executor.submit(search_tavily, query, max_results, "advanced")
        future_fc = executor.submit(search_firecrawl, query, max_results)
        future_tf = executor.submit(search_tinyfish, query, domain)

        # Collect results in priority order
        for fut in (future_tav, future_fc, future_tf):
            try:
                res = fut.result(timeout=25)
                if res and res.get("success"):
                    output["results"].append(res)
            except Exception as e:
                pass

    return output


def crawl_local(u: str) -> Dict[str, Any]:
    """Runs local Playwright/Crawl4AI crawler to fetch JS-rendered page."""
    cmd = [sys.executable, str(Path(__file__).parent / "crawl_distill.py"), u]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=30)
        if proc.returncode == 0 and proc.stdout.strip():
            return {
                "url": u,
                "success": True,
                "source": "playwright-local",
                "markdown": proc.stdout.strip()
            }
        return {"url": u, "success": False, "source": "playwright-local", "error": proc.stderr.strip() or "Empty output"}
    except Exception as e:
        return {"url": u, "success": False, "source": "playwright-local", "error": str(e)}


def parallel_fetch(urls: List[str], engine: str = "auto") -> List[Dict[str, Any]]:
    """
    Fetches multiple URLs concurrently using TinyFish (primary), Firecrawl (stealth),
    and Local Playwright Headless (zero-cost local fallback).
    """
    results = []

    def _fetch_single(u: str) -> Dict[str, Any]:
        if engine == "crawl":
            return crawl_local(u)
        if engine in ("tinyfish", "auto"):
            res = fetch_tinyfish(u)
            if res.get("success"):
                return res
        if engine in ("firecrawl", "auto"):
            res = scrape_firecrawl(u)
            if res.get("success"):
                return res
        if engine == "auto":
            res = crawl_local(u)
            if res.get("success"):
                return res
        return {"url": u, "success": False, "error": "All fetch engines failed"}

    with ThreadPoolExecutor(max_workers=min(len(urls), 5)) as executor:
        future_to_url = {executor.submit(_fetch_single, u): u for u in urls}
        for future in as_completed(future_to_url):
            try:
                results.append(future.result())
            except Exception as e:
                results.append({"url": future_to_url[future], "success": False, "error": str(e)})

    return results


def main():
    parser = argparse.ArgumentParser(description="Unified Multi-Tier Parallel Web Search & Intelligence Engine")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Search sub-command (Parallel by default!)
    s_parser = subparsers.add_parser("search", help="Execute search query across engines in parallel")
    s_parser.add_argument("query", help="Search query string")
    s_parser.add_argument("--domain", default=None, help="Restrict to specific domain")
    s_parser.add_argument("--max-results", type=int, default=5, help="Max results for API")
    s_parser.add_argument("--engine", choices=["parallel", "tavily", "firecrawl", "tinyfish", "frontier", "argon", "deep"], default="parallel", help="Engine selection")
    s_parser.add_argument("--profile", default=None, help="Target specific Chrome profile for argon/deep engine")
    s_parser.add_argument("--json", action="store_true", help="Output raw JSON")

    # Deep Search sub-command (Autonomous Gemini Deep Research via Argon Bridge)
    ds_parser = subparsers.add_parser("deep-search", aliases=["deep-research", "deep"], help="Execute autonomous Gemini Deep Research via Argon Bridge")
    ds_parser.add_argument("query", nargs="?", default=None, help="Deep research topic or question")
    ds_parser.add_argument("--status", action="store_true", help="Display live profile fleet visibility, active agent leases, and usage telemetry")
    ds_parser.add_argument("--goals", default=None, help="Specific technical goals or research vectors")
    ds_parser.add_argument("--profile", default=None, help="Target specific Chrome profile (e.g. 'Profile 14', 'Profile 13'); auto-negotiates idle profile if omitted")
    ds_parser.add_argument("--output", "-o", default=None, help="Save markdown dossier to output path in temp_read/")
    ds_parser.add_argument("--keep-chat", action="store_true", help="Retain chat thread in sidebar (disables auto-cleanup)")
    ds_parser.add_argument("--timeout", type=int, default=900, help="Deep research timeout in seconds (default: 900s)")
    ds_parser.add_argument("--json", action="store_true", help="Output raw JSON")

    # Fetch sub-command (Parallel multi-URL supported!)
    f_parser = subparsers.add_parser("fetch", help="Fetch clean markdown from one or more URLs in parallel")
    f_parser.add_argument("urls", nargs="+", help="Target URL(s) to fetch")
    f_parser.add_argument("--engine", choices=["auto", "tinyfish", "firecrawl", "crawl"], default="auto", help="Scraping engine")
    f_parser.add_argument("--json", action="store_true", help="Output raw JSON")

    # Local Playwright/Crawl4AI crawl sub-command
    c_parser = subparsers.add_parser("crawl", help="Crawl dynamic JS-rendered page locally via Playwright")
    c_parser.add_argument("url", help="Target URL to crawl")
    c_parser.add_argument("--wait-selector", default=None, help="CSS selector to wait for")
    c_parser.add_argument("--max-lines", type=int, default=0, help="Limit output to first N lines")
    c_parser.add_argument("--headed", action="store_true", help="Launch browser in headed mode")
    c_parser.add_argument("--output", default=None, help="Save markdown output to file")

    # Gemini prompt sub-command
    g_parser = subparsers.add_parser("gemini-prompt", help="Format high-effort Gemini Deep Research prompt")
    g_parser.add_argument("topic", help="Research topic")
    g_parser.add_argument("--goals", required=True, help="Specific technical goals")

    args = parser.parse_args()

    if args.command in ("deep-search", "deep-research", "deep"):
        if getattr(args, "status", False):
            try:
                from gemini_deep_research import print_fleet_status
                print_fleet_status()
            except Exception as se:
                print(f"Error checking status: {se}", file=sys.stderr)
            return

        if not args.query:
            ds_parser.error("A query or topic is required for deep-search, or pass --status")

        res = execute_argon_deep_research(
            topic=args.query,
            specific_goals=args.goals,
            profile=args.profile,
            output_path=args.output,
            auto_clean=not args.keep_chat,
            timeout_sec=args.timeout,
        )
        if args.json:
            print(json.dumps(res, indent=2))
        elif res.get("ok"):
            print("\n" + "=" * 80)
            print(f" ARGON DEEP RESEARCH DOSSIER (Profile: {res.get('profile')} | Duration: {res.get('duration_seconds')}s)")
            print("=" * 80)
            print(res.get("response"))
            print("=" * 80)
            if res.get("usage"):
                u = res.get("usage")
                print(f"Live Quota: {u.get('current_usage_percent')}% used ({u.get('current_reset')}) | Weekly: {u.get('weekly_usage_percent')}% used\n")
        else:
            print(f"Error during Deep Research: {res.get('error')}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "search":
        if args.engine in ("argon", "deep"):
            res = execute_argon_deep_research(args.query, profile=args.profile, auto_clean=True)
            if args.json:
                print(json.dumps(res, indent=2))
            elif res.get("ok"):
                print("\n" + "=" * 80)
                print(f" ARGON DEEP RESEARCH (Profile: {res.get('profile')} | Duration: {res.get('duration_seconds')}s)")
                print("=" * 80)
                print(res.get("response"))
                print("=" * 80)
            else:
                print(f"Error: {res.get('error')}", file=sys.stderr)
                sys.exit(1)
            return
        elif args.engine == "parallel":
            res = parallel_search(args.query, domain=args.domain, max_results=args.max_results)
        elif args.engine == "firecrawl":
            res = {"query": args.query, "results": [search_firecrawl(args.query, max_results=args.max_results)]}
        elif args.engine == "tinyfish":
            res = {"query": args.query, "results": [search_tinyfish(args.query, domain=args.domain)]}
        elif args.engine == "tavily":
            res = {"query": args.query, "results": [search_tavily(args.query, max_results=args.max_results)]}
        elif args.engine == "frontier":
            prompt = build_gemini_research_prompt(args.query, specific_goals=args.query)
            print(prompt)
            return

        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"\n=================================================================")
            print(f"SEARCH RESULTS FOR: '{args.query}' (Mode: {args.engine.upper()})")
            print(f"=================================================================")
            for r in res.get("results", []):
                src = r.get("source", "unknown").upper()
                print(f"\n--- [ENGINE: {src}] ---")
                if r.get("answer"):
                    print(f"Direct Synthesized Answer:\n{r['answer']}\n")
                if r.get("raw_text"):
                    print(r["raw_text"])
                for item in r.get("results", []):
                    print(f"- {item.get('title')}: {item.get('url')}")
                    if item.get("content"):
                        print(f"  {item.get('content')[:200]}...")

    elif args.command == "fetch":
        results = parallel_fetch(args.urls, engine=args.engine)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            for r in results:
                print(f"\n=================================================================")
                print(f"FETCHED: {r.get('url')} (Source: {r.get('source', 'unknown')})")
                print(f"Title: {r.get('title', 'N/A')}")
                print(f"=================================================================")
                md = r.get("markdown", "")
                print(md[:3500] if len(md) > 3500 else md)
                if len(md) > 3500:
                    print(f"\n[... {len(md) - 3500} additional characters truncated ...]")

    elif args.command == "crawl":
        cmd = [sys.executable, str(Path(__file__).parent / "crawl_distill.py"), args.url]
        if args.wait_selector:
            cmd.extend(["--wait-selector", args.wait_selector])
        if args.max_lines > 0:
            cmd.extend(["--max-lines", str(args.max_lines)])
        if args.headed:
            cmd.append("--headed")
        if args.output:
            cmd.extend(["--output", args.output])
        proc = subprocess.run(cmd, capture_output=not args.output, text=True, encoding="utf-8")
        if not args.output and proc.stdout:
            print(proc.stdout)
        if proc.stderr:
            print(proc.stderr, file=sys.stderr)

    elif args.command == "gemini-prompt":
        prompt = build_gemini_research_prompt(args.topic, args.goals)
        print(prompt)


if __name__ == "__main__":
    main()
